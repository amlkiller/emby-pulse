import datetime as real_datetime
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeLogger:
    def __init__(self):
        self.infos = []
        self.errors = []

    def info(self, message):
        self.infos.append(message)

    def error(self, message):
        self.errors.append(message)


class FakeDateTime:
    @classmethod
    def now(cls):
        return real_datetime.datetime(2026, 6, 3, 20, 15, 30)


class FakeDateTimeModule:
    datetime = FakeDateTime


def test_user_login_sends_photo_and_web_notification_through_legacy_entry(monkeypatch):
    from app.domains.notifications import bot_service

    sent = []
    notifications = []
    bot = bot_service.NotificationBot()
    bot._is_muted = lambda user_id, event_type: False
    bot._download_user_image = lambda user_id: "avatar-bytes"
    bot.send_photo = lambda chat_id, image, text, platform="all", wecom_photo_io=None, **_kwargs: sent.append(
        (chat_id, image, text, platform, wecom_photo_io)
    )

    monkeypatch.setattr(bot_service, "get_notify_rule", lambda rule_type: {"enabled": True, "channels": ["tg_bot", "wecom", "web"]})
    monkeypatch.setattr(bot_service, "get_location", lambda ip: "Shanghai")
    monkeypatch.setattr(bot_service, "add_system_notification", lambda *args: notifications.append(args))
    monkeypatch.setattr(bot_service, "datetime", FakeDateTimeModule)

    bot.on_user_login(
        {
            "User": {"Id": "u-1", "Name": "Alice"},
            "Session": {
                "RemoteEndPoint": "1.2.3.4",
                "Client": "Emby Web",
                "DeviceName": "Chrome",
            },
        }
    )

    assert len(sent) == 1
    chat_id, image, text, platform, wecom_photo_io = sent[0]
    assert chat_id == "sys_notify"
    assert image == "avatar-bytes"
    assert wecom_photo_io == "avatar-bytes"
    assert platform == "all"
    assert "安全预警：账号登录" in text
    assert "用户：</b>Alice" in text
    assert "网络：</b>1.2.3.4 (Shanghai)" in text
    assert "设备：</b>Emby Web (Chrome)" in text
    assert "时间：</b>2026-06-03 20:15:30" in text
    assert notifications == [
        ("user", "用户登录: Alice", "1.2.3.4 (Shanghai) - Emby Web", "/users_manage")
    ]


def test_user_login_disabled_rule_skips_without_legacy_fallback(monkeypatch):
    from app.domains.notifications import bot_service

    sent = []
    bot = bot_service.NotificationBot()
    bot.send_photo = lambda *args, **kwargs: sent.append((args, kwargs))

    monkeypatch.setattr(bot_service, "get_notify_rule", lambda _rule_type: {"enabled": False, "channels": ["tg_bot"]})
    monkeypatch.setattr(bot_service, "get_notify_user_login", lambda: True)

    bot.on_user_login({"User": {"Id": "u-1", "Name": "Alice"}})

    assert sent == []


def test_user_login_rule_lookup_failure_uses_legacy_switch_and_fallback_avatar(monkeypatch):
    from app.domains.notifications import bot_service

    sent = []
    bot = bot_service.NotificationBot()
    bot._is_muted = lambda user_id, event_type: False
    bot._download_user_image = lambda user_id: None
    bot.send_photo = lambda chat_id, image, text, platform="all", wecom_photo_io=None, **_kwargs: sent.append(
        (chat_id, image, text, platform, wecom_photo_io)
    )

    monkeypatch.setattr(bot_service, "get_notify_rule", lambda _rule_type: (_ for _ in ()).throw(RuntimeError("rule down")))
    monkeypatch.setattr(bot_service, "get_notify_user_login", lambda: True)
    monkeypatch.setattr(bot_service, "get_location", lambda ip: "Local")
    monkeypatch.setattr(bot_service, "datetime", FakeDateTimeModule)

    bot.on_user_login({"UserId": "u-2", "Title": "Alice Zhang", "RemoteEndPoint": "5.6.7.8"})

    assert len(sent) == 1
    chat_id, image, text, platform, wecom_photo_io = sent[0]
    assert chat_id == "sys_notify"
    assert image == "https://api.dicebear.com/9.x/notionists/png?seed=Alice%20Zhang"
    assert wecom_photo_io == image
    assert platform == "all"
    assert "用户：</b>Alice Zhang" in text
    assert "网络：</b>5.6.7.8 (Local)" in text


def test_user_login_rule_lookup_failure_respects_legacy_disabled_switch(monkeypatch):
    from app.domains.notifications import bot_service

    sent = []
    bot = bot_service.NotificationBot()
    bot.send_photo = lambda *args, **kwargs: sent.append((args, kwargs))

    monkeypatch.setattr(bot_service, "get_notify_rule", lambda _rule_type: (_ for _ in ()).throw(RuntimeError("rule down")))
    monkeypatch.setattr(bot_service, "get_notify_user_login", lambda: False)

    bot.on_user_login({"User": {"Id": "u-1", "Name": "Alice"}})

    assert sent == []


def test_user_login_mute_check_logs_and_skips_send(monkeypatch):
    from app.domains.notifications import bot_service

    sent = []
    logger = FakeLogger()
    bot = bot_service.NotificationBot()
    bot._is_muted = lambda user_id, event_type: True
    bot.send_photo = lambda *args, **kwargs: sent.append((args, kwargs))

    monkeypatch.setattr(bot_service, "get_notify_rule", lambda _rule_type: {"enabled": True, "channels": ["tg_bot"]})
    monkeypatch.setattr(bot_service, "logger", logger)

    bot.on_user_login({"User": {"Id": "u-1", "Name": "Muted User"}})

    assert sent == []
    assert logger.infos == ["🔇 [静音规则] 拦截了用户 Muted User 的登录通知"]
    assert logger.errors == []


def test_user_login_send_failure_logs_and_falls_back_to_all_platform(monkeypatch):
    from app.domains.notifications import bot_service

    sent = []
    logger = FakeLogger()
    bot = bot_service.NotificationBot()
    bot._is_muted = lambda user_id, event_type: False
    bot._download_user_image = lambda user_id: "avatar-bytes"

    def send_photo(chat_id, image, text, platform="all", wecom_photo_io=None, **_kwargs):
        if not sent:
            sent.append((chat_id, image, text, platform, wecom_photo_io, "raised"))
            raise RuntimeError("send down")
        sent.append((chat_id, image, text, platform, wecom_photo_io, "fallback"))

    bot.send_photo = send_photo

    monkeypatch.setattr(bot_service, "get_notify_rule", lambda _rule_type: {"enabled": True, "channels": ["tg_bot"]})
    monkeypatch.setattr(bot_service, "get_location", lambda ip: "Local")
    monkeypatch.setattr(bot_service, "logger", logger)
    monkeypatch.setattr(bot_service, "datetime", FakeDateTimeModule)

    bot.on_user_login({"User": {"Id": "u-1", "Name": "Alice"}})

    assert len(sent) == 2
    assert sent[0][3] == "tg"
    assert sent[0][5] == "raised"
    assert sent[1][3] == "all"
    assert sent[1][5] == "fallback"
    assert logger.errors == ["[用户登录通知] 发送失败: send down"]
