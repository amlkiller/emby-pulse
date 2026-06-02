import asyncio
import logging
import time
from typing import Optional

from app.domains.playback.stats_queries import build_stats_base_filter
from app.infra.clients.media_server_client import media_api
from app.infra.config.stats_settings import get_dashboard_cache_ttl
from app.infra.config.user_visibility_settings import get_hidden_users
from app.infra.db.playback_store import playback_store

logger = logging.getLogger("uvicorn")

_DASHBOARD_PRELOAD_KEY = "admin:all"
_dashboard_cache = {}
_dashboard_cache_user_ids = {}
_DASHBOARD_CACHE_TTL = get_dashboard_cache_ttl()
_DASHBOARD_ACTIVE_WINDOW = 600
_dashboard_last_access = {}
_dashboard_refresh_lock = asyncio.Lock()

_preload_started = False
_dashboard_cache_tasks_started = False
_dashboard_preload_task = None
_dashboard_refresh_task = None
_last_refresh_log_time = 0


def _normalize_dashboard_user_id(user_id):
    if user_id is None or user_id == "" or user_id == "all":
        return None
    return str(user_id)


def _get_dashboard_context(request, user_id: Optional[str] = None):
    admin_user = request.session.get("user", {}) or {}
    req_user = request.session.get("req_user", {}) or {}
    is_admin = admin_user.get("auth_type") == "emby" or admin_user.get("role") == "admin"

    if is_admin:
        effective_user_id = _normalize_dashboard_user_id(user_id)
        cache_key = f"admin:{effective_user_id or 'all'}"
    else:
        effective_user_id = req_user.get("Id") if req_user else admin_user.get("id")
        effective_user_id = _normalize_dashboard_user_id(effective_user_id)
        cache_key = f"user:{effective_user_id or 'unknown'}"

    return cache_key, effective_user_id, is_admin


def _get_dashboard_cache_entry(cache_key: str):
    return _dashboard_cache.get(cache_key, {"data": None, "ts": 0})


def _get_dashboard_cached_data(cache_key: str, now: float = None):
    now = now or time.time()
    entry = _get_dashboard_cache_entry(cache_key)
    if entry.get("data") and (now - entry.get("ts", 0)) < _DASHBOARD_CACHE_TTL:
        return entry["data"]
    return None


def _set_dashboard_cache(cache_key: str, data: dict, user_id=None, ts: float = None):
    _dashboard_cache[cache_key] = {
        "data": data,
        "ts": ts or time.time(),
    }
    _dashboard_cache_user_ids[cache_key] = user_id


def _mark_dashboard_access(cache_key: str, now: float = None):
    _dashboard_last_access[cache_key] = now or time.time()


def _get_admin_user_id():
    try:
        res = media_api.get("/Users", timeout=5)
        if res.status_code == 200:
            users = res.json()
            for u in users:
                if u.get("Policy", {}).get("IsAdministrator"):
                    return u["Id"]
            if users:
                return users[0]["Id"]
    except Exception:
        pass
    return None


def _get_user_map_local():
    user_map = {}
    try:
        res = media_api.get("/Users", timeout=2)
        if res.status_code == 200:
            for u in res.json():
                user_map[u["Id"]] = u["Name"]
    except Exception:
        pass
    return user_map


async def _fetch_dashboard_core(user_id: str) -> dict:
    """核心仪表盘数据（播放统计、媒体库储量）- 快速"""
    try:
        where, params = build_stats_base_filter(user_id)
        plays = playback_store.query(f"SELECT COUNT(*) as c FROM PlaybackActivity {where}", params)[0]["c"]
        users = playback_store.query(
            f"SELECT COUNT(DISTINCT UserId) as c FROM PlaybackActivity {where} AND DateCreated > date('now', 'localtime', '-30 days')",
            params,
        )[0]["c"]
        dur = playback_store.query(f"SELECT SUM(PlayDuration) as c FROM PlaybackActivity {where}", params)[0]["c"] or 0

        lib = {"movie": 0, "series": 0, "episode": 0}
        try:
            res = media_api.get("/Items/Counts", timeout=3)
            if res.status_code == 200:
                d = res.json()
                lib = {"movie": d.get("MovieCount", 0), "series": d.get("SeriesCount", 0), "episode": d.get("EpisodeCount", 0)}
        except Exception:
            pass

        return {
            "total_plays": plays,
            "active_users": users,
            "total_duration": dur,
            "library": lib,
        }
    except Exception:
        return {"total_plays": 0, "active_users": 0, "total_duration": 0, "library": {}}


