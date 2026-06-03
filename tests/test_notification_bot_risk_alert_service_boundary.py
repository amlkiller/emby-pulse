import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeLogger:
    def __init__(self):
        self.errors = []

    def error(self, message):
        self.errors.append(message)


def test_risk_alert_uses_legacy_providers_and_sends_actionable_keyboard(monkeypatch):
    from app.bot.notification_bot import bot_service

    sent = []
    notifications = []
    bot = bot_service.NotificationBot()
    bot.send_message = lambda chat_id, text, reply_markup=None, platform="all": sent.append(
        (chat_id, text, reply_markup, platform)
    )

    monkeypatch.setattr(bot_service, "get_pulse_url", lambda: "https://pulse.example/")
    monkeypatch.setattr(bot_service, "get_media_server_main_public_or_host", lambda: "https://fallback.example")
    monkeypatch.setattr(
        bot_service,
        "add_system_notification",
        lambda **kwargs: notifications.append(kwargs),
    )

    bot.on_risk_alert(
        {
            "user_id": "u-1",
            "username": "alice",
            "current": 4,
            "limit": 2,
            "devices_info": "TV\nPhone",
            "violation_action": "warn_user",
        }
    )

    assert len(sent) == 1
    chat_id, text, reply_markup, platform = sent[0]
    assert chat_id == "sys_notify"
    assert platform == "all"
    assert "【风控预警】 账号并发越界" in text
    assert "涉事用户：</b>alice" in text
    assert "当前并发：</b>4 / 额度 2" in text
    assert "TV\nPhone" in text
    assert "处理方式：</b>📢 已警告用户" in text
    assert reply_markup == {
        "inline_keyboard": [
            [{"text": "🚫 立即封禁此违规账号", "callback_data": "risk_ban_u-1"}],
            [{"text": "🛡️ 前往风控大盘拔网线", "url": "https://pulse.example/risk"}],
        ]
    }
    assert notifications == [
        {
            "notify_type": "risk",
            "title": "🚨 并发越界: alice",
            "message": "当前并发 4 / 额度 2，处理: 📢 已警告用户",
            "action_url": "/risk",
        }
    ]


def test_risk_alert_omits_ban_for_auto_ban_and_uses_admin_url_fallback(monkeypatch):
    from app.bot.notification_bot import bot_service

    sent = []
    bot = bot_service.NotificationBot()
    bot.send_message = lambda chat_id, text, reply_markup=None, platform="all": sent.append(
        (chat_id, text, reply_markup, platform)
    )

    monkeypatch.setattr(bot_service, "get_pulse_url", lambda: "")
    monkeypatch.setattr(bot_service, "get_media_server_main_public_or_host", lambda: "https://media.example")
    monkeypatch.setattr(bot_service, "add_system_notification", lambda **_kwargs: None)

    bot.on_risk_alert({"user_id": "u-2", "username": "bob", "violation_action": "auto_ban"})

    assert len(sent) == 1
    _chat_id, text, reply_markup, _platform = sent[0]
    assert "处理方式：</b>🚫 已自动封禁" in text
    assert reply_markup == {
        "inline_keyboard": [
            [{"text": "🛡️ 前往风控大盘拔网线", "url": "https://media.example/risk"}],
        ]
    }


def test_risk_alert_preserves_defaults_no_keyboard_and_logs_persistence_errors(monkeypatch):
    from app.bot.notification_bot import bot_service

    sent = []
    logger = FakeLogger()
    bot = bot_service.NotificationBot()
    bot.send_message = lambda chat_id, text, reply_markup=None, platform="all": sent.append(
        (chat_id, text, reply_markup, platform)
    )

    def raising_notification(**_kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(bot_service, "get_pulse_url", lambda: "")
    monkeypatch.setattr(bot_service, "get_media_server_main_public_or_host", lambda: "")
    monkeypatch.setattr(bot_service, "add_system_notification", raising_notification)
    monkeypatch.setattr(bot_service, "logger", logger)

    bot.on_risk_alert({})

    assert len(sent) == 1
    chat_id, text, reply_markup, platform = sent[0]
    assert chat_id == "sys_notify"
    assert platform == "all"
    assert "涉事用户：</b>未知" in text
    assert "当前并发：</b>0 / 额度 0" in text
    assert "违规设备：</b>\n未知设备" in text
    assert "处理方式：</b>🔔 仅提醒管理员" in text
    assert reply_markup is None
    assert logger.errors == ["写入风控通知失败: db down"]
