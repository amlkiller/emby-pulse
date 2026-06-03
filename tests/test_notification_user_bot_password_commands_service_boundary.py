import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class FakeMediaApi:
    def __init__(self):
        self.auth_status = 200
        self.post_status = 204
        self.auth_error = None
        self.post_error = None
        self.auth_calls = []
        self.post_calls = []

    def authenticate_by_name(self, username, password, timeout=None):
        self.auth_calls.append((username, password, timeout))
        if self.auth_error:
            raise self.auth_error
        return FakeResponse(self.auth_status)

    def post(self, path, json=None, timeout=None):
        self.post_calls.append((path, json, timeout))
        if self.post_error:
            raise self.post_error
        return FakeResponse(self.post_status)


class FakeUserBotDao:
    def __init__(self):
        self.updated = []

    def update_binding_init_password(self, tg_user_id, init_password):
        self.updated.append((tg_user_id, init_password))


class FakeLogger:
    def __init__(self):
        self.calls = []

    def error(self, message):
        self.calls.append(("error", message))


def _reset_password_command_state(monkeypatch):
    from app.bot.user_bot import user_bot_service

    sent = []
    unbound = []
    media_api = FakeMediaApi()
    user_bot_dao = FakeUserBotDao()
    logger = FakeLogger()
    binding = {
        "emby_user_id": "u1",
        "emby_username": "Alice",
        "init_password": "old-init",
    }

    monkeypatch.setattr(user_bot_service, "_user_state", {})
    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: binding)
    monkeypatch.setattr(user_bot_service, "_check_emby_account", lambda _binding: True)
    monkeypatch.setattr(user_bot_service, "_unbind_user", lambda tg_user_id: unbound.append(tg_user_id))
    monkeypatch.setattr(user_bot_service, "_send", lambda chat_id, text, reply_markup=None: sent.append((chat_id, text, reply_markup)))
    monkeypatch.setattr(user_bot_service, "_main_menu_keyboard", lambda binding_arg=None: {"menu": binding_arg})
    monkeypatch.setattr(user_bot_service, "validate_password_strength", lambda password: (True, ""))
    monkeypatch.setattr(user_bot_service, "media_api", media_api)
    monkeypatch.setattr(user_bot_service, "user_bot_dao", user_bot_dao)
    monkeypatch.setattr(user_bot_service, "safe_error_message", lambda exc, fallback: f"safe:{fallback}")
    monkeypatch.setattr(user_bot_service, "logger", logger)
    return user_bot_service, sent, unbound, media_api, user_bot_dao, logger


def test_cmd_password_requires_binding_and_active_emby_account(monkeypatch):
    user_bot_service, sent, unbound, media_api, _dao, _logger = _reset_password_command_state(monkeypatch)

    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: None)
    user_bot_service.cmd_password(10, "tg1", "old NewPass1")
    assert sent == [(10, "❌ 请先绑定账号", None)]
    assert media_api.auth_calls == []

    sent.clear()
    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: {"emby_user_id": "u1", "emby_username": "Alice"})
    monkeypatch.setattr(user_bot_service, "_check_emby_account", lambda _binding: False)
    user_bot_service.cmd_password(10, "tg1", "old NewPass1")
    assert unbound == ["tg1"]
    assert sent == [(10, "⚠️ 你的 Emby 账号已被删除，绑定已自动解除。请联系管理员。", {"menu": None})]
    assert media_api.auth_calls == []


def test_cmd_password_step2_validates_and_sets_confirm_state(monkeypatch):
    user_bot_service, sent, _unbound, _media_api, _dao, _logger = _reset_password_command_state(monkeypatch)
    user_bot_service._user_state["tg1"] = {"action": "change_pwd_step2"}

    monkeypatch.setattr(user_bot_service, "validate_password_strength", lambda _password: (False, "密码太弱"))
    user_bot_service.cmd_password(10, "tg1", "weak")
    assert sent == [(10, "❌ 密码太弱，请重新输入：", None)]
    assert user_bot_service._user_state == {"tg1": {"action": "change_pwd_step2"}}

    sent.clear()
    monkeypatch.setattr(user_bot_service, "validate_password_strength", lambda _password: (True, ""))
    user_bot_service.cmd_password(10, "tg1", "NewPass1")
    assert user_bot_service._user_state == {"tg1": {"action": "change_pwd_confirm", "new_pwd": "NewPass1"}}
    assert sent == [(
        10,
        "🔐 <b>确认新密码</b>\n\n请再次输入新密码进行确认：",
        {"inline_keyboard": [[{"text": "❌ 取消", "callback_data": "ub_cancel_state"}]]},
    )]


