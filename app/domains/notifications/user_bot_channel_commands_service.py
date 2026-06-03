import logging

from app.core.security_utils import safe_error_message


logger = logging.getLogger("uvicorn")

_get_binding_provider = lambda: (lambda tg_user_id: None)
_bind_channel_provider = lambda: (lambda channel_id, tg_user_id, channel_title="": False)
_unbind_channel_provider = lambda: (lambda channel_id: False)
_send_provider = lambda: (lambda chat_id, text, reply_markup=None: None)
_safe_error_message_provider = lambda: safe_error_message
_logger_provider = lambda: logger


def set_dependency_providers(
    *,
    get_binding_provider=None,
    bind_channel_provider=None,
    unbind_channel_provider=None,
    send_provider=None,
    safe_error_message_provider=None,
    logger_provider=None,
):
    global _get_binding_provider
    global _bind_channel_provider
    global _unbind_channel_provider
    global _send_provider
    global _safe_error_message_provider
    global _logger_provider

    if get_binding_provider is not None:
        _get_binding_provider = get_binding_provider
    if bind_channel_provider is not None:
        _bind_channel_provider = bind_channel_provider
    if unbind_channel_provider is not None:
        _unbind_channel_provider = unbind_channel_provider
    if send_provider is not None:
        _send_provider = send_provider
    if safe_error_message_provider is not None:
        _safe_error_message_provider = safe_error_message_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def cmd_bind_channel(chat_id, tg_user_id, args):
    """绑定频道到当前用户账号"""
    binding = _get_binding_provider()(tg_user_id)
    if not binding:
        _send_provider()(chat_id, "❌ 请先绑定 Emby 账号后再绑定频道")
        return

    if not args:
        _send_provider()(chat_id, "💡 使用方法：/bind_channel 频道ID\n\n获取频道ID：\n1. 将频道消息转发给 @userinfobot\n2. 或查看频道链接中的数字\n\n示例：/bind_channel -1001234567890")
        return

    try:
        channel_id = args.strip().split()[0]
        if _bind_channel_provider()(channel_id, tg_user_id, ""):
            _send_provider()(
                chat_id,
                f"✅ 频道绑定成功！\n\n频道ID：<code>{channel_id}</code>\n绑定账号：<b>{binding['emby_username']}</b>\n\n现在用频道身份发送命令将使用此账号",
            )
        else:
            _send_provider()(chat_id, "❌ 绑定失败，请稍后重试")
    except Exception as e:
        _logger_provider().error(f"[频道绑定] 执行失败: {e}")
        _send_provider()(chat_id, f"❌ 绑定失败：{_safe_error_message_provider()(e, '频道绑定异常，请稍后重试')}")


def cmd_unbind_channel(chat_id, tg_user_id, args):
    """解绑频道"""
    if not args:
        _send_provider()(chat_id, "💡 使用方法：/unbind_channel 频道ID")
        return

    channel_id = args.strip().split()[0]
    if _unbind_channel_provider()(channel_id):
        _send_provider()(chat_id, f"✅ 频道 <code>{channel_id}</code> 已解绑")
    else:
        _send_provider()(chat_id, "❌ 解绑失败")
