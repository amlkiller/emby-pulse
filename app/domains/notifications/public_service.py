"""Public notification facade for cross-domain callers."""


def _get_bot():
    from app.domains.notifications.bot_service import bot

    return bot


def _get_user_bot_service():
    from app.domains.notifications import user_bot_service

    return user_bot_service


def send_message(chat_id, text, parse_mode="HTML", reply_markup=None, platform="all"):
    return _get_bot().send_message(chat_id, text, parse_mode, reply_markup, platform)


def edit_message(chat_id, message_id, text, parse_mode="HTML", reply_markup=None, platform="tg"):
    return _get_bot().edit_message(chat_id, message_id, text, parse_mode, reply_markup, platform)


def send_photo(
    chat_id,
    photo_io,
    caption,
    parse_mode="HTML",
    reply_markup=None,
    platform="all",
    wecom_photo_io=None,
):
    return _get_bot().send_photo(
        chat_id,
        photo_io,
        caption,
        parse_mode,
        reply_markup,
        platform,
        wecom_photo_io,
    )


def send_to_channels(photo_io, caption, keyboard=None):
    return _get_bot().send_to_channels(photo_io, caption, keyboard)


def push_report_now(user_id, period, theme):
    return _get_bot().push_now(user_id, period, theme)


def is_user_bot_running() -> bool:
    return bool(_get_user_bot_service().user_bot.running)


def send_user_bot_message(chat_id, text, reply_markup=None):
    return _get_user_bot_service()._send(chat_id, text, reply_markup)


def send_user_bot_photo(chat_id, photo, caption, parse_mode="HTML"):
    return _get_user_bot_service()._tg_api(
        "sendPhoto",
        {"chat_id": chat_id, "photo": photo, "caption": caption, "parse_mode": parse_mode},
    )


def get_notify_rule(notify_type):
    from app.domains.notifications.notify_admin import get_notify_rule as notify_admin_get_notify_rule

    return notify_admin_get_notify_rule(notify_type)
