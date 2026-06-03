from app.infra.config.user_bot_settings import get_user_bot_token, get_user_bot_welcome_msg


_user_bot_token_provider = lambda: get_user_bot_token()
_welcome_msg_provider = lambda: get_user_bot_welcome_msg()
_send_provider = lambda: (lambda chat_id, text, reply_markup=None: None)


def set_dependency_providers(
    *,
    user_bot_token_provider=None,
    welcome_msg_provider=None,
    send_provider=None,
):
    global _user_bot_token_provider
    global _welcome_msg_provider
    global _send_provider

    if user_bot_token_provider is not None:
        _user_bot_token_provider = user_bot_token_provider
    if welcome_msg_provider is not None:
        _welcome_msg_provider = welcome_msg_provider
    if send_provider is not None:
        _send_provider = send_provider


def _bot_id_from_token():
    token = _user_bot_token_provider()
    return str(token.split(":")[0] if ":" in token else "")


def _default_welcome_message(group_name):
    return (
        f"👋 你好！我是 EmbyPulse 用户机器人，已加入 <b>{group_name}</b>\n\n"
        "✅ 发送 /checkin 或 /签到 获取积分\n"
        "✅ 发送 /help 查看群内可用指令\n\n"
        "💡 更多功能请私聊机器人使用"
    )


def handle_new_chat_members(chat_id, new_members, group_name):
    bot_id = _bot_id_from_token()
    for member in new_members:
        if member.get("is_bot") and str(member.get("id")) == bot_id:
            welcome_msg = _welcome_msg_provider()
            if welcome_msg:
                _send_provider()(chat_id, welcome_msg)
            else:
                _send_provider()(chat_id, _default_welcome_message(group_name))
            break
