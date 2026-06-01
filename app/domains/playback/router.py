import ipaddress
import logging
import math
import time
from typing import Optional

from fastapi import APIRouter, Request

from app.core.security_utils import safe_error_message
from app.domains.playback.queries import (
    build_history_select_fields,
    count_history,
    count_today_active_users,
    count_today_plays,
    count_total_plays,
    fetch_history_rowids,
    fetch_history_rows,
    fetch_history_rows_by_rowids,
    fetch_local_ip_data,
    sum_today_duration,
)
from app.infra.clients.media_server_client import media_api
from app.infra.config.user_visibility_settings import get_hidden_users

logger = logging.getLogger("uvicorn")

router = APIRouter()

_history_stats_cache = {"data": None, "expires": 0}
HISTORY_STATS_CACHE_TTL = 300
_user_map_cache = {"data": None, "expires": 0}
_valid_user_ids_cache = {"data": None, "expires": 0}
USER_CACHE_TTL = 300


def check_login(request: Request) -> bool:
    return request.session.get("user") is not None or request.session.get("req_user") is not None


def _is_ipv6(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).version == 6
    except Exception:
        return False


def get_user_map_local():
    if _user_map_cache["data"] and time.time() < _user_map_cache["expires"]:
        return _user_map_cache["data"]

    user_map = {}
    try:
        res = media_api.get("/Users", timeout=2)
        if res.status_code == 200:
            for u in res.json():
                user_map[u["Id"]] = u["Name"]
            _user_map_cache["data"] = user_map
            _user_map_cache["expires"] = time.time() + USER_CACHE_TTL
    except Exception:
        pass
    return user_map


def get_valid_user_ids():
    if _valid_user_ids_cache["data"] and time.time() < _valid_user_ids_cache["expires"]:
        return _valid_user_ids_cache["data"]

    valid_ids = set()
    try:
        res = media_api.get("/Users", timeout=2)
        if res.status_code == 200:
            for u in res.json():
                valid_ids.add(u["Id"])
            _valid_user_ids_cache["data"] = valid_ids
            _valid_user_ids_cache["expires"] = time.time() + USER_CACHE_TTL
    except Exception:
        pass
    return valid_ids


@router.get("/api/history/list")
def api_get_history(
    request: Request,
    page: int = 1,
    limit: int = 20,
    user_id: Optional[str] = None,
    keyword: Optional[str] = None,
):
    if not check_login(request):
        return {"status": "error", "message": "请先登录"}

    admin_user = request.session.get("user", {})
    req_user = request.session.get("req_user", {})
    is_admin = admin_user.get("auth_type") == "emby" or admin_user.get("role") == "admin"

    if not is_admin:
        if req_user:
            user_id = req_user.get("Id")
        elif admin_user:
            user_id = admin_user.get("id")

    try:
        where_clauses = []
        params = []

        hidden_users = get_hidden_users()
        if hidden_users:
            placeholders = ",".join(["?"] * len(hidden_users))
            where_clauses.append(f"UserId NOT IN ({placeholders})")
            params.extend(hidden_users)

        valid_user_ids = get_valid_user_ids()
        if valid_user_ids:
            placeholders = ",".join(["?"] * len(valid_user_ids))
            where_clauses.append(f"UserId IN ({placeholders})")
            params.extend(list(valid_user_ids))

        if user_id and user_id != "all":
            where_clauses.append("UserId = ?")
            params.append(user_id)

        if keyword:
            where_clauses.append("ItemName LIKE ?")
            params.append(f"%{keyword}%")

        where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        select_fields = build_history_select_fields()

        try:
            total = count_history(where_sql, params)
        except Exception:
            total = 0

        try:
            total_pages = math.ceil(total / limit) if limit > 0 else 1
        except Exception:
            total_pages = 1

        if page > 10:
            id_rows = fetch_history_rowids(where_sql, params, limit, (page - 1) * limit)
            if id_rows:
                rowids = [r["rowid"] for r in id_rows]
                rows = fetch_history_rows_by_rowids(select_fields, rowids)
            else:
                rows = []
        else:
            offset = (page - 1) * limit
            rows = fetch_history_rows(select_fields, where_sql, params, limit, offset)

        local_ip_data = fetch_local_ip_data(rows)
        user_map = get_user_map_local()
        result = []
        for row in rows:
            item = dict(row)
            item["UserName"] = user_map.get(item["UserId"], "未知用户")

            seconds = item.get("PlayDuration") or 0
            if seconds < 60:
                item["DurationStr"] = f"{seconds}秒"
            elif seconds < 3600:
                item["DurationStr"] = f"{round(seconds / 60)}分钟"
            else:
                item["DurationStr"] = f"{round(seconds / 3600, 1)}小时"

            try:
                item["DateStr"] = item["DateCreated"].replace("T", " ")[:16]
            except Exception:
                item["DateStr"] = item["DateCreated"]

            local_key = str(item.get("UserId", "")) + "_" + str(item.get("ItemId", ""))
            ip_found = False

            if local_key in local_ip_data and local_ip_data[local_key]["ip"]:
                full_ip = local_ip_data[local_key]["ip"]
                if len(full_ip) > 4:
                    item["IP"] = full_ip
                    item["Location"] = local_ip_data[local_key]["location"]
                    item["ISP"] = local_ip_data[local_key]["isp"]
                    ip_found = True

            if not ip_found:
                ip = row.get("RemoteEndPoint") or ""
                if ip:
                    try:
                        ip_obj = ipaddress.ip_address(ip.split(",")[0].split(":")[0] if "," in ip else ip.split(":")[0])
                        if ip_obj.version == 4 and ":" in ip and ip.count(":") == 1:
                            parts = ip.rsplit(":", 1)
                            if parts[-1].isdigit():
                                ip = parts[0]
                    except Exception:
                        if ip.count(":") == 1 and ip.split(":")[-1].isdigit():
                            ip = ip.rsplit(":", 1)[0]
                item["IP"] = ip or ""

            location = item.get("Location") or ""
            isp = item.get("ISP") or ""
            if location in ["", "未知地区", "未知"]:
                location = ""
            if isp in ["", "未知地区", "未知"]:
                isp = ""
            if location and isp:
                item["LocationStr"] = f"{location} · {isp}"
            elif location:
                item["LocationStr"] = location
            elif isp:
                item["LocationStr"] = isp
            else:
                item["LocationStr"] = "-"

            result.append(item)

        return {
            "status": "success",
            "data": result,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "total_pages": total_pages,
            },
        }
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e), "data": []}


