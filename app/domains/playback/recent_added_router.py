from fastapi import APIRouter, Request

from app.domains.playback.stats_helpers import check_login


router = APIRouter()

_check_login_provider = lambda: check_login
_get_added_stats_sync_provider = None


def set_dependency_providers(
    *,
    check_login_provider=None,
    get_added_stats_sync_provider=None,
):
    global _check_login_provider
    global _get_added_stats_sync_provider

    if check_login_provider is not None:
        _check_login_provider = check_login_provider
    if get_added_stats_sync_provider is not None:
        _get_added_stats_sync_provider = get_added_stats_sync_provider


def _get_added_stats_sync():
    if _get_added_stats_sync_provider is None:
        raise RuntimeError("recent_added stats provider is not configured")
    return _get_added_stats_sync_provider()()


@router.get("/api/stats/recent_added")
def api_recent_added(request: Request = None):
    # 🔒 安全检查（内部调用时 request 为 None，跳过检查）
    if request and not _check_login_provider()(request):
        return {"status": "error", "message": "请先登录"}
    """独立API入口，复用 _get_added_stats_sync 的逻辑"""
    result = _get_added_stats_sync()
    return {"status": "success", "data": result}
