from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from app.infra.db import audit_dao
from app.domains.system import invitation_dao
from app.domains.users import user_dao
from app.domains.users import user_bot_dao
from app.domains.notifications import notify_admin
from app.domains.users.audit_log_router import (
    api_clear_audit_logs,
    api_delete_audit_log,
    api_get_audit_logs,
    api_get_audit_stats,
    router as audit_log_router,
)
from app.domains.users.avatar_router import (
    api_update_user_image,
    api_user_self_avatar,
    get_user_avatar,
    router as avatar_router,
    set_dependency_providers as set_avatar_dependency_providers,
)
from app.domains.users.batch_router import (
    BatchActionModelLocal,
    api_manage_users_batch,
    router as batch_router,
    set_dependency_providers as set_batch_dependency_providers,
)
from app.domains.users.delete_verification_router import (
    APP_START_TIME,
    PasswordVerifyModel,
    admin_router as delete_verification_admin_router,
    api_check_delete_verified,
    api_get_admin_list,
    api_verify_delete_password,
    get_emby_admin_users,
    router as delete_verification_router,
    set_app_start_time_provider,
    verify_emby_admin_password,
)
from app.domains.users.delete_router import (
    api_manage_user_delete,
    router as delete_router,
    set_dependency_providers as set_delete_dependency_providers,
)
from app.domains.users.invitation_router import (
    InviteBatchModelLocal,
    InviteGenModelLocal,
    api_export_invites,
    api_gen_invite,
    api_get_invites,
    api_manage_invites_batch,
    router as invitation_router,
    set_dependency_providers as set_invitation_dependency_providers,
)
from app.domains.users.library_visibility_router import (
    HiddenLibrariesModel,
    api_get_user_libraries,
    api_update_hidden_libraries,
    router as library_visibility_router,
    set_dependency_providers as set_library_visibility_dependency_providers,
)
from app.domains.users.library_update_router import (
    api_manage_user_library,
    router as library_update_router,
    set_dependency_providers as set_library_update_dependency_providers,
)
from app.domains.users.libraries_router import (
    api_get_libraries,
    router as libraries_router,
    set_dependency_providers as set_libraries_dependency_providers,
)
from app.domains.users.manage_list_router import (
    api_manage_users,
    check_expired_users,
    router as manage_list_router,
    set_dependency_providers as set_manage_list_dependency_providers,
)
from app.domains.users.list_router import (
    api_get_users,
    router as list_router,
)
from app.domains.users.new_user_router import (
    NewUserModelEx,
    api_manage_user_new,
    router as new_user_router,
    set_dependency_providers as set_new_user_dependency_providers,
)
from app.domains.users.pin_router import (
    PinUserModel,
    api_pin_user,
    router as pin_router,
    set_dependency_providers as set_pin_dependency_providers,
)
from app.domains.users.request_permission_router import (
    UserReqPermissionModel,
    api_get_user_req_permission,
    api_update_user_req_permission,
    router as request_permission_router,
)
from app.domains.users.self_password_router import (
    UserPasswordChangeModel,
    api_user_self_password,
    router as self_password_router,
    set_dependency_providers as set_self_password_dependency_providers,
)
from app.domains.users.single_user_router import (
    api_get_single_user,
    router as single_user_router,
    set_dependency_providers as set_single_user_dependency_providers,
)
from app.domains.users.tag_router import (
    TAG_COLORS,
    TagCreateModel,
    UserTagsUpdateModel,
    api_create_tag,
    api_delete_tag,
    api_delete_tag_by_name,
    api_get_tags,
    api_get_user_tags,
    api_update_user_tags,
    router as tag_router,
)
from app.domains.users.template_router import (
    api_get_default_template,
    api_set_default_template,
    router as template_router,
)
from app.domains.users.update_router import (
    UserUpdateModelEx,
    api_manage_user_update,
    router as update_router,
    set_dependency_providers as set_update_dependency_providers,
)
from app.infra.clients.media_server_client import media_api
from app.infra.clients.network_client import network_client
from app.infra.config.media_server_settings import get_media_server_public_host
from app.infra.config.request_portal_settings import get_user_portal_url
from app.infra.config.user_bot_settings import get_default_user_template_id
from app.domains.users import public_service as user_service

from app.domains.users.auth import is_admin_user  # 🔒 引入管理员权限检查
from app.core.security import validate_password_strength  # 🔒 统一密码强度校验
from app.utils.image_validator import validate_image_bytes  # 🔒 头像强校验
import datetime
import logging
from app.core.security_utils import safe_error_message
from app.core.rate_limiter import get_client_ip

