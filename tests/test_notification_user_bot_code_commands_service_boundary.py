import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeInvitationDao:
    def __init__(self):
        self.registration_row = None
        self.registration_error = None
        self.renew_result = (None, "invalid")
        self.renew_error = None
        self.restored = []
        self.renew_calls = []

    def get_available_registration_invitation(self, code):
        if self.registration_error:
            raise self.registration_error
        return self.registration_row

    def restore_invitation_code_usage(self, code):
        if code == "fail":
            raise RuntimeError("restore failed")
        self.restored.append(code)

    def renew_user_with_invitation_code(self, code, username, user_id):
        self.renew_calls.append((code, username, user_id))
        if self.renew_error:
            raise self.renew_error
        return self.renew_result


class FakeLogger:
    def __init__(self):
        self.calls = []

    def error(self, message):
        self.calls.append(("error", message))


def _reset_code_command_state(monkeypatch):
    from app.domains.notifications import user_bot_service

    sent = []
    cleared = []
    invitation = FakeInvitationDao()
    logger = FakeLogger()

    monkeypatch.setattr(user_bot_service, "_user_state", {})
    monkeypatch.setattr(user_bot_service, "_clear_restriction_cache", lambda tg_user_id: cleared.append(tg_user_id))
    monkeypatch.setattr(user_bot_service, "_check_user_restrictions", lambda _tg_user_id: {"passed": True})
    monkeypatch.setattr(user_bot_service, "_format_restriction_message", lambda result: f"formatted:{result}")
    monkeypatch.setattr(user_bot_service, "_send", lambda chat_id, text, reply_markup=None: sent.append((chat_id, text, reply_markup)))
    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: None)
    monkeypatch.setattr(user_bot_service, "invitation_dao", invitation)
    monkeypatch.setattr(user_bot_service, "safe_error_message", lambda exc, fallback: f"safe:{fallback}")
    monkeypatch.setattr(user_bot_service, "logger", logger)
    return user_bot_service, sent, cleared, invitation, logger


def test_cmd_check_clears_cache_and_sends_passed_message(monkeypatch):
    user_bot_service, sent, cleared, _invitation, _logger = _reset_code_command_state(monkeypatch)

    user_bot_service.cmd_check(10, "tg1")

    assert cleared == ["tg1"]
    assert sent == [(10, "✅ <b>验证通过</b>\n\n你已经满足使用条件，可以正常使用机器人功能。", None)]


def test_cmd_check_formats_failed_restriction(monkeypatch):
    user_bot_service, sent, _cleared, _invitation, _logger = _reset_code_command_state(monkeypatch)
    monkeypatch.setattr(user_bot_service, "_check_user_restrictions", lambda _tg_user_id: {"passed": False, "missing": ["x"]})

    user_bot_service.cmd_check(10, "tg1")

    assert sent == [(10, "formatted:{'passed': False, 'missing': ['x']}", None)]


def test_cmd_code_sets_legacy_user_state_for_valid_registration_code(monkeypatch):
    user_bot_service, sent, _cleared, invitation, _logger = _reset_code_command_state(monkeypatch)
    invitation.registration_row = {
        "days": 30,
        "used_count": 1,
        "max_uses": 3,
        "template_user_id": "tpl1",
        "routes": "route-a",
        "route_mode": "allow",
    }

    user_bot_service.cmd_code(10, "tg1", " CODE1 ")

    assert user_bot_service._user_state == {
        "tg1": {
            "action": "code_input_name",
            "code": "CODE1",
            "days": 30,
            "tpl_id": "tpl1",
            "routes": "route-a",
            "route_mode": "allow",
        }
    }
    assert sent == [(
        10,
        "🎟️ <b>注册码验证成功！</b>\n\n请输入你想要的用户名（支持字母、数字、中文、下划线(_)、连字符(-)、@、.）：",
        {"inline_keyboard": [[{"text": "❌ 取消", "callback_data": "ub_cancel_state"}]]},
    )]


def test_cmd_code_preserves_guard_and_error_messages(monkeypatch):
    user_bot_service, sent, _cleared, invitation, logger = _reset_code_command_state(monkeypatch)

    user_bot_service.cmd_code(10, "tg1", "")
    assert sent[-1] == (10, "❌ 请输入注册码：/code 你的注册码", None)

    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: {"emby_username": "Alice"})
    user_bot_service.cmd_code(10, "tg1", "code")
    assert sent[-1] == (10, "❌ 你已经绑定了账号，如需续期请使用 /renew 续期码", None)

    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: None)
    invitation.registration_row = None
    user_bot_service.cmd_code(10, "tg1", "code")
    assert sent[-1] == (10, "❌ 注册码无效、已被使用或不是注册码", None)

    invitation.registration_row = {
        "days": 30,
        "used_count": 3,
        "max_uses": 3,
        "template_user_id": "",
        "routes": "",
        "route_mode": "",
    }
    user_bot_service.cmd_code(10, "tg1", "code")
    assert sent[-1] == (10, "❌ 该注册码已达使用上限", None)

    invitation.registration_error = RuntimeError("raw code error")
    user_bot_service.cmd_code(10, "tg1", "code")
    assert logger.calls == [("error", "[注册码] 验证失败: raw code error")]
    assert sent[-1] == (10, "❌ 注册码验证失败：safe:注册码验证异常，请稍后重试", None)


def test_restore_invitation_code_uses_legacy_invitation_dao_and_swallows_errors(monkeypatch):
    user_bot_service, _sent, _cleared, invitation, _logger = _reset_code_command_state(monkeypatch)

    user_bot_service._restore_invitation_code("ok")
    user_bot_service._restore_invitation_code("fail")

    assert invitation.restored == ["ok"]


def test_cmd_renew_preserves_success_and_permanent_display(monkeypatch):
    user_bot_service, sent, _cleared, invitation, _logger = _reset_code_command_state(monkeypatch)
    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: {"emby_username": "Alice", "emby_user_id": "u1"})
    invitation.renew_result = ({"days": 36500, "new_exp": "2099-01-01"}, None)

    user_bot_service.cmd_renew(10, "tg1", " RENEW ")

    assert invitation.renew_calls == [("RENEW", "Alice", "u1")]
    assert sent == [(10, "✅ <b>续期成功！</b>\n\n📅 新到期日：2099-01-01\n⏳ 延长了 永久", None)]


def test_cmd_renew_preserves_guards_errors_and_safe_error(monkeypatch):
    user_bot_service, sent, _cleared, invitation, logger = _reset_code_command_state(monkeypatch)

    user_bot_service.cmd_renew(10, "tg1", "")
    assert sent[-1] == (10, "❌ 请输入续期码：/renew 你的续期码", None)

    user_bot_service.cmd_renew(10, "tg1", "code")
    assert sent[-1] == (10, "❌ 请先绑定账号：/bind 用户名", None)

    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: {"emby_username": "Alice", "emby_user_id": "u1"})
    invitation.renew_result = (None, "invalid")
    user_bot_service.cmd_renew(10, "tg1", "code")
    assert sent[-1] == (10, "❌ 续期码无效、已被使用、不是续期码或已达使用上限", None)

    invitation.renew_result = (None, "permanent")
    user_bot_service.cmd_renew(10, "tg1", "code")
    assert sent[-1] == (10, "❌ 您的账号为永久有效，无需续费！", None)

    invitation.renew_error = RuntimeError("renew raw")
    user_bot_service.cmd_renew(10, "tg1", "code")
    assert logger.calls == [("error", "[续期] 执行失败: renew raw")]
    assert sent[-1] == (10, "❌ 续期失败：safe:续期操作异常，请联系管理员", None)