async def _fetch_users_list() -> list:
    """用户列表 - 快速"""
    try:
        res = media_api.get("/Users", timeout=3)
        if res.status_code == 200:
            hidden = get_hidden_users()
            return [
                {"UserId": u["Id"], "UserName": u["Name"], "IsHidden": u["Id"] in hidden}
                for u in res.json()
            ]
        logger.error(f"[用户列表] Emby API 错误: {res.status_code}")
        return []
    except Exception as e:
        logger.error(f"[用户列表] 获取失败: {e}")
        return []


async def _fetch_libraries() -> list:
    """媒体库列表 - 快速"""
    try:
        admin_id = _get_admin_user_id()
        if admin_id:
            res = media_api.get(f"/Users/{admin_id}/Views", timeout=5)
            if res.status_code == 200:
                return [
                    {
                        "Id": i.get("Id"),
                        "Name": i.get("Name"),
                        "CollectionType": i.get("CollectionType", "unknown"),
                        "ImageTag": i.get("ImageTags", {}).get("Primary", "")[:8] if i.get("ImageTags", {}).get("Primary") else "",
                    }
                    for i in res.json().get("Items", [])
                ]
            logger.error(f"[媒体库列表] Emby API 错误: {res.status_code}")
        return []
    except Exception as e:
        logger.error(f"[媒体库列表] 获取失败: {e}")
        return []


async def _fetch_top_users() -> list:
    """白金观影榜 - 快速（本地数据库）"""
    try:
        where_base, params_top = build_stats_base_filter("all")
        sql = (
            f"SELECT UserId, COUNT(*) as Plays, SUM(PlayDuration) as TotalTime FROM PlaybackActivity {where_base} "
            "GROUP BY UserId ORDER BY TotalTime DESC LIMIT 10"
        )
        res_top = playback_store.query(sql, params_top)
        user_map = _get_user_map_local()
        hidden = get_hidden_users()
        hidden_str = [str(h) for h in hidden]
        top_users = []
        for row in (res_top or []):
            if str(row["UserId"]) in hidden_str:
                continue
            u = dict(row)
            u["UserName"] = user_map.get(u["UserId"], f"User {str(u['UserId'])[:5]}")
            top_users.append(u)
            if len(top_users) >= 5:
                break
        return top_users
    except Exception as e:
        print(f"[Dashboard Init] Top users error: {e}")
        return []


async def _fetch_trend(user_id: str) -> dict:
    """趋势图数据 - 快速（本地数据库）"""
    try:
        where_trend, params_trend = build_stats_base_filter(user_id)
        sql_trend = (
            "SELECT substr(replace(DateCreated, 'T', ' '), 1, 10) as Label, "
            f"SUM(PlayDuration) as Duration FROM PlaybackActivity {where_trend} "
            "AND DateCreated > date('now', 'localtime', '-30 days') GROUP BY Label ORDER BY Label"
        )
        results_trend = playback_store.query(sql_trend, params_trend)
        trend_data = {}
        if results_trend:
            for r in results_trend:
                trend_data[r["Label"]] = int(r["Duration"] or 0)
        return trend_data
    except Exception:
        return {}


