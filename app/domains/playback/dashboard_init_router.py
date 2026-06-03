import asyncio
import copy
import time
from typing import Optional

from fastapi import APIRouter, Request

from app.domains.playback import dashboard_cache_service
from app.domains.users import public_service as user_service


router = APIRouter()

_user_service_provider = lambda: user_service
_get_dashboard_context_provider = lambda: dashboard_cache_service._get_dashboard_context
_mark_dashboard_access_provider = lambda: dashboard_cache_service._mark_dashboard_access
_get_dashboard_cached_data_provider = lambda: dashboard_cache_service._get_dashboard_cached_data
_fetch_dashboard_core_provider = lambda: dashboard_cache_service._fetch_dashboard_core
_fetch_users_list_provider = lambda: dashboard_cache_service._fetch_users_list
_fetch_libraries_provider = lambda: dashboard_cache_service._fetch_libraries
_fetch_top_users_provider = lambda: dashboard_cache_service._fetch_top_users
_fetch_trend_provider = lambda: dashboard_cache_service._fetch_trend
_get_dashboard_cache_entry_provider = lambda: dashboard_cache_service._get_dashboard_cache_entry
_set_dashboard_cache_provider = lambda: dashboard_cache_service._set_dashboard_cache
_asyncio_provider = lambda: asyncio
_copy_provider = lambda: copy
_time_provider = lambda: time
_print_provider = lambda: print


def set_dependency_providers(
    *,
    user_service_provider=None,
    get_dashboard_context_provider=None,
    mark_dashboard_access_provider=None,
    get_dashboard_cached_data_provider=None,
    fetch_dashboard_core_provider=None,
    fetch_users_list_provider=None,
    fetch_libraries_provider=None,
    fetch_top_users_provider=None,
    fetch_trend_provider=None,
    get_dashboard_cache_entry_provider=None,
    set_dashboard_cache_provider=None,
    asyncio_provider=None,
    copy_provider=None,
    time_provider=None,
    print_provider=None,
):
    global _user_service_provider
    global _get_dashboard_context_provider
    global _mark_dashboard_access_provider
    global _get_dashboard_cached_data_provider
    global _fetch_dashboard_core_provider
    global _fetch_users_list_provider
    global _fetch_libraries_provider
    global _fetch_top_users_provider
    global _fetch_trend_provider
    global _get_dashboard_cache_entry_provider
    global _set_dashboard_cache_provider
    global _asyncio_provider
    global _copy_provider
    global _time_provider
    global _print_provider

    if user_service_provider is not None:
        _user_service_provider = user_service_provider
    if get_dashboard_context_provider is not None:
        _get_dashboard_context_provider = get_dashboard_context_provider
    if mark_dashboard_access_provider is not None:
        _mark_dashboard_access_provider = mark_dashboard_access_provider
    if get_dashboard_cached_data_provider is not None:
        _get_dashboard_cached_data_provider = get_dashboard_cached_data_provider
    if fetch_dashboard_core_provider is not None:
        _fetch_dashboard_core_provider = fetch_dashboard_core_provider
    if fetch_users_list_provider is not None:
        _fetch_users_list_provider = fetch_users_list_provider
    if fetch_libraries_provider is not None:
        _fetch_libraries_provider = fetch_libraries_provider
    if fetch_top_users_provider is not None:
        _fetch_top_users_provider = fetch_top_users_provider
    if fetch_trend_provider is not None:
        _fetch_trend_provider = fetch_trend_provider
    if get_dashboard_cache_entry_provider is not None:
        _get_dashboard_cache_entry_provider = get_dashboard_cache_entry_provider
    if set_dashboard_cache_provider is not None:
        _set_dashboard_cache_provider = set_dashboard_cache_provider
    if asyncio_provider is not None:
        _asyncio_provider = asyncio_provider
    if copy_provider is not None:
        _copy_provider = copy_provider
    if time_provider is not None:
        _time_provider = time_provider
    if print_provider is not None:
        _print_provider = print_provider


@router.get("/api/dashboard/init")
async def api_dashboard_init(request: Request, user_id: Optional[str] = None):
    # 🔒 管理后台首屏聚合接口，仅管理员可访问
    if not _user_service_provider().is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    """
    仪表盘首屏聚合接口 - 核心数据快速返回
    """
    cache_key, effective_user_id, _is_admin = _get_dashboard_context_provider()(request, user_id)

    def _strip_user_id(data: dict) -> dict:
        """非管理员返回时剥离 top_users 中的原始 UserId"""
        if _is_admin:
            return data
        d = _copy_provider().deepcopy(data)
        for u in d.get("top_users", []):
            u.pop("UserId", None)
        return d

    now = _time_provider().time()
    _mark_dashboard_access_provider()(cache_key, now)

    # 🔥 检查内存缓存（30秒内直接返回）
    cached_data = _get_dashboard_cached_data_provider()(cache_key, now)
    if cached_data:
        return {
            "status": "success",
            "data": _strip_user_id(cached_data),
            "cached": True
        }

    async_lib = _asyncio_provider()

    # 🔥 并发执行核心数据（快速）
    try:
        results = await async_lib.gather(
            async_lib.wait_for(_fetch_dashboard_core_provider()(effective_user_id), timeout=5),
            async_lib.wait_for(_fetch_users_list_provider()(), timeout=3),
            async_lib.wait_for(_fetch_libraries_provider()(), timeout=5),
            async_lib.wait_for(_fetch_top_users_provider()(), timeout=3),
            async_lib.wait_for(_fetch_trend_provider()(effective_user_id), timeout=3),
            return_exceptions=True
        )

        dashboard, users, libraries, top_users, trend = results
    except async_lib.TimeoutError as e:
        _print_provider()(f"[Dashboard Init] 请求超时: {e}")
        stale_entry = _get_dashboard_cache_entry_provider()(cache_key)
        if stale_entry.get("data"):
            return {"status": "success", "data": _strip_user_id(stale_entry["data"]), "cached": True, "timeout": True}
        dashboard = {"total_plays": 0, "active_users": 0, "total_duration": 0, "library": {}}
        users = []
        libraries = []
        top_users = []
        trend = {}

    result_data = {
        "dashboard": dashboard if not isinstance(dashboard, Exception) else {"total_plays": 0, "active_users": 0, "total_duration": 0, "library": {}},
        "users": users if not isinstance(users, Exception) else [],
        "libraries": libraries if not isinstance(libraries, Exception) else [],
        "top_users": top_users if not isinstance(top_users, Exception) else [],
        "trend": trend if not isinstance(trend, Exception) else {}
    }

    # 🔥 更新内存缓存
    _set_dashboard_cache_provider()(cache_key, result_data, effective_user_id, now)

    return {
        "status": "success",
        "data": _strip_user_id(result_data),
        "cached": False
    }
