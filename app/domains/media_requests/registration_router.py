import datetime as dt
import json
import logging
import re

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.security import validate_password_strength
from app.core.security_utils import safe_error_message
from app.domains.media_requests.media_request_dao import (
    claim_registration_invitation,
    restore_invitation_code,
    save_registered_user_meta,
)
from app.domains.notifications import notify_admin
from app.domains.notifications import public_service as notification_service
from app.domains.users import public_service as user_service
from app.infra.clients.media_server_client import media_api
from app.infra.config.media_server_settings import (
    get_media_server_main_public_or_host,
    get_media_server_user_routes,
    get_media_server_welcome_message,
)
from app.infra.db import notification_dao


router = APIRouter()

_validate_password_strength_provider = lambda: validate_password_strength
_media_api_provider = lambda: media_api
_claim_registration_invitation_provider = lambda: claim_registration_invitation
_restore_invitation_code_provider = lambda: restore_invitation_code
_save_registered_user_meta_provider = lambda: save_registered_user_meta
_user_service_provider = lambda: user_service
_notify_admin_provider = lambda: notify_admin
_notification_service_provider = lambda: notification_service
_system_notification_provider = lambda: notification_dao.add_system_notification
_user_routes_provider = lambda: get_media_server_user_routes
_main_server_url_provider = lambda: get_media_server_main_public_or_host
_welcome_message_provider = lambda: get_media_server_welcome_message
_safe_error_message_provider = lambda: safe_error_message
_logger_provider = lambda: logging.getLogger("uvicorn")


class UserRegisterModel(BaseModel):
    """用户社区注册模型"""
    code: str
    username: str
    password: str


def set_dependency_providers(
    *,
    validate_password_strength_provider=None,
    media_api_provider=None,
    claim_registration_invitation_provider=None,
    restore_invitation_code_provider=None,
    save_registered_user_meta_provider=None,
    user_service_provider=None,
    notify_admin_provider=None,
    notification_service_provider=None,
    system_notification_provider=None,
    user_routes_provider=None,
    main_server_url_provider=None,
    welcome_message_provider=None,
    safe_error_message_provider=None,
    logger_provider=None,
):
    global _validate_password_strength_provider
    global _media_api_provider
    global _claim_registration_invitation_provider
    global _restore_invitation_code_provider
    global _save_registered_user_meta_provider
    global _user_service_provider
    global _notify_admin_provider
    global _notification_service_provider
    global _system_notification_provider
    global _user_routes_provider
    global _main_server_url_provider
    global _welcome_message_provider
    global _safe_error_message_provider
    global _logger_provider

    if validate_password_strength_provider is not None:
        _validate_password_strength_provider = validate_password_strength_provider
    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if claim_registration_invitation_provider is not None:
        _claim_registration_invitation_provider = claim_registration_invitation_provider
    if restore_invitation_code_provider is not None:
        _restore_invitation_code_provider = restore_invitation_code_provider
    if save_registered_user_meta_provider is not None:
        _save_registered_user_meta_provider = save_registered_user_meta_provider
    if user_service_provider is not None:
        _user_service_provider = user_service_provider
    if notify_admin_provider is not None:
        _notify_admin_provider = notify_admin_provider
    if notification_service_provider is not None:
        _notification_service_provider = notification_service_provider
    if system_notification_provider is not None:
        _system_notification_provider = system_notification_provider
    if user_routes_provider is not None:
        _user_routes_provider = user_routes_provider
    if main_server_url_provider is not None:
        _main_server_url_provider = main_server_url_provider
    if welcome_message_provider is not None:
        _welcome_message_provider = welcome_message_provider
    if safe_error_message_provider is not None:
        _safe_error_message_provider = safe_error_message_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def _restore_invitation_code(code):
    """Emby 用户创建失败时回滚邀请码消费计数"""
    try:
        _restore_invitation_code_provider()(code)
    except Exception:
        pass


