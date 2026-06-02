"""Public notification facade for cross-domain callers."""


def _get_bot():
    from app.domains.notifications.bot_service import bot

    return bot


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
