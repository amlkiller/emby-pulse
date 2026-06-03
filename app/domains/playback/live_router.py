from fastapi import APIRouter, Request

from app.domains.users import public_service as user_service
from app.infra.clients.media_server_client import media_api


router = APIRouter()

_user_service_provider = lambda: user_service
_media_api_provider = lambda: media_api


def set_dependency_providers(
    *,
    user_service_provider=None,
    media_api_provider=None,
):
    global _user_service_provider
    global _media_api_provider

    if user_service_provider is not None:
        _user_service_provider = user_service_provider
    if media_api_provider is not None:
        _media_api_provider = media_api_provider


@router.get("/api/stats/live")
def api_live_sessions(request: Request):
    # 🔒 安全检查：必须管理员
    if not _user_service_provider().is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    try:
        # 🚀 替换为 media_api
        res = _media_api_provider().get("/Sessions", timeout=5)
        if res.status_code == 200: return {"status": "success", "data": [s for s in res.json() if s.get("NowPlayingItem")]}
    except Exception: pass
    return {"status": "success", "data": []}


@router.get("/api/live")
def api_live_sessions_legacy(request: Request):
    # 🔒 安全检查：必须管理员
    if not _user_service_provider().is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    return api_live_sessions(request)
