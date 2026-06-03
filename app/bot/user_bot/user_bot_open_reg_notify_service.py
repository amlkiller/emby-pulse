import datetime
import logging

from app.infra.config.user_bot_settings import (
    get_user_bot_allowed_groups,
    is_user_bot_open_reg_notify_group_enabled,
    is_user_bot_open_reg_notify_user_enabled,
)


logger = logging.getLogger("uvicorn")

_notify_user_enabled_provider = lambda: is_user_bot_open_reg_notify_user_enabled()
_notify_group_enabled_provider = lambda: is_user_bot_open_reg_notify_group_enabled()
_allowed_groups_provider = lambda: get_user_bot_allowed_groups()
_get_all_bot_users_provider = lambda: []
_send_provider = lambda: (lambda chat_id, text: None)
_logger_provider = lambda: logger
_datetime_provider = lambda: datetime


def set_dependency_providers(
    *,
    notify_user_enabled_provider=None,
    notify_group_enabled_provider=None,
    allowed_groups_provider=None,
    get_all_bot_users_provider=None,
    send_provider=None,
    logger_provider=None,
    datetime_provider=None,
):
    global _notify_user_enabled_provider
    global _notify_group_enabled_provider
    global _allowed_groups_provider
    global _get_all_bot_users_provider
    global _send_provider
    global _logger_provider
    global _datetime_provider

    if notify_user_enabled_provider is not None:
        _notify_user_enabled_provider = notify_user_enabled_provider
    if notify_group_enabled_provider is not None:
        _notify_group_enabled_provider = notify_group_enabled_provider
    if allowed_groups_provider is not None:
        _allowed_groups_provider = allowed_groups_provider
    if get_all_bot_users_provider is not None:
        _get_all_bot_users_provider = get_all_bot_users_provider
    if send_provider is not None:
        _send_provider = send_provider
    if logger_provider is not None:
        _logger_provider = logger_provider
    if datetime_provider is not None:
        _datetime_provider = datetime_provider


def send_open_reg_closed_notify(reason=""):
    """发送开放注册关闭通知（名额已满等场景）"""
    notify_user = _notify_user_enabled_provider()
    notify_group = _notify_group_enabled_provider()

    if not notify_user and not notify_group:
        return

    reason_text = f"（{reason}）" if reason else ""
    msg = f"""📢 <b>开放注册已结束</b>

🙏 感谢大家的支持！
📊 本次开放注册已圆满结束{reason_text}
💌 如有疑问请联系管理员

⏰ 结束时间：{_datetime_provider().datetime.now().strftime("%Y-%m-%d %H:%M")}"""

    if notify_user:
        try:
            users = _get_all_bot_users_provider()
            for u in users:
                try:
                    _send_provider()(int(u["tg_user_id"]), msg)
                except Exception as e:
                    _logger_provider().error(f"[开放注册通知] 发送给用户 {u['tg_user_id']} 失败: {e}")
        except Exception as e:
            _logger_provider().error(f"[开放注册通知] 用户私聊通知失败: {e}")

    if notify_group:
        try:
            allowed_groups = _allowed_groups_provider()
            if allowed_groups:
                group_ids = [g.strip() for g in allowed_groups.replace("，", ",").split("\n") if g.strip()]
                for gid in group_ids:
                    try:
                        _send_provider()(int(gid), msg)
                        _logger_provider().info(f"[开放注册通知] 已发送到群 {gid}")
                    except Exception as e:
                        _logger_provider().error(f"[开放注册通知] 发送到群 {gid} 失败: {e}")
            else:
                _logger_provider().warning("[开放注册通知] 未配置群 ID，跳过群聊通知")
        except Exception as e:
            _logger_provider().error(f"[开放注册通知] 群聊通知失败: {e}")
