from fastapi import APIRouter, Request

from app.core.security_utils import safe_error_message
from app.domains.users.auth import is_admin_user
from app.infra.clients.media_server_client import media_api


router = APIRouter()

_media_api_provider = lambda: media_api
_is_admin_user_provider = lambda: is_admin_user
_safe_error_message_provider = lambda: safe_error_message


def set_dependency_providers(*, media_api_provider=None, is_admin_user_provider=None, safe_error_message_provider=None):
    global _media_api_provider
    global _is_admin_user_provider
    global _safe_error_message_provider

    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if is_admin_user_provider is not None:
        _is_admin_user_provider = is_admin_user_provider
    if safe_error_message_provider is not None:
        _safe_error_message_provider = safe_error_message_provider


@router.get("/api/manage/libraries")
def api_get_libraries(request: Request):
    if not _is_admin_user_provider()(request):
        return {"status": "error", "message": "需要管理员权限"}
    try:
        res = _media_api_provider().get("/Library/VirtualFolders", timeout=5)
        if res.status_code == 200:
            libs = [{"Id": item["Guid"], "Name": item["Name"]} for item in res.json() if "Guid" in item]
            return {"status": "success", "data": libs}
        return {"status": "error", "message": "媒体服务器 API 返回异常"}
    except Exception as e:
        return {"status": "error", "message": _safe_error_message_provider()(e)}
