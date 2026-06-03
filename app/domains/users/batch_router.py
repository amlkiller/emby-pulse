import datetime
from typing import List, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.rate_limiter import get_client_ip
from app.core.security_utils import safe_error_message
from app.domains.users import user_dao
from app.domains.users.auth import is_admin_user
from app.domains.users.delete_verification_router import verify_emby_admin_password
from app.infra.clients.media_server_client import media_api


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
_is_admin_user_provider = lambda: is_admin_user
_verify_admin_password_provider = lambda: verify_emby_admin_password
_clone_policy_provider = lambda: _clone_policy
_safe_error_message_provider = lambda: safe_error_message
_client_ip_provider = lambda: get_client_ip
_audit_log_provider = lambda: _noop_audit_log
_datetime_provider = lambda: datetime


class BatchActionModelLocal(BaseModel):
    user_ids: List[str]
    action: str
    value: Optional[str] = None
    copy_library: Optional[bool] = True
    copy_policy: Optional[bool] = True
    copy_parental: Optional[bool] = True
    allow_routes: Optional[str] = ""
    block_routes: Optional[str] = ""
    req_free: Optional[int] = 0  # 求片权限:0=跟随全局, 1=免费
    req_free_count: Optional[int] = -1  # 免费求片次数:-1=无限, >=0=次数
    username: Optional[str] = None  # 批量删除时必须传管理员账号
    password: Optional[str] = None  # 批量删除时必须传密码


def set_dependency_providers(
    *,
    media_api_provider=None,
    user_dao_provider=None,
    is_admin_user_provider=None,
    verify_admin_password_provider=None,
    clone_policy_provider=None,
    safe_error_message_provider=None,
    client_ip_provider=None,
    audit_log_provider=None,
    datetime_provider=None,
):
    global _media_api_provider
    global _user_dao_provider
    global _is_admin_user_provider
    global _verify_admin_password_provider
    global _clone_policy_provider
    global _safe_error_message_provider
    global _client_ip_provider
    global _audit_log_provider
    global _datetime_provider

    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if user_dao_provider is not None:
        _user_dao_provider = user_dao_provider
    if is_admin_user_provider is not None:
        _is_admin_user_provider = is_admin_user_provider
    if verify_admin_password_provider is not None:
        _verify_admin_password_provider = verify_admin_password_provider
    if clone_policy_provider is not None:
        _clone_policy_provider = clone_policy_provider
    if safe_error_message_provider is not None:
        _safe_error_message_provider = safe_error_message_provider
    if client_ip_provider is not None:
        _client_ip_provider = client_ip_provider
    if audit_log_provider is not None:
        _audit_log_provider = audit_log_provider
    if datetime_provider is not None:
        _datetime_provider = datetime_provider