router = APIRouter()
set_app_start_time_provider(lambda: APP_START_TIME)
set_invitation_dependency_providers(
    is_admin_user_provider=lambda: is_admin_user,
    invitation_dao_provider=lambda: invitation_dao,
    portal_url_provider=lambda: get_user_portal_url,
    client_ip_provider=lambda: get_client_ip,
    audit_log_provider=lambda: add_audit_log,
)
set_library_visibility_dependency_providers(
    media_api_provider=lambda: media_api,
    user_dao_provider=lambda: user_dao,
    logger_provider=lambda: logging,
)
set_library_update_dependency_providers(
    media_api_provider=lambda: media_api,
    user_dao_provider=lambda: user_dao,
    user_service_provider=lambda: user_service,
    is_admin_user_provider=lambda: is_admin_user,
    safe_error_message_provider=lambda: safe_error_message,
)
set_libraries_dependency_providers(
    media_api_provider=lambda: media_api,
    is_admin_user_provider=lambda: is_admin_user,
    safe_error_message_provider=lambda: safe_error_message,
)
set_manage_list_dependency_providers(
    media_api_provider=lambda: media_api,
    user_dao_provider=lambda: user_dao,
    user_bot_dao_provider=lambda: user_bot_dao,
    user_service_provider=lambda: user_service,
    is_admin_user_provider=lambda: is_admin_user,
    public_host_provider=lambda: get_media_server_public_host(),
    safe_error_message_provider=lambda: safe_error_message,
    datetime_provider=lambda: datetime,
    check_expired_users_provider=lambda: check_expired_users,
)
set_single_user_dependency_providers(
    media_api_provider=lambda: media_api,
    user_dao_provider=lambda: user_dao,
    is_admin_user_provider=lambda: is_admin_user,
)
set_delete_dependency_providers(
    media_api_provider=lambda: media_api,
    user_dao_provider=lambda: user_dao,
    user_service_provider=lambda: user_service,
    is_admin_user_provider=lambda: is_admin_user,
    notify_admin_provider=lambda: notify_admin,
    safe_error_message_provider=lambda: safe_error_message,
    client_ip_provider=lambda: get_client_ip,
    audit_log_provider=lambda: add_audit_log,
    app_start_time_provider=lambda: APP_START_TIME,
    now_provider=lambda: datetime.datetime.now(),
)
set_new_user_dependency_providers(
    media_api_provider=lambda: media_api,
    user_dao_provider=lambda: user_dao,
    user_service_provider=lambda: user_service,
    is_admin_user_provider=lambda: is_admin_user,
    default_template_id_provider=lambda: get_default_user_template_id(),
    clone_policy_provider=lambda: clone_policy,
    safe_error_message_provider=lambda: safe_error_message,
    client_ip_provider=lambda: get_client_ip,
    audit_log_provider=lambda: add_audit_log,
    now_provider=lambda: datetime.datetime.now().isoformat(),
)
set_batch_dependency_providers(
    media_api_provider=lambda: media_api,
    user_dao_provider=lambda: user_dao,
    is_admin_user_provider=lambda: is_admin_user,
    verify_admin_password_provider=lambda: verify_emby_admin_password,
    clone_policy_provider=lambda: clone_policy,
    safe_error_message_provider=lambda: safe_error_message,
    client_ip_provider=lambda: get_client_ip,
    audit_log_provider=lambda: add_audit_log,
    datetime_provider=lambda: datetime,
)
set_update_dependency_providers(
    media_api_provider=lambda: media_api,
    user_dao_provider=lambda: user_dao,
    user_service_provider=lambda: user_service,
    is_admin_user_provider=lambda: is_admin_user,
    clone_policy_provider=lambda: clone_policy,
    safe_error_message_provider=lambda: safe_error_message,
    client_ip_provider=lambda: get_client_ip,
    audit_log_provider=lambda: add_audit_log,
    datetime_provider=lambda: datetime,
)
set_avatar_dependency_providers(
    media_api_provider=lambda: media_api,
    network_client_provider=lambda: network_client,
    is_admin_user_provider=lambda: is_admin_user,
    validate_image_bytes_provider=lambda: validate_image_bytes,
    safe_error_message_provider=lambda: safe_error_message,
    client_ip_provider=lambda: get_client_ip,
    audit_log_provider=lambda: add_audit_log,
)
set_pin_dependency_providers(
    user_dao_provider=lambda: user_dao,
    safe_error_message_provider=lambda: safe_error_message,
    client_ip_provider=lambda: get_client_ip,
    audit_log_provider=lambda: add_audit_log,
    now_provider=lambda: datetime.datetime.now().isoformat(),
)
set_self_password_dependency_providers(
    media_api_provider=lambda: media_api,
    validate_password_strength_provider=lambda: validate_password_strength,
    safe_error_message_provider=lambda: safe_error_message,
)

