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


@router.get("/api/stats/monthly_stats")
def api_monthly_stats(request: Request, user_id: Optional[str] = None):
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
        where_base, params = _build_stats_base_filter_provider()(user_id)
        # 🔥 时区修复
        where = where_base + " AND DateCreated > date('now', 'localtime', '-12 months')"
        sql = f"SELECT substr(replace(DateCreated, 'T', ' '), 1, 7) as Month, SUM(PlayDuration) as Duration FROM PlaybackActivity {where} GROUP BY Month ORDER BY Month"
        results = _playback_store_provider().query(sql, params); data = {}
        if results:
            for r in results: data[r['Month']] = int(r['Duration'] or 0)
        return {"status": "success", "data": data}
    except: return {"status": "error", "data": {}}
