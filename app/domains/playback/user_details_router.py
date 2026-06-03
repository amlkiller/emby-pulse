import datetime
import re
from typing import Optional

from fastapi import APIRouter, Request

from app.domains.playback.stats_helpers import (
    check_login,
    get_clean_name,
    get_user_map_local,
    resolve_poster_ids,
)
from app.domains.playback.stats_queries import build_stats_base_filter, get_playback_column_name
from app.infra.clients.media_server_client import media_api
from app.infra.db.playback_store import playback_store


router = APIRouter()

_check_login_provider = lambda: check_login
_build_stats_base_filter_provider = lambda: build_stats_base_filter
_get_playback_column_name_provider = lambda: get_playback_column_name
_playback_store_provider = lambda: playback_store
_get_user_map_local_provider = lambda: get_user_map_local
_get_clean_name_provider = lambda: get_clean_name
_resolve_poster_ids_provider = lambda: resolve_poster_ids
_media_api_provider = lambda: media_api


def set_dependency_providers(
    *,
    check_login_provider=None,
    build_stats_base_filter_provider=None,
    get_playback_column_name_provider=None,
    playback_store_provider=None,
    get_user_map_local_provider=None,
    get_clean_name_provider=None,
    resolve_poster_ids_provider=None,
    media_api_provider=None,
):
    global _check_login_provider
    global _build_stats_base_filter_provider
    global _get_playback_column_name_provider
    global _playback_store_provider
    global _get_user_map_local_provider
    global _get_clean_name_provider
    global _resolve_poster_ids_provider
    global _media_api_provider

    if check_login_provider is not None:
        _check_login_provider = check_login_provider
    if build_stats_base_filter_provider is not None:
        _build_stats_base_filter_provider = build_stats_base_filter_provider
    if get_playback_column_name_provider is not None:
        _get_playback_column_name_provider = get_playback_column_name_provider
    if playback_store_provider is not None:
        _playback_store_provider = playback_store_provider
    if get_user_map_local_provider is not None:
        _get_user_map_local_provider = get_user_map_local_provider
    if get_clean_name_provider is not None:
        _get_clean_name_provider = get_clean_name_provider
    if resolve_poster_ids_provider is not None:
        _resolve_poster_ids_provider = resolve_poster_ids_provider
    if media_api_provider is not None:
        _media_api_provider = media_api_provider


