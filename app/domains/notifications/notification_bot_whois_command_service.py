import datetime
import logging

from app.domains.users import user_bot_dao


logger = logging.getLogger("uvicorn")

_user_bot_dao_provider = lambda: user_bot_dao
_escape_html_provider = lambda: _default_escape_html
_logger_provider = lambda: logger


def _default_escape_html(text):
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def set_dependency_providers(
    *,
    user_bot_dao_provider=None,
    escape_html_provider=None,
    logger_provider=None,
):
    global _user_bot_dao_provider
    global _escape_html_provider
    global _logger_provider

    if user_bot_dao_provider is not None:
        _user_bot_dao_provider = user_bot_dao_provider
    if escape_html_provider is not None:
        _escape_html_provider = escape_html_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def format_expire_status(expire_date):
    if not expire_date:
        return "永久有效"
    expire_text = str(expire_date).strip()
    if not expire_text:
        return "永久有效"

    try:
        exp_date = datetime.date.fromisoformat(expire_text[:10])
        today = datetime.date.today()
        days_left = (exp_date - today).days
        if days_left < 0:
            return f"{expire_text[:10]}（已过期 {abs(days_left)} 天）"
        if days_left == 0:
            return f"{expire_text[:10]}（今天到期）"
        return f"{expire_text[:10]}（{days_left} 天后到期）"
    except Exception:
        return expire_text


def format_whois_row(row, index=None):
    escape_html = _escape_html_provider()
    prefix = f"<b>匹配 {index}</b>\n" if index else "<b>绑定信息</b>\n"
    tg_username = row.get("tg_username") or ""
    tg_display_name = row.get("tg_display_name") or ""
    tg_username_text = f"@{tg_username}" if tg_username and not tg_username.startswith("@") else (tg_username or "未记录")
    expire_status = format_expire_status(row.get("expire_date"))

    return (
        f"{prefix}"
        f"👤 <b>Emby 用户：</b>{escape_html(row.get('emby_username') or '未记录')}\n"
        f"🆔 <b>Emby ID：</b><code>{escape_html(row.get('emby_user_id') or '未记录')}</code>\n"
        f"📅 <b>到期时间：</b>{escape_html(expire_status)}\n"
        f"✈️ <b>TG ID：</b><code>{escape_html(row.get('tg_user_id') or '未记录')}</code>\n"
        f"🔗 <b>TG 用户名：</b>{escape_html(tg_username_text)}\n"
        f"🏷️ <b>TG 名称：</b>{escape_html(tg_display_name or '未记录')}\n"
        f"⏱️ <b>绑定时间：</b>{escape_html(row.get('bound_at') or '未记录')}"
    )


def cmd_whois(bot, cid, text, platform):
    parts = text.split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        return bot.send_message(cid, "👤 请使用: /whois TG用户名/TG ID/Emby用户名", platform=platform)

    keyword = parts[1].strip()
    normalized = keyword.lstrip("@").strip()
    if not normalized:
        return bot.send_message(cid, "👤 请使用: /whois TG用户名/TG ID/Emby用户名", platform=platform)

    try:
        rows = _user_bot_dao_provider().search_whois_bindings(normalized) or []

        if not rows:
            escape_html = _escape_html_provider()
            return bot.send_message(cid, f"📭 未找到与 <b>{escape_html(keyword)}</b> 相关的绑定信息", platform=platform)

        result_rows = [dict(r) for r in rows]
        if len(result_rows) == 1:
            msg = format_whois_row(result_rows[0])
        else:
            msg = f"🔎 <b>找到 {len(result_rows)} 条匹配结果</b>\n\n"
            msg += "\n\n".join(format_whois_row(row, i + 1) for i, row in enumerate(result_rows))

        bot.send_message(cid, msg, platform=platform)
    except Exception as e:
        _logger_provider().error(f"[Bot] whois query error: {e}")
        bot.send_message(cid, "❌ 查询绑定信息失败", platform=platform)
