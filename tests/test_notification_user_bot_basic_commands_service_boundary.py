import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeResponse:
    def __init__(self, status_code=200, user=None):
        self.status_code = status_code
        self.user = user or {"Id": "u1", "Name": "Alice"}

    def json(self):
        return {"User": self.user}


class FakeMediaApi:
    def __init__(self, response=None, error=None):
        self.response = response or FakeResponse()
        self.error = error
        self.calls = []

    def authenticate_by_name(self, username, password, timeout=None):
        self.calls.append((username, password, timeout))
        if self.error:
            raise self.error
        return self.response


class FakeLogger:
    def __init__(self):
        self.calls = []

    def error(self, message):
        self.calls.append(("error", message))


def _reset_basic_command_state(monkeypatch):
    from app.domains.notifications import user_bot_service

    sent = []
    recorded = []
    bound = []
    logger = FakeLogger()

    monkeypatch.setattr(user_bot_service, "_user_state", {})
    monkeypatch.setattr(user_bot_service, "_record_bot_user", lambda tg_user_id, tg_name: recorded.append((tg_user_id, tg_name)))
    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: None)
    monkeypatch.setattr(
        user_bot_service,
        "_bind_user",
        lambda tg_user_id, uid, uname, init_password="", tg_username="", tg_display_name="": bound.append(
            (tg_user_id, uid, uname, init_password, tg_username, tg_display_name)
        ),
    )
    monkeypatch.setattr(user_bot_service, "_is_blacklisted", lambda _tg_user_id: False)
    monkeypatch.setattr(user_bot_service, "_send", lambda chat_id, text, reply_markup=None: sent.append((chat_id, text, reply_markup)))
    monkeypatch.setattr(user_bot_service, "_main_menu_keyboard", lambda binding=None: {"menu": binding})
    monkeypatch.setattr(user_bot_service, "is_user_bot_open_reg_enabled", lambda: True)
    monkeypatch.setattr(user_bot_service, "safe_error_message", lambda exc, fallback: f"safe:{fallback}")
    monkeypatch.setattr(user_bot_service, "logger", logger)
    monkeypatch.setattr(user_bot_service, "media_api", FakeMediaApi())
    return user_bot_service, sent, recorded, bound, logger


def test_cmd_start_records_user_and_sends_unbound_menu_through_legacy_wrapper(monkeypatch):
    user_bot_service, sent, recorded, _bound, _logger = _reset_basic_command_state(monkeypatch)

    user_bot_service.cmd_start(10, "tg1", "Alice TG")

    assert recorded == [("tg1", "Alice TG")]
    assert sent == [(
        10,
        "👋 你好 <b>Alice TG</b>！\n\n🎬 这是 <b>EmbyPulse</b> 用户自助服务机器人\n\n你还没有绑定账号，请先完成绑定或注册：",
        {"menu": None},
    )]


def test_cmd_help_uses_binding_status_and_menu_through_legacy_wrapper(monkeypatch):
    user_bot_service, sent, _recorded, _bound, _logger = _reset_basic_command_state(monkeypatch)
    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: {"emby_username": "Alice"})

    user_bot_service.cmd_help(10, "tg1")

    assert sent[0][0] == 10
    assert "✅ 已绑定：<b>Alice</b>" in sent[0][1]
    assert "/bind 用户名 — 绑定 Emby 账号" in sent[0][1]
    assert sent[0][2] == {"menu": {"emby_username": "Alice"}}


def test_cmd_bind_authenticates_binds_and_sends_success(monkeypatch):
    user_bot_service, sent, _recorded, bound, _logger = _reset_basic_command_state(monkeypatch)
    media_api = FakeMediaApi(FakeResponse(user={"Id": "u2", "Name": "Bob"}))
    monkeypatch.setattr(user_bot_service, "media_api", media_api)

    user_bot_service.cmd_bind(10, "tg1", "bob secret", tg_username="bob_tg", tg_display_name="Bob TG")

    assert media_api.calls == [("bob", "secret", 10)]
    assert bound == [("tg1", "u2", "Bob", "", "bob_tg", "Bob TG")]
    assert sent == [(
        10,
        "✅ <b>绑定成功！</b>\n\n👤 Emby 账号：<b>Bob</b>\n\n发送 /menu 打开主菜单",
        {"menu": {"emby_user_id": "u2", "emby_username": "Bob"}},
    )]


def test_cmd_bind_errors_are_logged_and_sanitized(monkeypatch):
    user_bot_service, sent, _recorded, bound, logger = _reset_basic_command_state(monkeypatch)
    monkeypatch.setattr(user_bot_service, "media_api", FakeMediaApi(error=RuntimeError("raw secret")))

    user_bot_service.cmd_bind(10, "tg1", "bob secret")

    assert bound == []
    assert logger.calls == [("error", "[绑定] Emby绑定失败: raw secret")]
    assert sent == [(10, "❌ 绑定失败：safe:绑定操作异常，请稍后重试", None)]


def test_cmd_register_sets_legacy_user_state_when_allowed(monkeypatch):
    user_bot_service, sent, _recorded, _bound, _logger = _reset_basic_command_state(monkeypatch)

    user_bot_service.cmd_register(10, "tg1", "Alice TG")

    assert user_bot_service._user_state == {"tg1": {"action": "register_name"}}
    assert sent == [(
        10,
        "🆕 <b>注册新账号</b>\n\n请输入你想要的用户名（支持字母、数字、中文、下划线(_)、连字符(-)、@、.）：",
        {"inline_keyboard": [[{"text": "❌ 取消", "callback_data": "ub_cancel_state"}]]},
    )]


def test_cmd_register_preserves_guard_order(monkeypatch):
    user_bot_service, sent, _recorded, _bound, _logger = _reset_basic_command_state(monkeypatch)

    monkeypatch.setattr(user_bot_service, "is_user_bot_open_reg_enabled", lambda: False)
    user_bot_service.cmd_register(10, "tg1", "Alice TG")
    assert sent[-1] == (10, "❌ 开放注册未开启，请联系管理员获取注册码后使用 /code 注册码", None)

    sent.clear()
    monkeypatch.setattr(user_bot_service, "is_user_bot_open_reg_enabled", lambda: True)
    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: {"emby_username": "Alice"})
    user_bot_service.cmd_register(10, "tg1", "Alice TG")
    assert sent[-1] == (10, "❌ 你已经绑定了账号，无需重复注册", None)

    sent.clear()
    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: None)
    monkeypatch.setattr(user_bot_service, "_is_blacklisted", lambda _tg_user_id: True)
    user_bot_service.cmd_register(10, "tg1", "Alice TG")
    assert sent[-1] == (10, "🚫 你的账号已被管理员限制注册，如有疑问请联系管理员。\n\n如果你有注册码，可以使用 /code 注册码 进行注册。", None)
