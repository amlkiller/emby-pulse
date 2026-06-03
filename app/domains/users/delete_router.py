import datetime

from fastapi import APIRouter, Request

from app.core.rate_limiter import get_client_ip
from app.core.security_utils import safe_error_message
from app.domains.notifications import notify_admin
from app.domains.users import public_service as user_service
from app.domains.users import user_dao
from app.domains.users.auth import is_admin_user
from app.domains.users.delete_verification_router import APP_START_TIME
from app.infra.clients.media_server_client import media_api


router = APIRouter()


def _noop_audit_log(**_kwargs):
    return None


_media_api_provider = lambda: media_api
_user_dao_provider = lambda: user_dao
_user_service_provider = lambda: user_service
_is_admin_user_provider = lambda: is_admin_user
_notify_admin_provider = lambda: notify_admin
_safe_error_message_provider = lambda: safe_error_message
_client_ip_provider = lambda: get_client_ip
_audit_log_provider = lambda: _noop_audit_log
_app_start_time_provider = lambda: APP_START_TIME
_now_provider = lambda: datetime.datetime.now()


def set_dependency_providers(
    *,
    media_api_provider=None,
    user_dao_provider=None,
    user_service_provider=None,
    is_admin_user_provider=None,
    notify_admin_provider=None,
    safe_error_message_provider=None,
    client_ip_provider=None,
    audit_log_provider=None,
    app_start_time_provider=None,
    now_provider=None,
):
    global _media_api_provider
    global _user_dao_provider
    global _user_service_provider
    global _is_admin_user_provider
    global _notify_admin_provider
    global _safe_error_message_provider
    global _client_ip_provider
    global _audit_log_provider
    global _app_start_time_provider
    global _now_provider

    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if user_dao_provider is not None:
        _user_dao_provider = user_dao_provider
    if user_service_provider is not None:
        _user_service_provider = user_service_provider
    if is_admin_user_provider is not None:
        _is_admin_user_provider = is_admin_user_provider
    if notify_admin_provider is not None:
        _notify_admin_provider = notify_admin_provider
    if safe_error_message_provider is not None:
        _safe_error_message_provider = safe_error_message_provider
    if client_ip_provider is not None:
        _client_ip_provider = client_ip_provider
    if audit_log_provider is not None:
        _audit_log_provider = audit_log_provider
    if app_start_time_provider is not None:
        _app_start_time_provider = app_start_time_provider
    if now_provider is not None:
        _now_provider = now_provider


@router.delete("/api/manage/user/{user_id}")
def api_manage_user_delete(user_id: str, request: Request):
    """删除单个用户 - 需要密码验证(首次验证后 30 分钟内有效,重启后失效)"""
    if not request.session.get("user"):
        return {"status": "error", "message": "未登录"}
    if not _is_admin_user_provider()(request):
        return {"status": "error", "message": "需要管理员权限"}
    # 🔒 Emby 不可用时拒绝删除，避免本地标记与远端失步
    if not _media_api_provider().health_check():
        return {"status": "error", "message": "Emby 服务不可用，请稍后重试"}

    # 🔥 清除用户缓存
    _user_service_provider().invalidate_emby_users_cache()

    # 检查是否已验证
    verified = request.session.get("delete_verified", False)
    verified_time = request.session.get("delete_verified_time", "")

    # 验证有效期检查(30分钟 + 重启后失效)
    if verified and verified_time:
        try:
            verify_dt = datetime.datetime.fromisoformat(verified_time)
            # 超过30分钟
            if _now_provider() - verify_dt > datetime.timedelta(minutes=30):
                verified = False
                request.session["delete_verified"] = False
            # 验证时间在容器启动之前(重启后失效)
            elif verify_dt < datetime.datetime.fromisoformat(_app_start_time_provider()):
                verified = False
                request.session["delete_verified"] = False
        except:
            verified = False

    if not verified:
        return {"status": "error", "message": "需要验证密码", "need_password": True}

    # 获取当前管理员账号
    admin_user = request.session.get("user", {})
    admin_name = admin_user.get("name", admin_user.get("username", "未知管理员"))

    try:
        media = _media_api_provider()
        dao = _user_dao_provider()

        # 获取用户名用于日志
        user_name = ""
        try:
            user_res = media.get(f"/Users/{user_id}", timeout=5)
            if user_res.status_code == 200:
                user_name = user_res.json().get("Name", "")
        except:
            pass

        if media.delete(f"/Users/{user_id}").status_code in [200, 204]:
            dao.delete_user_meta(user_id)
            # 同步删除临时账号记录
            try:
                dao.delete_temp_account_by_emby_user(user_id)
            except:
                pass

            # 🔥 发送用户删除通知
            try:
                from app.infra.db.notification_dao import add_system_notification
                from app.domains.notifications import public_service as notification_service

                rule = _notify_admin_provider().get_notify_rule('user_delete')
                if rule and rule.get('enabled'):
                    channels = rule.get('channels', [])
                    msg = f"🗑️ <b>用户删除通知</b>\n\n👤 <b>用户:</b>{user_name}\n👮 <b>操作人:</b>{admin_name}\n🕒 <b>时间:</b>{_now_provider().strftime('%Y-%m-%d %H:%M:%S')}"

                    # TG机器人/企业微信
                    if 'tg_bot' in channels or 'wecom' in channels:
                        platform = "all" if ('tg_bot' in channels and 'wecom' in channels) else ("tg" if 'tg_bot' in channels else "wecom")
                        notification_service.send_message("sys_notify", msg, platform=platform)

                    # Web通知中心
                    if 'web' in channels:
                        add_system_notification("user", f"用户删除: {user_name}", f"操作人: {admin_name}", "/users_manage")
            except Exception as e:
                pass

            # 记录审计日志
            ip_address = _client_ip_provider()(request)
            _audit_log_provider()(
                admin_id=admin_user.get("id", ""),
                admin_name=admin_name,
                action="删除用户",
                target_user_id=user_id,
                target_user_name=user_name,
                details="单个删除",
                ip_address=ip_address
            )
            return {"status": "success", "message": f"用户 {user_name} 已删除"}
        return {"status": "error", "message": "Emby 删除失败"}
    except Exception as e:
        return {"status": "error", "message": _safe_error_message_provider()(e)}