@router.post("/api/manage/users/batch")
def api_manage_users_batch(data: BatchActionModelLocal, request: Request):
    if not request.session.get("user"): return {"status": "error"}
    if not _is_admin_user_provider()(request): return {"status": "error", "message": "需要管理员权限"}
    if len(data.user_ids) > 100:
        return {"status": "error", "message": "单次批量操作最多 100 个用户"}
    # 🔒 Emby 不可用时拒绝批量操作（一次校验，避免循环中放大请求）
    if not _media_api_provider().health_check():
        return {"status": "error", "message": "Emby 服务不可用，请稍后重试"}

    # 获取当前管理员账号
    admin_user = request.session.get("user", {})
    admin_name = admin_user.get("name", admin_user.get("username", "未知管理员"))

    try:
        media = _media_api_provider()
        dao = _user_dao_provider()
        dt = _datetime_provider()

        # 批量删除需要账号和密码验证
        if data.action == "delete":
            if not data.username or not data.password:
                return {"status": "error", "message": "批量删除需要验证管理员账号和密码", "need_password": True}
            if not _verify_admin_password_provider()(data.username, data.password):
                return {"status": "error", "message": "账号或密码错误"}

        src_policy = {}; src_max_concurrent = None; src_is_vip = 0
        if data.action == "apply_template" and data.value:
            src_res = media.get(f"/Users/{data.value}", timeout=5)
            if src_res.status_code == 200:
                src_policy = src_res.json().get('Policy', {})
                t_meta = dao.get_user_policy_meta(data.value)
                src_max_concurrent = t_meta['max_concurrent'] if t_meta else None
                src_is_vip = t_meta['is_vip'] if t_meta and t_meta['is_vip'] else 0
            else:
                return {"status": "error", "message": "无法获取模板配置"}

        deleted_count = 0
        deleted_names = []
        # 其他操作的用户名列表
        operated_names = []

        for uid in data.user_ids:
            if data.action == "delete":
                # 获取用户名用于日志
                user_name = ""
                try:
                    user_res = media.get(f"/Users/{uid}", timeout=5)
                    if user_res.status_code == 200:
                        user_name = user_res.json().get("Name", "")
                except:
                    pass

                media.delete(f"/Users/{uid}")
                dao.delete_user_meta(uid)
                # 同步删除临时账号记录
                try:
                    dao.delete_temp_account_by_emby_user(uid)
                except:
                    pass
                deleted_count += 1
                if user_name:
                    deleted_names.append(user_name)
            elif data.action in ["enable", "disable"]:
                p_res = media.get(f"/Users/{uid}", timeout=5)
                if p_res.status_code == 200:
                    user_data = p_res.json()
                    user_name = user_data.get("Name", "")
                    if user_name:
                        operated_names.append(user_name)
                    p = user_data.get('Policy', {})
                    p['IsDisabled'] = (data.action == "disable")
                    if data.action == "enable": p['LoginAttemptsBeforeLockout'] = -1
                    media.post(f"/Users/{uid}/Policy", json=p)
                    # 设置 admin_disabled 标记
                    try:
                        dao.save_user_admin_disabled(uid, data.action == "disable", dt.datetime.now().isoformat())
                    except Exception: pass
            elif data.action == "renew":
                # 获取用户名
                try:
                    user_res = media.get(f"/Users/{uid}", timeout=5)
                    if user_res.status_code == 200:
                        user_name = user_res.json().get("Name", "")
                        if user_name:
                            operated_names.append(user_name)
                except Exception: pass

                new_date = None
                if data.value.startswith('+'):
                    days_to_add = int(data.value[1:])
                    row = dao.get_user_meta(uid)
                    current_expire = row['expire_date'] if row and row['expire_date'] else None
                    if current_expire:
                        try:
                            base_date = dt.datetime.strptime(current_expire, "%Y-%m-%d")
                            if base_date < dt.datetime.now(): base_date = dt.datetime.now()
                        except: base_date = dt.datetime.now()
                    else: base_date = dt.datetime.now()
                    new_date = (base_date + dt.timedelta(days=days_to_add)).strftime("%Y-%m-%d")
                else: new_date = data.value if data.value else None

                dao.save_user_expire_preserve(uid, new_date, dt.datetime.now().isoformat())
            elif data.action == "apply_template":
                p_res = media.get(f"/Users/{uid}", timeout=5)
                if p_res.status_code == 200:
                    user_data = p_res.json()
                    user_name = user_data.get("Name", "")
                    if user_name:
                        operated_names.append(user_name)
                    p = user_data.get('Policy', {})
                    p = _clone_policy_provider()(p, src_policy, data.copy_library, data.copy_policy, data.copy_parental)

                    if data.copy_policy:
                        dao.save_user_policy_meta(uid, src_max_concurrent, src_is_vip, dt.datetime.now().isoformat())

                    media.post(f"/Users/{uid}/Policy", json=p)
            elif data.action == "set_routes":
                # 批量设置用户线路权限
                allow_routes = data.allow_routes if data.allow_routes else ""
                block_routes = data.block_routes if data.block_routes else ""

                # 获取用户名
                try:
                    user_res = media.get(f"/Users/{uid}", timeout=5)
                    if user_res.status_code == 200:
                        user_name = user_res.json().get("Name", "")
                        if user_name:
                            operated_names.append(user_name)
                except Exception: pass

                dao.save_user_routes_preserve(uid, allow_routes, block_routes, dt.datetime.now().isoformat())
            elif data.action == "set_req_free":
                # 批量设置求片权限
                req_free = data.req_free if data.req_free is not None else 0
                req_free_count = data.req_free_count if data.req_free_count is not None else -1

                # 获取用户名
                try:
                    user_res = media.get(f"/Users/{uid}", timeout=5)
                    if user_res.status_code == 200:
                        user_name = user_res.json().get("Name", "")
                        if user_name:
                            operated_names.append(user_name)
                except Exception: pass

                dao.save_user_req_permission(uid, req_free, req_free_count, dt.datetime.now().isoformat())

        # 记录审计日志
        ip_address = _client_ip_provider()(request)
        # 格式化用户名列表(最多显示10个)
        names_str = ', '.join(operated_names[:10]) + ('...' if len(operated_names) > 10 else '') if operated_names else ''

        if data.action == "delete" and deleted_count > 0:
            _audit_log_provider()(
                admin_id=admin_user.get("id", ""),
                admin_name=admin_name,
                action="批量删除",
                target_count=deleted_count,
                details=f"删除用户: {', '.join(deleted_names[:10])}{'...' if len(deleted_names) > 10 else ''}",
                ip_address=ip_address
            )
        elif data.action == "enable":
            _audit_log_provider()(
                admin_id=admin_user.get("id", ""),
                admin_name=admin_name,
                action="批量启用",
                target_count=len(data.user_ids),
                details=f"启用用户: {names_str or f'{len(data.user_ids)} 个'}",
                ip_address=ip_address
            )
        elif data.action == "disable":
            _audit_log_provider()(
                admin_id=admin_user.get("id", ""),
                admin_name=admin_name,
                action="批量禁用",
                target_count=len(data.user_ids),
                details=f"禁用用户: {names_str or f'{len(data.user_ids)} 个'}",
                ip_address=ip_address
            )
        elif data.action == "apply_template":
            _audit_log_provider()(
                admin_id=admin_user.get("id", ""),
                admin_name=admin_name,
                action="批量应用模板",
                target_count=len(data.user_ids),
                details=f"模板: {data.value}, 用户: {names_str or f'{len(data.user_ids)} 个'}",
                ip_address=ip_address
            )
        elif data.action == "renew":
            _audit_log_provider()(
                admin_id=admin_user.get("id", ""),
                admin_name=admin_name,
                action="批量续期",
                target_count=len(data.user_ids),
                details=f"续期: {data.value}, 用户: {names_str or f'{len(data.user_ids)} 个'}",
                ip_address=ip_address
            )
        elif data.action == "set_routes":
            _audit_log_provider()(
                admin_id=admin_user.get("id", ""),
                admin_name=admin_name,
                action="批量设置线路",
                target_count=len(data.user_ids),
                details=f"允许: {data.allow_routes or '无'}, 屏蔽: {data.block_routes or '无'}, 用户: {names_str or f'{len(data.user_ids)} 个'}",
                ip_address=ip_address
            )
        elif data.action == "set_req_free":
            req_mode = "免费求片" if data.req_free == 1 else "跟随全局"
            req_count_str = "无限次" if data.req_free_count == -1 else f"{data.req_free_count}次"
            _audit_log_provider()(
                admin_id=admin_user.get("id", ""),
                admin_name=admin_name,
                action="批量设置求片权限",
                target_count=len(data.user_ids),
                details=f"模式: {req_mode}, 次数: {req_count_str}, 用户: {names_str or f'{len(data.user_ids)} 个'}",
                ip_address=ip_address
            )

        return {"status": "success", "message": f"成功操作了 {len(data.user_ids)} 个用户"}
    except Exception as e: return {"status": "error", "message": _safe_error_message_provider()(e)}