# ==========================================
# 操作审计日志
# ==========================================

def add_audit_log(admin_id: str, admin_name: str, action: str,
                  target_user_id: str = None, target_user_name: str = None,
                  target_count: int = 0, details: str = "", ip_address: str = ""):
    """添加操作审计日志"""
    try:
        audit_dao.create_user_audit_log(
            admin_id,
            admin_name,
            action,
            target_user_id,
            target_user_name,
            target_count,
            details,
            ip_address,
            datetime.datetime.now().isoformat(),
        )
    except Exception as e:
        logging.error(f"[审计日志] 添加失败: {e}")

router.include_router(delete_verification_admin_router)
router.include_router(audit_log_router)
router.include_router(delete_verification_router)

# 🔥 remark 字段迁移已由 database.py 的 ensure_tables() 处理,此处不再重复
# 移除重复的 ALTER TABLE 代码,避免日志报错

# 🔥 无感迁移:添加 admin_disabled 字段并迁移历史数据
def migrate_admin_disabled():
    """迁移 admin_disabled 字段,区分过期禁用和管理员禁用"""
    try:
        today = datetime.date.today().strftime("%Y-%m-%d")
        disabled_user_ids = set()

        try:
            res = media_api.get("/Users", timeout=10)
            if res.status_code == 200:
                for u in res.json():
                    if u.get('Policy', {}).get('IsDisabled', False):
                        disabled_user_ids.add(u['Id'])
        except Exception as e:
            logging.getLogger("uvicorn").warning(f"⚠️ 迁移时获取用户列表失败: {e}")

        migrated_count = user_dao.migrate_admin_disabled(disabled_user_ids, today)
        if migrated_count is not None:
            logging.getLogger("uvicorn").info("✅ 数据库迁移:已添加 admin_disabled 字段")
            logging.getLogger("uvicorn").info(f"✅ 数据库迁移完成:已标记 {migrated_count} 个管理员禁用用户")
    except Exception as e:
        logging.getLogger("uvicorn").error(f"❌ 数据库迁移失败: {e}")

DANGEROUS_POLICY_KEYS = {'IsAdministrator', 'IsDisabled', 'LoginAttemptsBeforeLockout'}
LIBRARY_POLICY_KEYS = {'EnableAllFolders', 'EnabledFolders', 'ExcludedSubFolders', 'BlockedMediaFolders', 'BlockedChannels', 'EnableAllChannels', 'EnabledChannels'}
PARENTAL_POLICY_KEYS = {'MaxParentalRating', 'BlockUnratedItems', 'BlockedTags', 'AllowedTags'}

def clone_policy(target_policy: dict, src_policy: dict, copy_lib: bool, copy_pol: bool, copy_par: bool):
    """深拷贝策略对象,支持分类映射。无需枚举,兼容未来所有 Emby 新权限字段!"""
    for k, v in src_policy.items():
        if k in DANGEROUS_POLICY_KEYS:
            continue
        is_lib = k in LIBRARY_POLICY_KEYS
        is_par = k in PARENTAL_POLICY_KEYS
        is_pol = not is_lib and not is_par

        if (copy_lib and is_lib) or (copy_par and is_par) or (copy_pol and is_pol):
            target_policy[k] = v
    return target_policy

router.include_router(libraries_router)

router.include_router(manage_list_router)

router.include_router(single_user_router)

# ==========================================
# C 端用户自助 API(修改头像 / 修改密码)
# ==========================================
router.include_router(avatar_router)
router.include_router(self_password_router)


router.include_router(library_visibility_router)
router.include_router(invitation_router)

router.include_router(library_update_router)

router.include_router(update_router)

router.include_router(new_user_router)

class DeleteWithPasswordModel(BaseModel):
    password: Optional[str] = None  # 批量删除必须传密码

router.include_router(delete_router)

router.include_router(batch_router)

router.include_router(template_router)

# ==================== 置顶用户功能 ====================
router.include_router(pin_router)

router.include_router(list_router)

# 审计日志页面路由已移除,改为用户管理页面弹窗

router.include_router(request_permission_router)
router.include_router(tag_router)
