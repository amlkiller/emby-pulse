from typing import Optional

from fastapi import APIRouter, Request

from app.domains.playback.stats_helpers import check_login, get_cached_stats, set_cached_stats
from app.domains.playback.stats_queries import build_stats_base_filter
from app.infra.clients.media_server_client import media_api
from app.infra.db.playback_store import playback_store


router = APIRouter()

_check_login_provider = lambda: check_login
_build_stats_base_filter_provider = lambda: build_stats_base_filter
_playback_store_provider = lambda: playback_store
_get_cached_stats_provider = lambda: get_cached_stats
_set_cached_stats_provider = lambda: set_cached_stats
_media_api_provider = lambda: media_api


def set_dependency_providers(
    *,
    check_login_provider=None,
    build_stats_base_filter_provider=None,
    playback_store_provider=None,
    get_cached_stats_provider=None,
    set_cached_stats_provider=None,
    media_api_provider=None,
):
    global _check_login_provider
    global _build_stats_base_filter_provider
    global _playback_store_provider
    global _get_cached_stats_provider
    global _set_cached_stats_provider
    global _media_api_provider

    if check_login_provider is not None:
        _check_login_provider = check_login_provider
    if build_stats_base_filter_provider is not None:
        _build_stats_base_filter_provider = build_stats_base_filter_provider
    if playback_store_provider is not None:
        _playback_store_provider = playback_store_provider
    if get_cached_stats_provider is not None:
        _get_cached_stats_provider = get_cached_stats_provider
    if set_cached_stats_provider is not None:
        _set_cached_stats_provider = set_cached_stats_provider
    if media_api_provider is not None:
        _media_api_provider = media_api_provider


@router.get("/api/stats/dashboard")
def api_dashboard(request: Request, user_id: Optional[str] = None):
    # 🔒 安全检查：必须登录
    if not _check_login_provider()(request):
        return {"status": "error", "message": "请先登录"}

    # 🔒 权限检查：普通用户只能查看自己的数据
    admin_user = request.session.get("user", {})
    req_user = request.session.get("req_user", {})
    is_admin = admin_user.get("auth_type") == "emby" or admin_user.get("role") == "admin"

    if not is_admin:
        if req_user:
            user_id = req_user.get("Id")
        elif admin_user:
            user_id = admin_user.get("id")

    # 🔥 尝试使用缓存（仅全局统计，不缓存特定用户）
    cache_key = f"dashboard_{user_id or 'all'}"
    cached = _get_cached_stats_provider()(cache_key)
    if cached:
        return cached

    try:
        where, params = _build_stats_base_filter_provider()(user_id)
        plays = _playback_store_provider().query(f"SELECT COUNT(*) as c FROM PlaybackActivity {where}", params)[0]['c']
        # 🔥 时区修复
        users = _playback_store_provider().query(f"SELECT COUNT(DISTINCT UserId) as c FROM PlaybackActivity {where} AND DateCreated > date('now', 'localtime', '-30 days')", params)[0]['c']
        dur = _playback_store_provider().query(f"SELECT SUM(PlayDuration) as c FROM PlaybackActivity {where}", params)[0]['c'] or 0
        base = {"total_plays": plays, "active_users": users, "total_duration": dur}
        lib = {"movie": 0, "series": 0, "episode": 0}

        try:
            # 🚀 替换为 media_api
            res = _media_api_provider().get("/Items/Counts", timeout=5)
            if res.status_code == 200:
                d = res.json()
                lib = {"movie": d.get("MovieCount", 0), "series": d.get("SeriesCount", 0), "episode": d.get("EpisodeCount", 0)}
        except Exception: pass

        result = {"status": "success", "data": {**base, "library": lib}}
        # 🔥 缓存结果
        _set_cached_stats_provider()(cache_key, result)
        return result
    except: return {"status": "error", "data": {"total_plays":0, "library": {}}}