async def preload_dashboard_cache(silent: bool = False, cache_key: str = _DASHBOARD_PRELOAD_KEY, user_id=None):
    """
    后台预热仪表盘缓存
    在容器启动后自动执行，用户打开首页即可秒出数据
    """
    global _preload_started

    if not _preload_started:
        await asyncio.sleep(8)
        _preload_started = True

    if _dashboard_refresh_lock.locked():
        return False

    async with _dashboard_refresh_lock:
        try:
            if not silent:
                print("[🔥 预热] 开始预热仪表盘缓存...")

            effective_user_id = _normalize_dashboard_user_id(user_id)
            results = await asyncio.gather(
                asyncio.wait_for(_fetch_dashboard_core(effective_user_id), timeout=15),
                asyncio.wait_for(_fetch_users_list(), timeout=10),
                asyncio.wait_for(_fetch_libraries(), timeout=15),
                asyncio.wait_for(_fetch_top_users(), timeout=10),
                asyncio.wait_for(_fetch_trend(effective_user_id), timeout=10),
                return_exceptions=True,
            )

            dashboard, users, libraries, top_users, trend = results

            result_data = {
                "dashboard": dashboard if not isinstance(dashboard, Exception) else {"total_plays": 0, "active_users": 0, "total_duration": 0, "library": {}},
                "users": users if not isinstance(users, Exception) else [],
                "libraries": libraries if not isinstance(libraries, Exception) else [],
                "top_users": top_users if not isinstance(top_users, Exception) else [],
                "trend": trend if not isinstance(trend, Exception) else {},
            }

            _set_dashboard_cache(cache_key, result_data, effective_user_id)

            if not silent:
                print(f"[🔥 预热] 仪表盘缓存预热完成！媒体库: {len(result_data['libraries'])} 个, 用户: {len(result_data['users'])} 个")
            return True
        except Exception as e:
            if not silent:
                print(f"[🔥 预热] 预热失败: {e}")
            return False


async def start_dashboard_cache_refresh_loop():
    """
    后台定时刷新仪表盘缓存
    每分钟检查一次，只在近期有人访问且缓存过期时刷新
    """
    global _last_refresh_log_time

    try:
        while True:
            await asyncio.sleep(60)
            try:
                now = time.time()
                active_keys = [
                    key for key, last_access in list(_dashboard_last_access.items())
                    if now - last_access <= _DASHBOARD_ACTIVE_WINDOW
                ]
                for cache_key in active_keys:
                    entry = _get_dashboard_cache_entry(cache_key)
                    cache_age = now - entry.get("ts", 0) if entry.get("ts", 0) > 0 else 999
                    if cache_age >= _DASHBOARD_CACHE_TTL:
                        await preload_dashboard_cache(
                            silent=True,
                            cache_key=cache_key,
                            user_id=_dashboard_cache_user_ids.get(cache_key),
                        )
                        if now - _last_refresh_log_time >= 300:
                            _last_refresh_log_time = now
                            print("[🔥 缓存] 后台刷新完成，下次刷新: 60秒后")
            except Exception:
                pass
    except asyncio.CancelledError:
        raise


def start_dashboard_cache_tasks(preload_func=None, refresh_func=None) -> None:
    global _dashboard_cache_tasks_started, _dashboard_preload_task, _dashboard_refresh_task
    if _dashboard_cache_tasks_started:
        return
    preload_func = preload_func or preload_dashboard_cache
    refresh_func = refresh_func or start_dashboard_cache_refresh_loop
    _dashboard_cache_tasks_started = True
    _dashboard_preload_task = asyncio.create_task(preload_func())
    _dashboard_refresh_task = asyncio.create_task(refresh_func())


def stop_dashboard_cache_tasks() -> None:
    global _dashboard_cache_tasks_started, _dashboard_preload_task, _dashboard_refresh_task
    for task in (_dashboard_preload_task, _dashboard_refresh_task):
        if task and not task.done():
            task.cancel()
    _dashboard_preload_task = None
    _dashboard_refresh_task = None
    _dashboard_cache_tasks_started = False