@router.get("/api/stats/user_details")
def api_user_details(request: Request, user_id: Optional[str] = None):
    # 🔒 安全检查
    if not _check_login_provider()(request):
        return {"status": "error", "message": "请先登录"}

    # 🔒 权限检查：普通用户只能查看自己的数据
    admin_user = request.session.get("user", {})
    req_user = request.session.get("req_user", {})
    is_admin = admin_user.get("auth_type") == "emby" or admin_user.get("role") == "admin"

    # 如果不是管理员，强制只能查看自己的数据
    if not is_admin:
        if req_user:
            user_id = req_user.get("Id")
        elif admin_user:
            user_id = admin_user.get("id")

    try:
        where, params = _build_stats_base_filter_provider()(user_id)
        client_col = _get_playback_column_name_provider()()

        # 🔥 动态检测可用列
        available_cols = ["DateCreated", "ItemName", "ItemId", "PlayDuration", "UserId"]
        try:
            test_sql = "SELECT * FROM PlaybackActivity LIMIT 1"
            test_res = _playback_store_provider().query(test_sql, [])
            if test_res and len(test_res) > 0:
                first_row = test_res[0]
                if hasattr(first_row, 'keys'):
                    available_cols = list(first_row.keys())
                elif isinstance(first_row, dict):
                    available_cols = list(first_row.keys())
        except:
            pass

        # 构建查询字段（只使用存在的列）
        select_fields = ["DateCreated", "ItemName", "ItemId", "PlayDuration", "UserId"]
        if "ItemType" in available_cols:
            select_fields.append("ItemType")
        if "DeviceName" in available_cols:
            select_fields.append("COALESCE(DeviceName, 'Unknown') as Device")
        if client_col in available_cols or client_col.lower() in [c.lower() for c in available_cols]:
            select_fields.append(f"COALESCE({client_col}, 'Unknown') as Client")

        # 🚀 性能优化：合并多次查询为一次大查询
        all_data_sql = f"""
            SELECT {', '.join(select_fields)} FROM PlaybackActivity {where}
            ORDER BY DateCreated DESC
        """
        all_rows = _playback_store_provider().query(all_data_sql, params)

        # 从内存中聚合数据
        h_data = {str(i).zfill(2): 0 for i in range(24)}
        devices_map = {}
        clients_map = {}
        logs = []
        pref = {"movie_plays": 0, "episode_plays": 0}
        agg_fav = {}
        total_plays = 0
        total_duration = 0

        # 用户映射（只查一次）
        u_map = _get_user_map_local_provider()()

        # 限制处理的记录数，提高性能
        max_logs = 100
        processed = 0

        if all_rows:
            for row in all_rows:
                r = dict(row)
                total_plays += 1
                dur = r.get('PlayDuration') or 0
                total_duration += dur

                # 小时分布
                dc = r.get('DateCreated')
                if dc:
                    m = re.search(r'(\d{4})-(\d{2})-(\d{2})[T\s](\d{2}):(\d{2}):(\d{2})', str(dc))
                    if m:
                        hour = m.group(4)
                        h_data[hour] += 1

                # 设备分布（前10）
                device = r.get('Device') or 'Unknown'
                devices_map[device] = devices_map.get(device, 0) + 1

                # 客户端分布（前10）
                client = r.get('Client') or 'Unknown'
                clients_map[client] = clients_map.get(client, 0) + 1

                # 最近记录（前100条）
                if processed < max_logs:
                    l = {
                        'DateCreated': dc,
                        'ItemName': r.get('ItemName'),
                        'ItemId': r.get('ItemId'),
                        'ItemType': r.get('ItemType'),
                        'PlayDuration': dur,
                        'Device': r.get('Device'),
                        'UserId': r.get('UserId'),
                        'UserName': u_map.get(r.get('UserId'), "User"),
                        'smart_poster': f"/api/proxy/smart_image?item_id={r.get('ItemId')}&type=Primary"
                    }
                    if not is_admin:
                        l.pop('UserId', None)  # 🔒 非管理员不暴露原始 UserId
                    logs.append(l)
                    processed += 1

                # 播放偏好
                item_type = r.get('ItemType')
                if item_type == 'Movie':
                    pref['movie_plays'] += 1
                elif item_type == 'Episode':
                    pref['episode_plays'] += 1

                # 最爱内容聚合
                clean = _get_clean_name_provider()(r.get('ItemName'), item_type or '')
                if clean not in agg_fav:
                    agg_fav[clean] = {"ItemName": clean, "ItemId": r.get("ItemId"), "c": 0, "d": 0}
                agg_fav[clean]["c"] += 1
                agg_fav[clean]["d"] += dur

        # 解析海报ID（批量处理最近记录和最爱）
        if logs:
            _resolve_poster_ids_provider()(logs)

        # 设备/客户端排序取前10
        devices = [{"Device": k, "Plays": v} for k, v in sorted(devices_map.items(), key=lambda x: x[1], reverse=True)[:10]]
        clients = [{"Client": k, "Plays": v} for k, v in sorted(clients_map.items(), key=lambda x: x[1], reverse=True)[:10]]

        # 概览数据
        overview = {
            "total_plays": total_plays,
            "total_duration": total_duration,
            "avg_duration": round(total_duration / total_plays) if total_plays > 0 else 0,
            "account_age_days": 1
        }

        # 最爱内容
        top_fav = max(agg_fav.values(), key=lambda x: x['d']) if agg_fav else None
        if top_fav:
            _resolve_poster_ids_provider()([top_fav])

        # 异步获取账号创建时间（不影响主要数据返回）
        try:
            if user_id and user_id != 'all':
                u_res = _media_api_provider().get(f"/Users/{user_id}", timeout=3)
                if u_res.status_code == 200:
                    dc = u_res.json().get("DateCreated")
                    if dc:
                        m = re.search(r'(\d{4})-(\d{2})-(\d{2})', str(dc))
                        if m:
                            fd = datetime.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                            overview['account_age_days'] = max(1, (datetime.datetime.now() - fd).days)
            else:
                u_res = _media_api_provider().get("/Users", timeout=3)
                if u_res.status_code == 200:
                    earliest_dt = None
                    for u in u_res.json():
                        dc = u.get("DateCreated")
                        if dc:
                            m = re.search(r'(\d{4})-(\d{2})-(\d{2})', str(dc))
                            if m:
                                dt = datetime.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                                if not earliest_dt or dt < earliest_dt:
                                    earliest_dt = dt
                    if earliest_dt:
                        overview['account_age_days'] = max(1, (datetime.datetime.now() - earliest_dt).days)
        except Exception: pass

        return {"status": "success", "data": {
            "hourly": h_data, "devices": devices, "clients": clients,
            "logs": logs, "overview": overview, "preference": pref, "top_fav": top_fav
        }}
    except Exception as e:
        return {"status": "error", "data": {"hourly": {}, "devices": [], "clients": [], "logs": []}}
