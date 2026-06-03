from fastapi import APIRouter, Request

from app.core.security_utils import safe_error_message
from app.domains.playback.stats_helpers import get_admin_user_id
from app.domains.users import public_service as user_service
from app.infra.clients.media_server_client import media_api


router = APIRouter()

_user_service_provider = lambda: user_service
_media_api_provider = lambda: media_api
_get_admin_user_id_provider = lambda: get_admin_user_id
_safe_error_message_provider = lambda: safe_error_message


def set_dependency_providers(
    *,
    user_service_provider=None,
    media_api_provider=None,
    get_admin_user_id_provider=None,
    safe_error_message_provider=None,
):
    global _user_service_provider
    global _media_api_provider
    global _get_admin_user_id_provider
    global _safe_error_message_provider

    if user_service_provider is not None:
        _user_service_provider = user_service_provider
    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if get_admin_user_id_provider is not None:
        _get_admin_user_id_provider = get_admin_user_id_provider
    if safe_error_message_provider is not None:
        _safe_error_message_provider = safe_error_message_provider


@router.get("/api/stats/libraries")
def api_get_libraries(request: Request):
    """获取媒体库列表（管理员显示所有媒体库）"""
    # 🔒 安全检查：必须管理员
    if not _user_service_provider().is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    try:
        # 🔥 管理员登录后显示所有媒体库（使用 /Library/VirtualFolders）
        lib_res = _media_api_provider().get("/Library/VirtualFolders", timeout=10)
        if lib_res.status_code != 200:
            return {"status": "error", "message": "获取媒体库失败"}

        libraries = []
        for lib in lib_res.json():
            item_id = lib.get("ItemId") or lib.get("Guid") or lib.get("Id")

            # 获取图片标签
            image_tag = ""
            if item_id:
                try:
                    admin_id = _get_admin_user_id_provider()()
                    if admin_id:
                        item_res = _media_api_provider().get(f"/Users/{admin_id}/Items/{item_id}", timeout=3)
                        if item_res.status_code == 200:
                            item_data = item_res.json()
                            image_tag = item_data.get("ImageTags", {}).get("Primary", "")[:8] if item_data.get("ImageTags", {}).get("Primary") else ""
                except:
                    pass

            lib_info = {
                "Id": item_id,
                "Name": lib.get("Name", "未命名"),
                "CollectionType": lib.get("CollectionType", "unknown"),
                "ImageTag": image_tag
            }
            libraries.append(lib_info)

        return {"status": "success", "data": libraries}
    except Exception as e:
        return {"status": "error", "message": _safe_error_message_provider()(e)}
