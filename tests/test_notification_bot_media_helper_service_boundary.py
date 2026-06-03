import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.bot.notification_bot import bot_service


class FakeResponse:
    def __init__(self, status_code=200, payload=None, content=b""):
        self.status_code = status_code
        self._payload = payload or {}
        self.content = content

    def json(self):
        return self._payload


class FakeMediaApi:
    def __init__(self):
        self.calls = []
        self.users_payload = [{"Id": "u1", "Name": "Alice"}, {"Id": "u2", "Name": "Bob"}]

    def get(self, path, params=None, timeout=None):
        self.calls.append((path, params, timeout))
        if path == "/Users":
            return FakeResponse(payload=self.users_payload)
        if path == "/Users/u1/Images/Primary":
            return FakeResponse(content=b"user-image")
        if path == "/Items/item-1/Images/Backdrop":
            return FakeResponse(content=b"item-image")
        return FakeResponse(status_code=404)


class FakeLogger:
    def __init__(self):
        self.errors = []

    def error(self, message):
        self.errors.append(message)


def test_media_helper_downloads_user_and_item_images_through_legacy_media_api(monkeypatch):
    fake_media = FakeMediaApi()
    monkeypatch.setattr(bot_service, "media_api", fake_media)

    bot = bot_service.NotificationBot()

    user_image = bot._download_user_image("u1")
    item_image = bot._download_emby_image("item-1", "Backdrop", image_tag="tag-1")

    assert user_image.read() == b"user-image"
    assert item_image.read() == b"item-image"
    assert fake_media.calls == [
        ("/Users/u1/Images/Primary", {"maxHeight": 400, "maxWidth": 400, "quality": 90}, 5),
        ("/Items/item-1/Images/Backdrop", {"maxHeight": 800, "maxWidth": 600, "quality": 90, "tag": "tag-1"}, 15),
    ]
    assert bot._download_user_image("") is None
    assert bot._download_emby_image("") is None


def test_media_helper_username_cache_fills_once_and_falls_back(monkeypatch):
    fake_media = FakeMediaApi()
    monkeypatch.setattr(bot_service, "media_api", fake_media)

    bot = bot_service.NotificationBot()

    assert bot._get_username("u2") == "Bob"
    assert bot.user_cache == {"u1": "Alice", "u2": "Bob"}
    assert bot._get_username("u1") == "Alice"
    assert bot._get_username("missing") == "Unknown User"
    user_calls = [call for call in fake_media.calls if call[0] == "/Users"]
    assert user_calls == [("/Users", None, 2), ("/Users", None, 2)]


def test_media_helper_subnet_key_preserves_ipv4_and_groups_ipv6():
    bot = bot_service.NotificationBot()

    assert bot._get_subnet_key("192.168.1.10") == "192.168.1.10"
    assert bot._get_subnet_key("2001:db8:abcd:0012:0000:0000:0000:0001") == "2001:0db8:abcd:0012::/64"
    assert bot._get_subnet_key("not-an-ip") == "not-an-ip"


def test_media_helper_save_playback_history_uses_legacy_providers(monkeypatch):
    fake_logger = FakeLogger()
    insert_calls = []
    monkeypatch.setattr(bot_service, "logger", fake_logger)
    monkeypatch.setattr(bot_service, "get_isp", lambda ip: f"isp:{ip}")
    monkeypatch.setattr(
        bot_service,
        "insert_bot_playback_history_record",
        lambda *args: insert_calls.append(args),
    )

    bot = bot_service.NotificationBot()
    bot._save_playback_history(
        {"Session": {"Client": "Infuse", "DeviceName": "iPad"}},
        "u1",
        "Alice",
        {"Id": "item-1", "Name": "Movie", "Type": "Movie"},
        "1.2.3.4",
        "Shanghai",
    )

    assert insert_calls == [
        ("u1", "Alice", "item-1", "Movie", "Movie", "Infuse", "iPad", "1.2.3.4", "Shanghai", "isp:1.2.3.4")
    ]
    assert fake_logger.errors == []