def test_cmd_password_confirm_branch_clears_state_on_mismatch_and_success(monkeypatch):
    user_bot_service, sent, _unbound, media_api, _dao, _logger = _reset_password_command_state(monkeypatch)
    user_bot_service._user_state["tg1"] = {"action": "change_pwd_confirm", "new_pwd": "NewPass1"}

    user_bot_service.cmd_password(10, "tg1", "OtherPass1")
    assert user_bot_service._user_state == {}
    assert media_api.post_calls == []
    assert sent == [(
        10,
        "❌ 两次密码不一致，修改失败。",
        {"inline_keyboard": [[{"text": "🔙 返回", "callback_data": "ub_back_menu"}]]},
    )]

    sent.clear()
    user_bot_service._user_state["tg1"] = {"action": "change_pwd_confirm", "new_pwd": "NewPass1"}
    user_bot_service.cmd_password(10, "tg1", "NewPass1")
    assert user_bot_service._user_state == {}
    assert media_api.post_calls == [("/Users/u1/Password", {"NewPw": "NewPass1"}, 5)]
    assert sent == [(
        10,
        "✅ <b>密码修改成功！</b>\n\n新密码：<code>NewPass1</code>\n\n请妥善保管你的密码",
        {"inline_keyboard": [[{"text": "🔙 返回", "callback_data": "ub_back_menu"}]]},
    )]


def test_cmd_password_initial_flow_preserves_usage_validation_auth_and_update(monkeypatch):
    user_bot_service, sent, _unbound, media_api, user_bot_dao, _logger = _reset_password_command_state(monkeypatch)

    user_bot_service.cmd_password(10, "tg1", "")
    assert sent[-1] == (
        10,
        "🔐 <b>修改密码</b>\n\n请发送命令（当前密码和新密码用空格隔开）：\n<code>/password 当前密码 新密码</code>\n\n例如：<code>/password 当前密码 NewPass1</code>\n\n⚠️ 新密码至少 8 位，需包含小写字母 + 大写字母或数字",
        {"inline_keyboard": [[{"text": "❌ 取消", "callback_data": "ub_back_menu"}]]},
    )

    sent.clear()
    monkeypatch.setattr(user_bot_service, "validate_password_strength", lambda _password: (False, "密码太弱"))
    user_bot_service.cmd_password(10, "tg1", "old weak")
    assert sent == [(10, "❌ 密码太弱，请检查后重试", None)]
    assert media_api.auth_calls == []

    sent.clear()
    monkeypatch.setattr(user_bot_service, "validate_password_strength", lambda _password: (True, ""))
    media_api.auth_status = 401
    user_bot_service.cmd_password(10, "tg1", "old NewPass1")
    assert media_api.auth_calls == [("Alice", "old", 10)]
    assert sent == [(10, "❌ 当前密码错误，请检查后重试", None)]

    sent.clear()
    media_api.auth_status = 200
    user_bot_service.cmd_password(10, "tg1", "old NewPass1")
    assert media_api.post_calls == [("/Users/u1/Password", {"NewPw": "NewPass1"}, 10)]
    assert user_bot_dao.updated == [("tg1", "NewPass1")]
    assert sent == [(
        10,
        "✅ <b>密码修改成功！</b>\n\n新密码：<code>NewPass1</code>\n\n请妥善保管你的密码",
        {"inline_keyboard": [[{"text": "🔙 返回", "callback_data": "ub_back_menu"}]]},
    )]


def test_cmd_password_failures_are_logged_and_sanitized(monkeypatch):
    user_bot_service, sent, _unbound, media_api, _dao, logger = _reset_password_command_state(monkeypatch)

    user_bot_service._user_state["tg1"] = {"action": "change_pwd_confirm", "new_pwd": "NewPass1"}
    media_api.post_error = RuntimeError("raw confirm failure")
    user_bot_service.cmd_password(10, "tg1", "NewPass1")
    assert logger.calls == [("error", "[改密] 执行失败: raw confirm failure")]
    assert sent == [(10, "❌ 修改密码失败：safe:密码修改异常，请稍后重试", None)]
    assert user_bot_service._user_state == {}

    sent.clear()
    logger.calls.clear()
    media_api.post_error = None
    media_api.auth_error = RuntimeError("raw auth failure")
    user_bot_service.cmd_password(10, "tg1", "old NewPass1")
    assert logger.calls == [("error", "[设密] 执行失败: raw auth failure")]
    assert sent == [(10, "❌ 修改密码失败：safe:密码修改异常，请稍后重试", None)]
