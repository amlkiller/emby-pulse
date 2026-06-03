import io
import json
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.bot.notification_bot import bot_service


class FakeResponse:
    def __init__(self, status_code=200, text="ok"):
        self.status_code = status_code
        self.text = text


class FakeLogger:
    def __init__(self):
        self.infos = []
        self.warnings = []
        self.errors = []

    def info(self, message):
        self.infos.append(message)

    def warning(self, message):
        self.warnings.append(message)

    def error(self, message):
        self.errors.append(message)


class FakeTelegramClient:
    def __init__(self):
        self.calls = []

    def send_photo(self, token, data=None, files=None, proxies=None, timeout=None):
        self.calls.append(("send_photo", token, data, files, proxies, timeout))
        return FakeResponse()

    def send_message(self, token, data, proxies=None, timeout=None):
        self.calls.append(("send_message", token, data, proxies, timeout))
        return FakeResponse()


def test_notification_bot_send_to_channel_uses_legacy_module_dependencies(monkeypatch):
    fake_client = FakeTelegramClient()
    fake_logger = FakeLogger()
    photo = io.BytesIO(b"image-bytes")
    photo.seek(3)

    monkeypatch.setattr(bot_service, "telegram_client", fake_client)
    monkeypatch.setattr(bot_service, "logger", fake_logger)
    monkeypatch.setattr(bot_service, "get_notify_tg_bot_token", lambda: "tg-token")
    monkeypatch.setattr(bot_service, "get_safe_proxies", lambda: {"https": "proxy"})

    bot = bot_service.NotificationBot()
    bot._send_to_channel("channel-1", photo, "caption", {"inline_keyboard": [[{"text": "Open", "url": "https://x"}]]})
    bot._send_to_channel("channel-2", None, "text", None)

    assert fake_client.calls[0][0] == "send_photo"
    assert fake_client.calls[0][1] == "tg-token"
    assert fake_client.calls[0][2]["chat_id"] == "channel-1"
    assert fake_client.calls[0][2]["caption"] == "caption"
    assert json.loads(fake_client.calls[0][2]["reply_markup"]) == {
        "inline_keyboard": [[{"text": "Open", "url": "https://x"}]]
    }
    assert fake_client.calls[0][3]["photo"][1] is photo
    assert fake_client.calls[0][4] == {"https": "proxy"}
    assert photo.tell() == 0

    assert fake_client.calls[1] == (
        "send_message",
        "tg-token",
        {"chat_id": "channel-2", "text": "text", "parse_mode": "HTML"},
        {"https": "proxy"},
        30,
    )
    assert fake_logger.errors == []


def test_notification_bot_send_to_channels_filters_and_sends_enabled_channels(monkeypatch):
    fake_client = FakeTelegramClient()
    fake_logger = FakeLogger()
    channels = [
        {"name": "enabled-a", "chat_id": "channel-a", "enabled": True},
        {"name": "disabled", "chat_id": "channel-disabled", "enabled": False},
        {"name": "missing-chat", "enabled": True},
        {"name": "enabled-b", "chat_id": "channel-b"},
    ]

    monkeypatch.setattr(bot_service, "telegram_client", fake_client)
    monkeypatch.setattr(bot_service, "logger", fake_logger)
    monkeypatch.setattr(bot_service, "get_notify_channels", lambda: json.dumps(channels))
    monkeypatch.setattr(bot_service, "get_notify_tg_bot_token", lambda: "tg-token")
    monkeypatch.setattr(bot_service, "get_safe_proxies", lambda: None)

    bot = bot_service.NotificationBot()
    bot.send_to_channels(None, "caption", keyboard={"inline_keyboard": []})

    sent_chat_ids = [call[2]["chat_id"] for call in fake_client.calls]
    assert sent_chat_ids == ["channel-a", "channel-b"]
    assert fake_logger.infos[0] == "📢 [频道通知] 准备推送到 3 个频道"
    assert "enabled-a" in fake_logger.infos[1]
    assert "enabled-b" in fake_logger.infos[2]


def test_notification_bot_notify_channels_applies_item_type_filter_and_omits_keyboard(monkeypatch):
    fake_client = FakeTelegramClient()
    channels = [
        {"name": "movies", "chat_id": "channel-movie", "notify_types": ["movie"]},
        {"name": "episodes", "chat_id": "channel-episode", "notify_types": ["episode"]},
        {"name": "disabled", "chat_id": "channel-disabled", "enabled": False, "notify_types": ["episode"]},
    ]

    monkeypatch.setattr(bot_service, "telegram_client", fake_client)
    monkeypatch.setattr(bot_service, "logger", FakeLogger())
    monkeypatch.setattr(bot_service, "get_notify_channels", lambda: json.dumps(channels))
    monkeypatch.setattr(bot_service, "get_notify_tg_bot_token", lambda: "tg-token")
    monkeypatch.setattr(bot_service, "get_safe_proxies", lambda: None)

    bot = bot_service.NotificationBot()
    bot._notify_channels(None, "caption", {"inline_keyboard": [[{"text": "hidden"}]]}, "episode", {"Id": "item-1"})

    assert len(fake_client.calls) == 1
    assert fake_client.calls[0][2] == {
        "chat_id": "channel-episode",
        "text": "caption",
        "parse_mode": "HTML",
    }
