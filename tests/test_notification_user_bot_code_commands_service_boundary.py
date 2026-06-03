import sys
import datetime as real_datetime
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
        self.claim_result = True
        self.claim_calls = []
        self.finished = []

    def get_available_registration_invitation(self, code):
        if self.registration_error:
            raise self.registration_error
        return self.registration_row

    def restore_invitation_code_usage(self, code):
        if code == "fail":
            raise RuntimeError("restore failed")
        self.restored.append(code)

    def claim_invitation_usage(self, code, safe_name):
        self.claim_calls.append((code, safe_name))
        return self.claim_result

    def save_code_registration_meta_and_finish_invitation(self, code, uid, expire, allow_routes, block_routes):
        self.finished.append((code, uid, expire, allow_routes, block_routes))

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


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self.payload = payload or {}
        self.status_code = status_code

    def json(self):
        return self.payload


class FakeMediaApi:
    def __init__(self):
        self.users = []
        self.template = {"Policy": {"IsAdministrator": True, "IsDisabled": True, "Other": "keep"}}
        self.create_status = 201
        self.calls = []

    def get(self, path, timeout=None):
        self.calls.append(("get", path, timeout))
        if path == "/Users":
            return FakeResponse(self.users)
        if path.startswith("/Users/"):
            return FakeResponse(self.template)
        return FakeResponse({})

    def post(self, path, json=None, timeout=None):
        self.calls.append(("post", path, json, timeout))
        if path == "/Users/New":
            return FakeResponse({"Id": "u-new"}, self.create_status)
        return FakeResponse({"ok": True}, 200)


class FakeSecrets:
    def __init__(self):
        self.calls = []

    def token_urlsafe(self, length):
        self.calls.append(length)
        return "pw-token"


class FakeDateTime:
    timedelta = real_datetime.timedelta

    class date:
        @classmethod
        def today(cls):
            return real_datetime.date(2026, 6, 3)


class FakeLock:
    def __init__(self, key, events):
        self.key = key
        self.events = events

    def __enter__(self):
        self.events.append(("lock_enter", self.key))
        return self

    def __exit__(self, exc_type, exc, tb):
        self.events.append(("lock_exit", self.key))
        return False


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


def _reset_code_registration_state(monkeypatch):
    user_bot_service, sent, _cleared, invitation, logger = _reset_code_command_state(monkeypatch)

    queue = {"enter": True, "events": []}
    media_api = FakeMediaApi()
    secrets = FakeSecrets()
    locks = []
    bound = []
    invalidated = []
    notifications = []
    restored = []

    monkeypatch.setattr(user_bot_service, "_enter_reg_queue", lambda chat_id: queue["events"].append(("enter", chat_id)) or queue["enter"])
    monkeypatch.setattr(user_bot_service, "_leave_reg_queue", lambda: queue["events"].append(("leave",)))
    monkeypatch.setattr(user_bot_service, "_get_username_lock", lambda key: locks.append(key) or FakeLock(key, queue["events"]))
    monkeypatch.setattr(user_bot_service, "media_api", media_api)
    monkeypatch.setattr(user_bot_service, "_restore_invitation_code", lambda code: restored.append(code))
    monkeypatch.setattr(
        user_bot_service,
        "_bind_user",
        lambda tg_user_id, uid, name, init_password="", tg_username="", tg_display_name="": bound.append(
            (tg_user_id, uid, name, init_password, tg_username, tg_display_name)
        ),
    )
    monkeypatch.setattr(user_bot_service, "secrets", secrets)
    monkeypatch.setattr(user_bot_service, "datetime", FakeDateTime)
    monkeypatch.setattr(user_bot_service, "_invalidate_users_cache_after_code_registration", lambda: invalidated.append(True))
    monkeypatch.setattr(
        user_bot_service,
        "_send_code_registration_notifications",
        lambda safe_name, days, code, tg_user_id: notifications.append((safe_name, days, code, tg_user_id)),
    )

    return user_bot_service, sent, invitation, logger, queue, media_api, secrets, locks, bound, invalidated, notifications, restored


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


def test_do_code_register_preserves_queue_rejection(monkeypatch):
    user_bot_service, sent, invitation, _logger, queue, media_api, _secrets, _locks, _bound, _invalidated, _notifications, _restored = (
        _reset_code_registration_state(monkeypatch)
    )
    queue["enter"] = False

    user_bot_service._do_code_register(10, "tg1", "Alice", "CODE1", 30, "tpl1")

    assert queue["events"] == [("enter", 10)]
    assert sent == []
    assert invitation.claim_calls == []
    assert media_api.calls == []


