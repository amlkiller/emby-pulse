from fastapi import APIRouter, Request

from app.core.security_utils import safe_error_message
from app.domains.users import public_service as user_service
from app.domains.users import user_dao
from app.domains.users.auth import is_admin_user
from app.domains.users.update_router import UserUpdateModelEx
from app.infra.clients.media_server_client import media_api


router = APIRouter()


_media_api_provider = lambda: media_api
_user_dao_provider = lambda: user_dao
_user_service_provider = lambda: user_service
_is_admin_user_provider = lambda: is_admin_user
_safe_error_message_provider = lambda: safe_error_message


def set_dependency_providers(
    *,
    media_api_provider=None,
    user_dao_provider=None,
    user_service_provider=None,
    is_admin_user_provider=None,
    safe_error_message_provider=None,
):
    global _media_api_provider
    global _user_dao_provider
    global _user_service_provider
    global _is_admin_user_provider
    global _safe_error_message_provider

    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if user_dao_provider is not None:
        _user_dao_provider = user_dao_provider
    if user_service_provider is not None:
        _user_service_provider = user_service_provider
    if is_admin_user_provider is not None:
        _is_admin_user_provider = is_admin_user_provider
    if safe_error_message_provider is not None:
        _safe_error_message_provider = safe_error_message_provider


@router.post("/api/manage/user/library")
def api_manage_user_library(data: UserUpdateModelEx, request: Request):
    """单独保存媒体库权限"""
    # 🔒 安全检查：必须管理员
    if not _is_admin_user_provider()(request): return {"status": "error", "message": "需要管理员权限"}
    # 🔒 Emby 不可用时拒绝，避免本地/远端权限错位
    if not _media_api_provider().health_check():
        return {"status": "error", "message": "Emby 服务不可用，请稍后重试"}
    _user_service_provider().invalidate_emby_users_cache()
    try:
        media = _media_api_provider()
        dao = _user_dao_provider()

        # 获取用户当前 Policy
        p_res = media.get(f"/Users/{data.user_id}")
        if p_res.status_code != 200:
            return {"status": "error", "message": "用户不存在"}

        p = p_res.json().get('Policy', {})

        # 获取旧的媒体库权限用于对比
        old_enable_all = p.get('EnableAllFolders', True)
        old_enabled_folders = set(p.get('EnabledFolders', []))

        # 设置新的媒体库权限
        new_enable_all = bool(data.enable_all_folders)
        new_enabled_folders = set([str(x) for x in data.enabled_folders]) if not new_enable_all and data.enabled_folders is not None else set()

        # 检测是否有变化
        library_changed = (old_enable_all != new_enable_all) or (old_enabled_folders != new_enabled_folders)

        if library_changed:
            p['EnableAllFolders'] = new_enable_all
            p['EnabledFolders'] = list(new_enabled_folders) if not new_enable_all else []

            # 同步更新 admin_enabled_folders，但保留用户的 hidden_libraries
            try:
                final_enabled = dao.sync_user_library_permissions(data.user_id, new_enable_all, new_enabled_folders)
                if final_enabled is not None:
                    p['EnabledFolders'] = final_enabled
            except Exception: pass

            # 更新 Emby Policy
            media.post(f"/Users/{data.user_id}/Policy", json=p)

        return {"status": "success", "message": "媒体库权限已保存"}
    except Exception as e:
        return {"status": "error", "message": _safe_error_message_provider()(e)}