@router.get("/api/history/stats")
def api_get_history_stats(request: Request):
    if not check_login(request):
        return {"status": "error", "message": "请先登录"}

    if _history_stats_cache["data"] and time.time() < _history_stats_cache["expires"]:
        return _history_stats_cache["data"]

    try:
        from datetime import datetime

        now = datetime.now()
        today_start = now.strftime("%Y-%m-%d 00:00:00")
        today_end = now.strftime("%Y-%m-%d 23:59:59")

        hidden_users = get_hidden_users()
        valid_user_ids = get_valid_user_ids()

        hidden_clause = ""
        valid_user_clause = ""
        params = []

        if hidden_users:
            placeholders = ",".join(["?"] * len(hidden_users))
            hidden_clause = f" AND UserId NOT IN ({placeholders})"
            params.extend(hidden_users)

        if valid_user_ids:
            placeholders = ",".join(["?"] * len(valid_user_ids))
            valid_user_clause = f" AND UserId IN ({placeholders})"
            params.extend(list(valid_user_ids))

        today_count = 0
        total_seconds = 0
        active_users = 0
        total_count = 0

        try:
            today_count = count_today_plays(today_start, today_end, hidden_clause + valid_user_clause, params)
        except Exception as e:
            print(f"[统计] 今日播放次数查询失败: {e}")

        try:
            total_seconds = sum_today_duration(today_start, today_end, hidden_clause + valid_user_clause, params)
        except Exception as e:
            print(f"[统计] 今日播放时长查询失败: {e}")

        try:
            active_users = count_today_active_users(today_start, today_end, hidden_clause + valid_user_clause, params)
        except Exception as e:
            print(f"[统计] 活跃用户数查询失败: {e}")

        try:
            total_count = count_total_plays(hidden_clause + valid_user_clause, params)
        except Exception as e:
            print(f"[统计] 累计播放次数查询失败: {e}")

        if total_seconds < 60:
            today_duration = f"{int(total_seconds)}秒"
        elif total_seconds < 3600:
            today_duration = f"{int(total_seconds / 60)}分钟"
        else:
            today_duration = f"{round(total_seconds / 3600, 1)}小时"

        result = {
            "status": "success",
            "data": {
                "today_count": today_count,
                "today_duration": today_duration,
                "active_users": active_users,
                "total_count": total_count,
            },
        }
        _history_stats_cache["data"] = result
        _history_stats_cache["expires"] = time.time() + HISTORY_STATS_CACHE_TTL
        return result
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}
