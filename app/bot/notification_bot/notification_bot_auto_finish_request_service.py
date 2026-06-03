import logging

from app.domains.media_requests import media_request_dao


logger = logging.getLogger("uvicorn")


def _default_get_notify_rule(rule_type):
    from app.domains.notifications.notify_admin import get_notify_rule

    return get_notify_rule(rule_type)


def _default_user_bot_send():
    from app.bot.user_bot.user_bot_service import _send, _tg_api

    return _send


_media_request_dao_provider = lambda: media_request_dao
_notify_rule_provider = lambda: _default_get_notify_rule
_user_bot_send_provider = lambda: _default_user_bot_send
_logger_provider = lambda: logger


def set_dependency_providers(
    *,
    media_request_dao_provider=None,
    notify_rule_provider=None,
    user_bot_send_provider=None,
    logger_provider=None,
):
    global _media_request_dao_provider
    global _notify_rule_provider
    global _user_bot_send_provider
    global _logger_provider

    if media_request_dao_provider is not None:
        _media_request_dao_provider = media_request_dao_provider
    if notify_rule_provider is not None:
        _notify_rule_provider = notify_rule_provider
    if user_bot_send_provider is not None:
        _user_bot_send_provider = user_bot_send_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def auto_finish_request(bot, tmdb_id, season=None):
    if not tmdb_id:
        return
    try:
        tid = int(tmdb_id)
        requests_to_notify, users_to_notify = _media_request_dao_provider().finish_media_requests_for_item(tid, season)

        if requests_to_notify and users_to_notify:
            bot._notify_request_status_change(tid, requests_to_notify, users_to_notify, "finish")
    except Exception as e:
        _logger_provider().error(f"[自动入库] 更新工单状态失败: {e}")


def _format_status_text(action, reject_reason):
    if action == "approve":
        return "🚀", "审批通过，正在下载中"
    if action == "finish":
        return "✅", "已入库完成，可以观看啦！"
    if action == "reject":
        return "❌", f"已拒绝\n📝 原因: {reject_reason or '未说明'}"
    if action == "manual":
        return "✋", "已手动接单，正在处理中"
    if action == "hdhive_done":
        return "📥", "影巢转存成功，等待入库"
    return "📢", "状态已更新"


def notify_request_status_change(tmdb_id, requests_info, users_info, action, reject_reason=None):
    try:
        logger_obj = _logger_provider()
        rule = _notify_rule_provider()("request_status")

        if not rule or not rule.get("enabled") or "tg_bot" not in rule.get("channels", []):
            logger_obj.info("[状态变更通知] 规则未启用或渠道不含tg_bot")
            return

        user_ids = [u["user_id"] for u in users_info]
        tg_bindings = _media_request_dao_provider().list_tg_bindings(user_ids)
        send = _user_bot_send_provider()()

        for req in requests_info:
            title = req["title"]
            year = req["year"] or ""
            media_type = req["media_type"]
            season = req["season"]

            if media_type == "tv":
                title_text = f"{title} S{season}"
            else:
                title_text = title

            status_icon, status_text = _format_status_text(action, reject_reason)
            msg = f"{status_icon} <b>求片状态更新</b>\n\n📺 <b>内容：</b>{title_text} ({year})\n📢 <b>状态：</b>{status_text}"

            for u in users_info:
                user_id = u["user_id"]
                tg_id = tg_bindings.get(user_id)

                if tg_id:
                    logger_obj.info(f"[自动入库通知] 发送给用户: tg_id={tg_id}, title={title_text}")
                    try:
                        send(int(tg_id), msg)
                    except Exception as e:
                        logger_obj.error(f"[自动入库通知] 发送失败: {e}")
    except Exception as e:
        _logger_provider().error(f"[状态变更通知] 通知失败: {e}")