@router.post("/api/requests/register")
async def user_community_register(data: UserRegisterModel, request: Request):
    """用户社区注册 API - 注册成功后自动登录"""
    media = _media_api_provider()
    claim_invitation = _claim_registration_invitation_provider()
    save_user_meta = _save_registered_user_meta_provider()
    users = _user_service_provider()
    notify_rules = _notify_admin_provider()
    notifications = _notification_service_provider()
    add_notification = _system_notification_provider()
    get_user_routes = _user_routes_provider()
    get_main_server_url = _main_server_url_provider()
    get_welcome_message = _welcome_message_provider()
    validate_password = _validate_password_strength_provider()
    safe_error = _safe_error_message_provider()
    logger = _logger_provider()

    try:
        # 1. 先校验用户名和密码（不消耗邀请码）
        username = data.username.strip()
        if not username or len(username) < 2:
            return {"status": "error", "message": "用户名至少需要 2 个字符"}

        if len(username) > 16:
            return {"status": "error", "message": "用户名最多 16 个字符，当前 " + str(len(username)) + " 个字符"}

        safe_name = re.sub(r'[^a-zA-Z0-9一-龥_\-.@]', '', username)

        if safe_name != username:
            invalid_chars = set(re.findall(r'[^a-zA-Z0-9一-龥_\-.@]', username))
            invalid_str = ', '.join(f"'{c}'" for c in list(invalid_chars)[:5])
            return {"status": "error", "message": f"用户名包含不支持的字符: {invalid_str}。只允许字母、数字、中文、下划线(_)、连字符(-)、@ 和 ."}

        if not safe_name:
            return {"status": "error", "message": "用户名无效，请使用字母、数字、中文、下划线(_)、连字符(-)、@ 或 ."}

        password = data.password.strip()
        pw_valid, pw_error = validate_password(password)
        if not pw_valid:
            return {"status": "error", "message": pw_error}

        # 2. 检查 Emby 用户名是否已存在
        try:
            users_data = media.get("/Users", timeout=5).json()
            if any(u['Name'].lower() == safe_name.lower() for u in users_data):
                return {"status": "error", "message": f"用户名 {safe_name} 已被占用，请换一个"}
        except Exception as e:
            return {"status": "error", "message": safe_error(e, "检查用户名失败")}

        # 3. 所有校验通过后，原子抢占邀请码（防 TOCTOU 竞态）
        invite, invite_error = claim_invitation(data.code, safe_name)
        if invite_error:
            return {"status": "error", "message": invite_error}

        days = invite['days'] if invite['days'] else 30
        template_user_id = invite['template_user_id'] if invite['template_user_id'] else None
        routes = invite['routes'] if invite['routes'] else ''
        route_mode = invite['route_mode'] if invite['route_mode'] else 'block'
        req_free = invite['req_free'] if 'req_free' in invite.keys() else 0
        req_free_count = invite['req_free_count'] if 'req_free_count' in invite.keys() else -1

        # 4. 创建 Emby 用户
        try:
            create_res = media.post("/Users/New", json={"Name": safe_name}, timeout=10)
            if create_res.status_code not in [200, 201]:
                _restore_invitation_code(data.code)
                return {"status": "error", "message": f"创建账号失败: {create_res.text}"}

            new_user = create_res.json()
            uid = new_user.get("Id")

            # 设置密码
            media.post(f"/Users/{uid}/Password", json={"NewPw": password}, timeout=5)

            # 应用模板（如果有）
            admin_enabled_folders = None
            if template_user_id:
                try:
                    tpl = media.get(f"/Users/{template_user_id}", timeout=5).json()
                    if tpl.get("Policy"):
                        policy = tpl["Policy"]
                        policy["IsAdministrator"] = False
                        policy["IsDisabled"] = False
                        media.post(f"/Users/{uid}/Policy", json=policy, timeout=5)
                        # 🔥 保存管理员设置的媒体库权限
                        if not policy.get("EnableAllFolders", True):
                            admin_enabled_folders = policy.get("EnabledFolders", [])
                except:
                    pass
            else:
                try:
                    # 读取完整 Policy 再合并，避免 Emby 整体替换清空默认权限
                    user_info = media.get(f"/Users/{uid}", timeout=5).json()
                    policy = user_info.get("Policy", {})
                    policy["IsDisabled"] = False
                    media.post(f"/Users/{uid}/Policy", json=policy, timeout=3)
                except:
                    pass

            # 6. 保存用户元数据
            # 处理永久注册码：days = -1 或 days = 0 或 days >= 36500（100年）视为永久
            expire_date = None
            if days == -1 or days == 0 or days >= 36500:
                expire_date = None  # 永久有效用 None 表示
            elif days > 0:
                expire_date = (dt.date.today() + dt.timedelta(days=days)).strftime("%Y-%m-%d")

            allow_routes = ""
            block_routes = ""
            if routes:
                if route_mode == 'allow':
                    allow_routes = routes
                else:
                    block_routes = routes

            save_user_meta(uid, expire_date, allow_routes, block_routes, req_free, req_free_count, admin_enabled_folders)

            # 清除用户列表缓存
            try:
                users.invalidate_emby_users_cache()
            except:
                pass

            # 8. 发送通知
            try:
                rule = notify_rules.get_notify_rule('user_register')
                days_display = "永久" if (days == -1 or days == 0 or days >= 36500) else f"{days} 天"
                msg = f"🎟️ <b>新用户注册</b>\n\n👤 {safe_name}\n📅 有效期：{days_display}\n🔗 邀请码：{data.code}\n📱 注册渠道：用户社区"

                if rule and rule.get('enabled'):
                    channels = rule.get('channels', [])

                    # TG机器人/企业微信
                    if 'tg_bot' in channels or 'wecom' in channels:
                        platform = "all" if ('tg_bot' in channels and 'wecom' in channels) else ("tg" if 'tg_bot' in channels else "wecom")
                        notifications.send_message("sys_notify", msg, platform=platform)

                    # Web通知中心
                    if 'web' in channels:
                        add_notification("user", f"新用户注册: {safe_name}", f"用户社区注册，有效期 {days_display}", "/users_manage")
                else:
                    # 兜底：使用旧方式发送通知
                    notifications.send_message("sys_notify", msg, platform="all")
                    add_notification("user", f"新用户注册: {safe_name}", f"用户社区注册，有效期 {days_display}", "/users_manage")
            except Exception as e:
                logger.error(f"[用户社区注册] 发送通知失败: {e}")

            # 9. 🔥 获取用户可访问的线路（使用 get_user_routes 根据权限过滤）
            user_routes = get_user_routes(uid)
            if not user_routes:
                # 如果没有线路，使用默认服务器地址
                server_url = get_main_server_url()
                if server_url:
                    user_routes = [{"name": "默认推荐节点", "url": server_url, "is_main": True}]

            # 10. 🔥 自动登录用户社区
            # 🔥 安全：清除整个 Session，防止残留其他用户数据
            request.session.clear()
            request.session["req_user"] = {"Id": uid, "Name": safe_name}

            # 11. 获取欢迎消息
            welcome_message = get_welcome_message()

            return {
                "status": "success",
                "message": "注册成功",
                "user": {"Id": uid, "Name": safe_name},
                "expire_days": days,
                "expire_date": expire_date,
                "server_url": json.dumps(user_routes) if user_routes else "",
                "welcome_message": welcome_message,
            }

        except Exception as e:
            logger.error(f"[用户社区注册] 创建用户失败: {e}")
            _restore_invitation_code(data.code)
            return {"status": "error", "message": safe_error(e, "注册失败")}

    except Exception as e:
        logger.error(f"[用户社区注册] 系统错误: {e}")
        return {"status": "error", "message": safe_error(e, "系统错误")}
