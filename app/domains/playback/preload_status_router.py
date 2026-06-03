import time

from fastapi import APIRouter, Request

from app.domains.playback import dashboard_cache_service
from app.domains.users import public_service as user_service


router = APIRouter()

_user_service_provider = lambda: user_service
_get_dashboard_cache_entry_provider = lambda: dashboard_cache_service._get_dashboard_cache_entry
_dashboard_preload_key_provider = lambda: dashboard_cache_service._DASHBOARD_PRELOAD_KEY
_dashboard_cache_ttl_provider = lambda: dashboard_cache_service._DASHBOARD_CACHE_TTL
_time_provider = lambda: time


def set_dependency_providers(
    *,
    user_service_provider=None,
    get_dashboard_cache_entry_provider=None,
    dashboard_preload_key_provider=None,
    dashboard_cache_ttl_provider=None,
    time_provider=None,
):
    global _user_service_provider
    global _get_dashboard_cache_entry_provider
    global _dashboard_preload_key_provider
    global _dashboard_cache_ttl_provider
    global _time_provider

    if user_service_provider is not None:
        _user_service_provider = user_service_provider
    if get_dashboard_cache_entry_provider is not None:
        _get_dashboard_cache_entry_provider = get_dashboard_cache_entry_provider
    if dashboard_preload_key_provider is not None:
        _dashboard_preload_key_provider = dashboard_preload_key_provider
    if dashboard_cache_ttl_provider is not None:
        _dashboard_cache_ttl_provider = dashboard_cache_ttl_provider
    if time_provider is not None:
        _time_provider = time_provider


@router.get("/api/dashboard/preload_status")
async def api_preload_status(request: Request):
    """
    获取缓存预热状态
    前端可以据此判断是否需要等待
    """
    # 🔒 管理后台聚合状态，仅管理员可访问
    if not _user_service_provider().is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    entry = _get_dashboard_cache_entry_provider()(_dashboard_preload_key_provider())
    data = entry.get("data")
    ts = entry.get("ts", 0)
    return {
        "status": "success",
        "data": {
            "cached": data is not None,
            "cache_age": round(_time_provider().time() - ts) if ts > 0 else 0,
            "cache_ttl": _dashboard_cache_ttl_provider(),
            "libraries_count": len(data.get("libraries", [])) if data else 0,
            "users_count": len(data.get("users", [])) if data else 0
        }
    }
