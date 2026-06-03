from app.infra.clients.telegram_client import telegram_client


def _default_ban_user_provider():
    from app.domains.risk import risk_service

    return risk_service.ban_user


def _default_log_risk_action_provider():
    from app.domains.risk import risk_service

    return risk_service.log_risk_action


_ban_user_provider = _default_ban_user_provider
_log_risk_action_provider = _default_log_risk_action_provider
_telegram_client_provider = lambda: telegram_client
_username_lookup_provider = lambda bot, user_id: bot._get_username(user_id)


def set_dependency_providers(
    *,
    ban_user_provider=None,
    log_risk_action_provider=None,
    telegram_client_provider=None,
    username_lookup_provider=None,
):
    global _ban_user_provider
    global _log_risk_action_provider
    global _telegram_client_provider
    global _username_lookup_provider

    if ban_user_provider is not None:
        _ban_user_provider = ban_user_provider
    if log_risk_action_provider is not None:
        _log_risk_action_provider = log_risk_action_provider
    if telegram_client_provider is not None:
        _telegram_client_provider = telegram_client_provider
    if username_lookup_provider is not None:
        _username_lookup_provider = username_lookup_provider


def handle_risk_ban_callback(bot, data, cq, cid, mid, token, proxies):
    if not data.startswith("risk_ban_"):
        return False

    uid = data.replace("risk_ban_", "")
    operator = cq.get("from", {}).get("first_name", "Admin")
    target_username = _username_lookup_provider(bot, uid)

    if _ban_user_provider()(uid):
        _log_risk_action_provider()(uid, target_username, "ban", f"机器快捷执法 (操作人: {operator})")
        action_text = f"✅ 已成功封禁该违规账号！\n(执行人: {operator})"
    else:
        action_text = "❌ 封禁失败，可能 API 权限不足。"

    msg_obj = cq["message"]
    orig_text = msg_obj.get("text", "风控警报")
    new_text = f"{orig_text}\n\n━━━━━━━━━━━━━━\n{action_text}"
    try:
        _telegram_client_provider().post_api(
            token,
            "editMessageText",
            json={"chat_id": cid, "message_id": mid, "text": new_text, "reply_markup": {"inline_keyboard": []}},
            proxies=proxies,
            timeout=5,
        )
    except Exception:
        pass
    return True
