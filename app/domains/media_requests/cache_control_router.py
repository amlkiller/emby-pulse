from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.domains.media_requests import community_cache_service
from app.domains.media_requests.media_request_dao import ensure_media_request_schema
from app.domains.users import public_service as user_service


router = APIRouter()

_community_cache_service_provider = lambda: community_cache_service
_refresh_community_cache_provider = lambda: community_cache_service._refresh_community_cache
_invalidate_cache_provider = lambda: community_cache_service._invalidate_cache
_sync_task_state_provider = lambda: (lambda: None)
_ensure_schema_provider = lambda: ensure_media_request_schema
_user_service_provider = lambda: user_service


def set_dependency_providers(
    *,
    community_cache_service_provider=None,
    refresh_community_cache_provider=None,
    invalidate_cache_provider=None,
    sync_task_state_provider=None,
    ensure_schema_provider=None,
    user_service_provider=None,
):
    global _community_cache_service_provider
    global _refresh_community_cache_provider
    global _invalidate_cache_provider
    global _sync_task_state_provider
    global _ensure_schema_provider
    global _user_service_provider

    if community_cache_service_provider is not None:
        _community_cache_service_provider = community_cache_service_provider
    if refresh_community_cache_provider is not None:
        _refresh_community_cache_provider = refresh_community_cache_provider
    if invalidate_cache_provider is not None:
        _invalidate_cache_provider = invalidate_cache_provider
    if sync_task_state_provider is not None:
        _sync_task_state_provider = sync_task_state_provider
    if ensure_schema_provider is not None:
        _ensure_schema_provider = ensure_schema_provider
    if user_service_provider is not None:
        _user_service_provider = user_service_provider


def start_community_cache_refresh_loop() -> None:
    _community_cache_service_provider().start_community_cache_refresh_loop(
        refresh_func=_refresh_community_cache_provider()
    )
    _sync_task_state_provider()()


def stop_community_cache_refresh_loop() -> None:
    _community_cache_service_provider().stop_community_cache_refresh_loop()
    _sync_task_state_provider()()


def start_media_request_services() -> None:
    _ensure_schema_provider()()
    start_community_cache_refresh_loop()


@router.post("/api/requests/refresh_cache")
def refresh_community_cache_api(request: Request):
    """手动刷新用户社区首页缓存（管理员接口）"""
    if not request.session.get("user"):
        return JSONResponse(status_code=401, content={"status": "error", "message": "未登录"})
    if not _user_service_provider().is_admin_user(request):
        return JSONResponse(status_code=403, content={"status": "error", "message": "需要管理员权限"})

    # 后台执行刷新
    _refresh_community_cache_provider()()
    return {"status": "success", "message": "缓存已刷新"}


@router.post("/api/requests/clear_cache")
def clear_community_cache_api(request: Request):
    """清除用户社区首页缓存（管理员接口）"""
    if not request.session.get("user"):
        return JSONResponse(status_code=401, content={"status": "error", "message": "未登录"})
    if not _user_service_provider().is_admin_user(request):
        return JSONResponse(status_code=403, content={"status": "error", "message": "需要管理员权限"})

    _invalidate_cache_provider()()
    return {"status": "success", "message": "缓存已清除"}
