import datetime
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.rate_limiter import get_client_ip
from app.core.security_utils import safe_error_message
from app.domains.users import public_service as user_service
from app.domains.users import user_dao
from app.domains.users.auth import is_admin_user
from app.infra.clients.media_server_client import media_api
from app.infra.config.user_bot_settings import get_default_user_template_id


router = APIRouter()


def _noop_audit_log(**_kwargs):
    return None


DANGEROUS_POLICY_KEYS = {'IsAdministrator', 'IsDisabled', 'LoginAttemptsBeforeLockout'}
LIBRARY_POLICY_KEYS = {'EnableAllFolders', 'EnabledFolders', 'ExcludedSubFolders', 'BlockedMediaFolders', 'BlockedChannels', 'EnableAllChannels', 'EnabledChannels'}
PARENTAL_POLICY_KEYS = {'MaxParentalRating', 'BlockUnratedItems', 'BlockedTags', 'AllowedTags'}


def _clone_policy(target_policy: dict, src_policy: dict, copy_lib: bool, copy_pol: bool, copy_par: bool):
    for k, v in src_policy.items():
        if k in DANGEROUS_POLICY_KEYS:
            continue
        is_lib = k in LIBRARY_POLICY_KEYS
        is_par = k in PARENTAL_POLICY_KEYS
        is_pol = not is_lib and not is_par

        if (copy_lib and is_lib) or (copy_par and is_par) or (copy_pol and is_pol):
            target_policy[k] = v
    return target_policy


_media_api_provider = lambda: media_api
_user_dao_provider = lambda: user_dao
_user_service_provider = lambda: user_service
_is_admin_user_provider = lambda: is_admin_user
_default_template_id_provider = lambda: get_default_user_template_id()
_clone_policy_provider = lambda: _clone_policy
_safe_error_message_provider = lambda: safe_error_message
_client_ip_provider = lambda: get_client_ip
_audit_log_provider = lambda: _noop_audit_log
_now_provider = lambda: datetime.datetime.now().isoformat()


class NewUserModelEx(BaseModel):
    name: str
    password: Optional[str] = None
    expire_date: Optional[str] = None
    template_user_id: Optional[str] = None
    copy_library: bool = True
    copy_policy: bool = True
    copy_parental: bool = True
    max_concurrent: Optional[int] = None
    is_vip: bool = False
    remark: Optional[str] = ""
    allow_routes: Optional[str] = ""
    block_routes: Optional[str] = ""
    req_free: Optional[int] = 0  # 0=跟随全局, 1=免费
    req_free_count: Optional[int] = -1  # -1=无限次, >=0=剩余次数


def set_dependency_providers(
    *,
    media_api_provider=None,
    user_dao_provider=None,
    user_service_provider=None,
    is_admin_user_provider=None,
    default_template_id_provider=None,
    clone_policy_provider=None,
    safe_error_message_provider=None,
    client_ip_provider=None,
    audit_log_provider=None,
    now_provider=None,
):
    global _media_api_provider
    global _user_dao_provider
    global _user_service_provider
    global _is_admin_user_provider
    global _default_template_id_provider
    global _clone_policy_provider
    global _safe_error_message_provider
    global _client_ip_provider
    global _audit_log_provider
    global _now_provider

    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if user_dao_provider is not None:
        _user_dao_provider = user_dao_provider
    if user_service_provider is not None:
        _user_service_provider = user_service_provider
    if is_admin_user_provider is not None:
        _is_admin_user_provider = is_admin_user_provider
    if default_template_id_provider is not None:
        _default_template_id_provider = default_template_id_provider
    if clone_policy_provider is not None:
        _clone_policy_provider = clone_policy_provider
    if safe_error_message_provider is not None:
        _safe_error_message_provider = safe_error_message_provider
    if client_ip_provider is not None:
        _client_ip_provider = client_ip_provider
    if audit_log_provider is not None:
        _audit_log_provider = audit_log_provider
    if now_provider is not None:
        _now_provider = now_provider


@router.post("/api/manage/user/new")
def api_manage_user_new(data: NewUserModelEx, request: Request):
    # 🔒 安全检查：必须管理员
    if not _is_admin_user_provider()(request): return {"status": "error", "message": "需要管理员权限"}
    # 🔒 Emby 不可用时拒绝创建
    if not _media_api_provider().health_check():
        return {"status": "error", "message": "Emby 服务不可用，请稍后重试"}
    # 🔥 清除用户缓存
    _user_service_provider().invalidate_emby_users_cache()
    try:
        media = _media_api_provider()
        res = media.post("/Users/New", json={"Name": data.name})
        if res.status_code != 200: return {"status": "error", "message": f"创建失败: {res.text}"}
        new_id = res.json()['Id']

        if data.password: media.post(f"/Users/{new_id}/Password", json={"Id": new_id, "NewPw": data.password})

        p = media.get(f"/Users/{new_id}").json().get('Policy', {})

        tpl_id = data.template_user_id or _default_template_id_provider()
        if tpl_id:
            src_res = media.get(f"/Users/{tpl_id}", timeout=5)
            if src_res.status_code == 200:
                src = src_res.json().get('Policy', {})
                p = _clone_policy_provider()(p, src, data.copy_library, data.copy_policy, data.copy_parental)
        else:
            for k in ['BlockedMediaFolders','BlockedChannels','EnableAllChannels','EnabledChannels']: p.pop(k, None)

        media.post(f"/Users/{new_id}/Policy", json=p)

        v_exp = data.expire_date if data.expire_date else None
        v_max = data.max_concurrent
        v_vip = 1 if data.is_vip else 0
        v_remark = data.remark if data.remark else ""
        v_allow_routes = data.allow_routes if data.allow_routes else ""
        v_block_routes = data.block_routes if data.block_routes else ""
        v_req_free = data.req_free if data.req_free else 0
        v_req_free_count = data.req_free_count if data.req_free_count is not None else -1
        _user_dao_provider().create_user_meta(
            new_id,
            v_exp,
            v_max,
            v_vip,
            v_remark,
            v_allow_routes,
            v_block_routes,
            v_req_free,
            v_req_free_count,
            _now_provider(),
        )

        # 记录审计日志
        admin_user = request.session.get("user", {})
        admin_name = admin_user.get("name", "未知")
        ip_address = _client_ip_provider()(request)
        _audit_log_provider()(
            admin_id=admin_user.get("id", ""),
            admin_name=admin_name,
            action="创建用户",
            target_user_id=new_id,
            target_user_name=data.name,
            ip_address=ip_address
        )

        return {"status": "success", "message": "用户创建成功"}
    except Exception as e: return {"status": "error", "message": _safe_error_message_provider()(e)}
