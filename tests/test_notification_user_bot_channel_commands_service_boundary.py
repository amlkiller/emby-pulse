import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeLogger:
    def __init__(self):
        self.calls = []

    def error(self, message):
        self.calls.append(("error", message))


def _reset_channel_command_state(monkeypatch):
    from tests.user_bot_worker_boundary import user_bot_worker_boundary as user_bot_service

    sent = []
    bind_calls = []
    unbind_calls = []
    logger = FakeLogger()
    binding = {"emby_username": "Alice"}

    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: binding)
    monkeypatch.setattr(user_bot_service, "_send", lambda chat_id, text, reply_markup=None: sent.append((chat_id, text, reply_markup)))
    monkeypatch.setattr(
        user_bot_service,
        "_bind_channel",
        lambda channel_id, tg_user_id, channel_title="": bind_calls.append((channel_id, tg_user_id, channel_title)) or True,
    )
    monkeypatch.setattr(user_bot_service, "_unbind_channel", lambda channel_id: unbind_calls.append(channel_id) or True)
    monkeypatch.setattr(user_bot_service, "safe_error_message", lambda exc, fallback: f"safe:{fallback}")
    monkeypatch.setattr(user_bot_service, "logger", logger)

    return user_bot_service, sent, bind_calls, unbind_calls, logger


def test_cmd_bind_channel_requires_binding_and_args(monkeypatch):
    user_bot_service, sent, bind_calls, _unbind_calls, _logger = _reset_channel_command_state(monkeypatch)

    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: None)
    user_bot_service.cmd_bind_channel(10, "tg1", "-1001")
    assert sent[-1] == (10, "❌ 请先绑定 Emby 账号后再绑定频道", None)
    assert bind_calls == []

    sent.clear()
    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: {"emby_username": "Alice"})
    user_bot_service.cmd_bind_channel(10, "tg1", "")
    assert sent == [(
        10,
        "💡 使用方法：/bind_channel 频道ID\n\n获取频道ID：\n1. 将频道消息转发给 @userinfobot\n2. 或查看频道链接中的数字\n\n示例：/bind_channel -1001234567890",
        None,
    )]
    assert bind_calls == []


def test_cmd_bind_channel_success_and_failure_use_runtime_binding_provider(monkeypatch):
    user_bot_service, sent, bind_calls, _unbind_calls, _logger = _reset_channel_command_state(monkeypatch)

    user_bot_service.cmd_bind_channel(10, "tg1", " -100123 extra ")

    assert bind_calls == [("-100123", "tg1", "")]
    assert sent == [(
        10,
        "✅ 频道绑定成功！\n\n频道ID：<code>-100123</code>\n绑定账号：<b>Alice</b>\n\n现在用频道身份发送命令将使用此账号",
        None,
    )]

    sent.clear()
    monkeypatch.setattr(user_bot_service, "_bind_channel", lambda _channel_id, _tg_user_id, _channel_title="": False)
    user_bot_service.cmd_bind_channel(10, "tg1", "-100123")
    assert sent == [(10, "❌ 绑定失败，请稍后重试", None)]


def test_cmd_bind_channel_errors_are_logged_and_sanitized(monkeypatch):
    user_bot_service, sent, _bind_calls, _unbind_calls, logger = _reset_channel_command_state(monkeypatch)

    def raise_bind(_channel_id, _tg_user_id, _channel_title=""):
        raise RuntimeError("raw channel failure")

    monkeypatch.setattr(user_bot_service, "_bind_channel", raise_bind)

    user_bot_service.cmd_bind_channel(10, "tg1", "-100123")

    assert logger.calls == [("error", "[频道绑定] 执行失败: raw channel failure")]
    assert sent == [(10, "❌ 绑定失败：safe:频道绑定异常，请稍后重试", None)]


def test_cmd_unbind_channel_preserves_usage_success_and_failure(monkeypatch):
    user_bot_service, sent, _bind_calls, unbind_calls, _logger = _reset_channel_command_state(monkeypatch)

    user_bot_service.cmd_unbind_channel(10, "tg1", "")
    assert sent[-1] == (10, "💡 使用方法：/unbind_channel 频道ID", None)
    assert unbind_calls == []

    user_bot_service.cmd_unbind_channel(10, "tg1", " -100123 extra ")
    assert unbind_calls == ["-100123"]
    assert sent[-1] == (10, "✅ 频道 <code>-100123</code> 已解绑", None)

    monkeypatch.setattr(user_bot_service, "_unbind_channel", lambda _channel_id: False)
    user_bot_service.cmd_unbind_channel(10, "tg1", "-100123")
    assert sent[-1] == (10, "❌ 解绑失败", None)
