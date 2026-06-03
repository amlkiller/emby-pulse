import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.bot.notification_bot import bot_service


class FakeLogger:
    def __init__(self):
        self.errors = []

    def error(self, message):
        self.errors.append(message)


def _capture_bot_messages():
    bot = bot_service.NotificationBot()
    sent = []
    bot.send_message = lambda chat_id, text, parse_mode="HTML", reply_markup=None, platform="all": sent.append(
        (chat_id, text, parse_mode, reply_markup, platform)
    )
    return bot, sent


def test_calendar_command_formats_updates_through_legacy_entry(monkeypatch):
    from app.domains.notifications import calendar_notify

    monkeypatch.setattr(calendar_notify, "get_today_updates", lambda: ["episode"])
    monkeypatch.setattr(calendar_notify, "format_notify_message", lambda updates: f"formatted:{updates}")

    bot, sent = _capture_bot_messages()

    bot._cmd_calendar("chat-1", "tg")

    assert sent == [("chat-1", "formatted:['episode']", "HTML", None, "tg")]


def test_calendar_command_logs_error_and_sends_failure_through_legacy_entry(monkeypatch):
    from app.domains.notifications import calendar_notify

    logger = FakeLogger()

    def raise_updates():
        raise RuntimeError("calendar raw")

    monkeypatch.setattr(calendar_notify, "get_today_updates", raise_updates)
    monkeypatch.setattr(bot_service, "logger", logger)

    bot, sent = _capture_bot_messages()

    bot._cmd_calendar("chat-1", "wecom")

    assert logger.errors == ["[Bot] calendar error: calendar raw"]
    assert sent == [("chat-1", "❌ 获取今日更新失败", "HTML", None, "wecom")]


def test_help_command_sends_existing_menu_through_legacy_entry():
    bot, sent = _capture_bot_messages()

    bot._cmd_help("chat-1", "tg")

    assert len(sent) == 1
    chat_id, text, parse_mode, reply_markup, platform = sent[0]
    assert chat_id == "chat-1"
    assert parse_mode == "HTML"
    assert reply_markup is None
    assert platform == "tg"
    assert text.startswith("🤖 <b>EmbyPulse 智能助理指南</b>")
    assert "/calendar - 查看今日剧集更新" in text
    assert "/whois [TG用户名/TG ID/Emby用户名] - 查询绑定信息与到期时间" in text
    assert text.endswith("/help - 获取本帮助菜单")