def test_do_code_register_preserves_validation_and_state_restore(monkeypatch):
    user_bot_service, sent, _invitation, _logger, queue, _media_api, _secrets, _locks, _bound, _invalidated, _notifications, _restored = (
        _reset_code_registration_state(monkeypatch)
    )

    user_bot_service._do_code_register(10, "tg1", "abcdefghijklmnopq", "CODE1", 30, "tpl1", routes="r1", route_mode="allow")

    assert sent[-1] == (10, "❌ 用户名最多 16 个字符，当前 17 个字符", None)
    assert user_bot_service._user_state == {
        "tg1": {
            "action": "code_input_name",
            "code": "CODE1",
            "days": 30,
            "tpl_id": "tpl1",
            "routes": "r1",
            "route_mode": "allow",
        }
    }
    assert queue["events"] == [("enter", 10), ("leave",)]

    sent.clear()
    user_bot_service._user_state.clear()
    queue["events"].clear()

    user_bot_service._do_code_register(10, "tg1", "Bad Name!", "CODE1", 30, "tpl1")

    assert sent[-1][0] == 10
    assert sent[-1][1].startswith("❌ 用户名包含不支持的字符:")
    assert "只允许字母、数字、中文、下划线(_)、连字符(-)、@ 和 ." in sent[-1][1]
    assert user_bot_service._user_state["tg1"]["action"] == "code_input_name"
    assert queue["events"] == [("enter", 10), ("leave",)]


def test_do_code_register_preserves_duplicate_and_claim_failure(monkeypatch):
    user_bot_service, sent, invitation, _logger, queue, media_api, _secrets, locks, _bound, _invalidated, _notifications, _restored = (
        _reset_code_registration_state(monkeypatch)
    )
    media_api.users = [{"Name": "Alice"}]

    user_bot_service._do_code_register(10, "tg1", "Alice", "CODE1", 30, "tpl1")

    assert sent[-1] == (10, "❌ 用户名 <b>Alice</b> 已被占用，请换一个", None)
    assert user_bot_service._user_state["tg1"]["action"] == "code_input_name"
    assert locks == ["alice"]
    assert invitation.claim_calls == []
    assert queue["events"] == [("enter", 10), ("lock_enter", "alice"), ("lock_exit", "alice"), ("leave",)]

    sent.clear()
    queue["events"].clear()
    media_api.users = []
    invitation.claim_result = False

    user_bot_service._do_code_register(10, "tg1", "Bob", "CODE1", 30, "tpl1")

    assert invitation.claim_calls == [("CODE1", "Bob")]
    assert sent[-1] == (10, "❌ 注册码已失效或已达到使用上限", None)
    assert queue["events"] == [("enter", 10), ("lock_enter", "bob"), ("lock_exit", "bob"), ("leave",)]


def test_do_code_register_preserves_emby_create_failure_rollback(monkeypatch):
    user_bot_service, sent, invitation, _logger, queue, media_api, _secrets, _locks, _bound, _invalidated, _notifications, restored = (
        _reset_code_registration_state(monkeypatch)
    )
    media_api.create_status = 500

    user_bot_service._do_code_register(10, "tg1", "Alice", "CODE1", 30, "")

    assert invitation.claim_calls == [("CODE1", "Alice")]
    assert restored == ["CODE1"]
    assert sent[-1] == (10, "❌ 创建账号失败", None)
    assert ("post", "/Users/New", {"Name": "Alice"}, 10) in media_api.calls
    assert queue["events"][-1] == ("leave",)


def test_do_code_register_preserves_success_meta_binding_and_notifications(monkeypatch):
    user_bot_service, sent, invitation, _logger, queue, media_api, secrets, locks, bound, invalidated, notifications, restored = (
        _reset_code_registration_state(monkeypatch)
    )

    user_bot_service._do_code_register(
        10,
        "tg1",
        "Alice",
        "CODE1",
        30,
        "tpl1",
        routes="route-a",
        route_mode="allow",
        tg_username="alice_tg",
        tg_display_name="Alice TG",
    )

    assert secrets.calls == [8]
    assert locks == ["alice"]
    assert invitation.claim_calls == [("CODE1", "Alice")]
    assert invitation.finished == [("CODE1", "u-new", "2026-07-03", "route-a", "")]
    assert bound == [("tg1", "u-new", "Alice", "pw-token", "alice_tg", "Alice TG")]
    assert invalidated == [True]
    assert notifications == [("Alice", 30, "CODE1", "tg1")]
    assert restored == []
    assert sent[-1] == (
        10,
        "🎉 <b>注册码激活成功！</b>\n\n👤 用户名：<code>Alice</code>\n🔑 密码：<code>pw-token</code>\n📅 有效期：30 天（至 2026-07-03）\n\n💡 密码可在「个人中心」随时查看",
        None,
    )
    assert ("post", "/Users/u-new/Password", {"NewPw": "pw-token"}, 5) in media_api.calls
    assert ("post", "/Users/u-new/Policy", {"IsAdministrator": False, "IsDisabled": False, "Other": "keep"}, 5) in media_api.calls
    assert queue["events"][-1] == ("leave",)


def test_do_code_register_preserves_exception_safe_error(monkeypatch):
    user_bot_service, sent, _invitation, logger, queue, media_api, _secrets, _locks, _bound, _invalidated, _notifications, _restored = (
        _reset_code_registration_state(monkeypatch)
    )

    def raise_users(path, timeout=None):
        raise RuntimeError("raw register")

    media_api.get = raise_users

    user_bot_service._do_code_register(10, "tg1", "Alice", "CODE1", 30, "tpl1")

    assert logger.calls == [("error", "[注册码] 使用失败: raw register")]
    assert sent[-1] == (10, "❌ 注册码使用失败：safe:注册操作异常，请稍后重试", None)
    assert queue["events"] == [("enter", 10), ("lock_enter", "alice"), ("lock_exit", "alice"), ("leave",)]
