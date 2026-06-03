import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.domains.notifications import bot_service


class FakeBus:
    def __init__(self):
        self.published = []

    def publish(self, event, *args):
        self.published.append((event, *args))


class FakeLogger:
    def __init__(self):
        self.infos = []
        self.warnings = []

    def info(self, message):
        self.infos.append(message)

    def warning(self, message):
        self.warnings.append(message)


def test_is_admin_preserves_tg_comma_parsing_and_wecom_allow(monkeypatch):
    monkeypatch.setattr(bot_service, "get_tg_chat_id", lambda: " 100，200, 300 ")
    bot = bot_service.NotificationBot()

    assert bot._is_admin("100", "tg") is True
    assert bot._is_admin("200", "tg") is True
    assert bot._is_admin("300", "tg") is True
    assert bot._is_admin("400", "tg") is False
    assert bot._is_admin("anyone", "wecom") is True
    assert bot._is_admin("100", "unknown") is False


def test_handle_message_routes_commands_through_legacy_wrappers(monkeypatch):
    monkeypatch.setattr(bot_service, "get_tg_chat_id", lambda: "admin")
    bot = bot_service.NotificationBot()
    calls = []

    bot._cmd_check = lambda cid, platform: calls.append(("check", cid, platform))
    bot._cmd_search = lambda cid, text, platform: calls.append(("search", cid, text, platform))
    bot._cmd_stats = lambda cid, period, platform: calls.append(("stats", cid, period, platform))
    bot._cmd_now = lambda cid, platform: calls.append(("now", cid, platform))
    bot._cmd_latest = lambda cid, platform: calls.append(("latest", cid, platform))
    bot._cmd_recent = lambda cid, platform: calls.append(("recent", cid, platform))
    bot._cmd_calendar = lambda cid, platform: calls.append(("calendar", cid, platform))
    bot._cmd_emby_restart = lambda cid, text, platform: calls.append(("emby_restart", cid, text, platform))
    bot._cmd_whois = lambda cid, text, platform: calls.append(("whois", cid, text, platform))
    bot._cmd_help = lambda cid, platform: calls.append(("help", cid, platform))

    messages = [
        "/check",
        "/search Matrix",
        "/stats",
        "/weekly",
        "/monthly",
        "/yearly",
        "/now",
        "/latest",
        "/recent",
        "/calendar",
        "/emby_restart all",
        "/whois alice",
        "/help",
    ]
    for message in messages:
        bot._handle_message(message, "chat-1", "tg")

    assert calls == [
        ("check", "chat-1", "tg"),
        ("search", "chat-1", "/search Matrix", "tg"),
        ("stats", "chat-1", "day", "tg"),
        ("stats", "chat-1", "week", "tg"),
        ("stats", "chat-1", "month", "tg"),
        ("stats", "chat-1", "year", "tg"),
        ("now", "chat-1", "tg"),
        ("latest", "chat-1", "tg"),
        ("recent", "chat-1", "tg"),
        ("calendar", "chat-1", "tg"),
        ("emby_restart", "chat-1", "/emby_restart all", "tg"),
        ("whois", "chat-1", "/whois alice", "tg"),
        ("help", "chat-1", "tg"),
    ]


def test_handle_message_reply_mode_takes_precedence_over_command(monkeypatch):
    bot = bot_service.NotificationBot()
    calls = []
    bot._msg_reply_mode["chat-1"] = "user-1"
    bot._handle_msg_reply_message = lambda text, cid: calls.append(("reply", text, cid))
    bot._cmd_help = lambda *args: calls.append(("help", *args))

    bot._handle_message("  /help  ", "chat-1", "tg")

    assert calls == [("reply", "/help", "chat-1")]


def test_non_admin_plain_message_logs_warning_without_publish(monkeypatch):
    fake_bus = FakeBus()
    fake_logger = FakeLogger()
    monkeypatch.setattr(bot_service, "bus", fake_bus)
    monkeypatch.setattr(bot_service, "logger", fake_logger)
    monkeypatch.setattr(bot_service, "get_tg_chat_id", lambda: "admin")

    bot = bot_service.NotificationBot()

    bot._handle_message("  hello users  ", "guest", "tg")

    assert fake_logger.warnings == ["[Bot] 非管理员用户尝试发送非命令消息: guest"]
    assert fake_logger.infos == []
    assert fake_bus.published == []


def test_admin_plain_message_logs_and_publishes_event(monkeypatch):
    fake_bus = FakeBus()
    fake_logger = FakeLogger()
    monkeypatch.setattr(bot_service, "bus", fake_bus)
    monkeypatch.setattr(bot_service, "logger", fake_logger)
    monkeypatch.setattr(bot_service, "get_tg_chat_id", lambda: "admin")

    bot = bot_service.NotificationBot()

    bot._handle_message("  broadcast text  ", "admin", "tg")

    assert fake_logger.warnings == []
    assert fake_logger.infos == ["[Bot] 非命令消息，发布到事件总线: broadcast text..."]
    assert fake_bus.published == [("bot.admin_message", "broadcast text", "admin", "tg")]
