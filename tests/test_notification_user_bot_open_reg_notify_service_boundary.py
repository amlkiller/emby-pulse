import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeNow:
    def strftime(self, _fmt):
        return "2026-06-03 14:30"


class FakeLogger:
    def __init__(self):
        self.calls = []

    def info(self, message):
        self.calls.append(("info", message))

    def warning(self, message):
        self.calls.append(("warning", message))

    def error(self, message):
        self.calls.append(("error", message))


def _reset_open_reg_notify_state(monkeypatch):
    from app.domains.notifications import user_bot_service

    logger = FakeLogger()
    monkeypatch.setattr(user_bot_service, "is_user_bot_open_reg_notify_user_enabled", lambda: False)
    monkeypatch.setattr(user_bot_service, "is_user_bot_open_reg_notify_group_enabled", lambda: False)
    monkeypatch.setattr(user_bot_service, "get_user_bot_allowed_groups", lambda: "")
    monkeypatch.setattr(user_bot_service, "_get_all_bot_users", lambda: [])
    monkeypatch.setattr(user_bot_service, "logger", logger)
    monkeypatch.setattr(
        user_bot_service,
        "datetime",
        SimpleNamespace(datetime=SimpleNamespace(now=lambda: FakeNow())),
    )
    return user_bot_service, logger


def test_open_reg_closed_notify_returns_when_all_notifications_disabled(monkeypatch):
    user_bot_service, logger = _reset_open_reg_notify_state(monkeypatch)
    sent = []

    monkeypatch.setattr(user_bot_service, "_send", lambda chat_id, text, reply_markup=None: sent.append((chat_id, text)))

    user_bot_service._send_open_reg_closed_notify("批次名额已满")

    assert sent == []
    assert logger.calls == []


def test_open_reg_closed_notify_sends_to_recorded_bot_users(monkeypatch):
    user_bot_service, _logger = _reset_open_reg_notify_state(monkeypatch)
    sent = []

    monkeypatch.setattr(user_bot_service, "is_user_bot_open_reg_notify_user_enabled", lambda: True)
    monkeypatch.setattr(user_bot_service, "_get_all_bot_users", lambda: [{"tg_user_id": "1001"}, {"tg_user_id": 1002}])
    monkeypatch.setattr(user_bot_service, "_send", lambda chat_id, text, reply_markup=None: sent.append((chat_id, text)))

    user_bot_service._send_open_reg_closed_notify("批次名额已满")

    assert [chat_id for chat_id, _text in sent] == [1001, 1002]
    assert all("📊 本次开放注册已圆满结束（批次名额已满）" in text for _chat_id, text in sent)
    assert all("⏰ 结束时间：2026-06-03 14:30" in text for _chat_id, text in sent)


def test_open_reg_closed_notify_sends_to_configured_groups(monkeypatch):
    user_bot_service, logger = _reset_open_reg_notify_state(monkeypatch)
    sent = []

    monkeypatch.setattr(user_bot_service, "is_user_bot_open_reg_notify_group_enabled", lambda: True)
    monkeypatch.setattr(user_bot_service, "get_user_bot_allowed_groups", lambda: " -1001 \n-1002\n-1003")
    monkeypatch.setattr(user_bot_service, "_send", lambda chat_id, text, reply_markup=None: sent.append((chat_id, text)))

    user_bot_service._send_open_reg_closed_notify("")

    assert [chat_id for chat_id, _text in sent] == [-1001, -1002, -1003]
    assert all("📊 本次开放注册已圆满结束\n" in text for _chat_id, text in sent)
    assert logger.calls == [
        ("info", "[开放注册通知] 已发送到群 -1001"),
        ("info", "[开放注册通知] 已发送到群 -1002"),
        ("info", "[开放注册通知] 已发送到群 -1003"),
    ]


def test_open_reg_closed_notify_logs_missing_group_config(monkeypatch):
    user_bot_service, logger = _reset_open_reg_notify_state(monkeypatch)

    monkeypatch.setattr(user_bot_service, "is_user_bot_open_reg_notify_group_enabled", lambda: True)
    monkeypatch.setattr(user_bot_service, "get_user_bot_allowed_groups", lambda: "")

    user_bot_service._send_open_reg_closed_notify("用户总数已达上限")

    assert logger.calls == [("warning", "[开放注册通知] 未配置群 ID，跳过群聊通知")]


def test_open_reg_closed_notify_swallows_send_failures(monkeypatch):
    user_bot_service, logger = _reset_open_reg_notify_state(monkeypatch)
    sent = []

    monkeypatch.setattr(user_bot_service, "is_user_bot_open_reg_notify_user_enabled", lambda: True)
    monkeypatch.setattr(user_bot_service, "is_user_bot_open_reg_notify_group_enabled", lambda: True)
    monkeypatch.setattr(user_bot_service, "_get_all_bot_users", lambda: [{"tg_user_id": "1001"}, {"tg_user_id": "1002"}])
    monkeypatch.setattr(user_bot_service, "get_user_bot_allowed_groups", lambda: "-1001\n-1002")

    def fake_send(chat_id, text, reply_markup=None):
        sent.append((chat_id, text))
        if chat_id in {1001, -1001}:
            raise RuntimeError(f"send failed {chat_id}")

    monkeypatch.setattr(user_bot_service, "_send", fake_send)

    user_bot_service._send_open_reg_closed_notify("批次名额已满")

    assert [chat_id for chat_id, _text in sent] == [1001, 1002, -1001, -1002]
    assert logger.calls == [
        ("error", "[开放注册通知] 发送给用户 1001 失败: send failed 1001"),
        ("error", "[开放注册通知] 发送到群 -1001 失败: send failed -1001"),
        ("info", "[开放注册通知] 已发送到群 -1002"),
    ]
