from typing import Optional

from fastapi import APIRouter, Request

from app.domains.playback.stats_helpers import check_login
from app.domains.playback.stats_queries import build_stats_base_filter
from app.infra.db.playback_store import playback_store


router = APIRouter()

_check_login_provider = lambda: check_login
_build_stats_base_filter_provider = lambda: build_stats_base_filter
_playback_store_provider = lambda: playback_store


def set_dependency_providers(
    *,
    check_login_provider=None,
    build_stats_base_filter_provider=None,
    playback_store_provider=None,
):
    global _check_login_provider
    global _build_stats_base_filter_provider
    global _playback_store_provider

    if check_login_provider is not None:
        _check_login_provider = check_login_provider
    if build_stats_base_filter_provider is not None:
        _build_stats_base_filter_provider = build_stats_base_filter_provider
    if playback_store_provider is not None:
        _playback_store_provider = playback_store_provider


@router.get("/api/stats/trend")
@router.get("/api/stats/chart")
def api_chart_stats(request: Request, user_id: Optional[str] = None, dimension: str = 'day'):
    # 🔒 安全检查
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

    try:
        where, params = _build_stats_base_filter_provider()(user_id)
        # 🔥 时区修复
        if dimension == 'week':
            sql = f"SELECT strftime('%Y-%W', substr(replace(DateCreated, 'T', ' '), 1, 19)) as Label, SUM(PlayDuration) as Duration FROM PlaybackActivity {where} AND DateCreated > date('now', 'localtime', '-120 days') GROUP BY Label ORDER BY Label"
        elif dimension == 'month':
            sql = f"SELECT substr(replace(DateCreated, 'T', ' '), 1, 7) as Label, SUM(PlayDuration) as Duration FROM PlaybackActivity {where} AND DateCreated > date('now', 'localtime', '-365 days') GROUP BY Label ORDER BY Label"
        else:
            sql = f"SELECT substr(replace(DateCreated, 'T', ' '), 1, 10) as Label, SUM(PlayDuration) as Duration FROM PlaybackActivity {where} AND DateCreated > date('now', 'localtime', '-30 days') GROUP BY Label ORDER BY Label"

        results = _playback_store_provider().query(sql, params)
        data = {}
        if results:
            for r in results: data[r['Label']] = int(r['Duration'] or 0)
        return {"status": "success", "data": data}
    except: return {"status": "error", "data": {}}
