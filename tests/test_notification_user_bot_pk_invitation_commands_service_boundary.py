import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class FakeMediaApi:
    def __init__(self):
        self.users = [{"Id": "u2", "Name": "Bob"}]
        self.calls = []

    def get(self, path, timeout=None):
        self.calls.append((path, timeout))
        return FakeResponse(self.users)


class FakeUserBotDao:
    def __init__(self):
        self.username_map = {"bob": "tg2"}
        self.bindings = {
            "tg2": {"emby_user_id": "u2", "emby_username": "Bob"},
            "Bob": {"emby_user_id": "u2", "emby_username": "Bob"},
        }
        self.username_calls = []
        self.binding_calls = []

    def get_tg_user_id_by_username(self, username):
        self.username_calls.append(username)
        return self.username_map.get(username)

    def get_binding_by_tg_user_or_username(self, identifier):
        self.binding_calls.append(identifier)
        return self.bindings.get(identifier)


class FakePointDao:
    def __init__(self):
        self.invite_result = {"status": "success", "invite_id": 42, "timeout_minutes": 5}
        self.created_invitations = []
        self.saved_messages = []
        self.latest_invite = {"id": 42, "challenger_name": "Alice", "chat_id": 20}
        self.accept_result = {
            "status": "success",
            "challenger_name": "Alice",
            "target_name": "Bob",
            "challenger_roll": 5,
            "target_roll": 3,
            "chat_id": 20,
            "winner_name": "Alice",
            "win_amount": 90,
            "tax_rate": 10,
        }
        self.accept_calls = []
        self.status_updates = []
        self.raise_on_create = None

    def create_pk_invitation(
        self,
        challenger_id,
        challenger_name,
        challenger_tg_name,
        target_id,
        target_name,
        target_tg_name,
        points,
        chat_id,
        command_message_id=None,
    ):
        self.created_invitations.append(
            (
                challenger_id,
                challenger_name,
                challenger_tg_name,
                target_id,
                target_name,
                target_tg_name,
                points,
                chat_id,
                command_message_id,
            )
        )
        if self.raise_on_create:
            raise self.raise_on_create
        return self.invite_result

    def save_pk_invitation_message_id(self, invite_id, message_id):
        self.saved_messages.append((invite_id, message_id))

    def get_latest_pending_pk_invitation_for_target(self, user_id):
        return self.latest_invite

    def accept_pk_invitation(self, invite_id, user_id):
        self.accept_calls.append((invite_id, user_id))
        return self.accept_result

    def set_pk_invitation_status(self, invite_id, status):
        self.status_updates.append((invite_id, status))


class FakeLogger:
    def __init__(self):
        self.errors = []

    def error(self, message):
        self.errors.append(message)


def _reset_pk_invitation_state(monkeypatch):
    from app.domains.notifications import user_bot_service

    sent = []
    point_dao = FakePointDao()
    user_bot_dao = FakeUserBotDao()
    media_api = FakeMediaApi()
    logger = FakeLogger()
    binding = {"emby_user_id": "u1", "emby_username": "Alice", "tg_name": "AliceTG"}
    emby_bindings = {
        "u2": {"tg_name": "BobTG", "tg_username": "bob_tg"},
    }

    def fake_send(chat_id, text, reply_markup=None):
        sent.append((chat_id, text, reply_markup))
        return {"ok": True, "result": {"message_id": 900 + len(sent)}}

    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: binding)
    monkeypatch.setattr(user_bot_service, "_get_binding_by_emby_id", lambda emby_user_id: emby_bindings.get(emby_user_id))
    monkeypatch.setattr(user_bot_service, "_send", fake_send)
    monkeypatch.setattr(user_bot_service, "point_dao", point_dao)
    monkeypatch.setattr(user_bot_service, "user_bot_dao", user_bot_dao)
    monkeypatch.setattr(user_bot_service, "media_api", media_api)
    monkeypatch.setattr(user_bot_service, "safe_error_message", lambda _err, fallback: f"masked:{fallback}")
    monkeypatch.setattr(user_bot_service, "logger", logger)

    return user_bot_service, sent, point_dao, user_bot_dao, media_api, logger


def test_cmd_pk_invite_uses_mention_target_and_preserves_invite_message(monkeypatch):
    user_bot_service, sent, point_dao, user_bot_dao, _media_api, _logger = _reset_pk_invitation_state(monkeypatch)

    result = user_bot_service.cmd_pk_invite(
        10,
        "tg1",
        "/upk @bob 100",
        is_group=True,
        entities=[{"type": "mention", "offset": 5, "length": 4}],
        user_msg_id=77,
    )

    assert result is None
    assert user_bot_dao.username_calls == ["bob"]
    assert user_bot_dao.binding_calls == ["tg2"]
    assert point_dao.created_invitations == [("u1", "Alice", "AliceTG", "u2", "Bob", "BobTG", 100, 10, 77)]
    assert point_dao.saved_messages == [(42, 901)]
    assert sent == [(
        10,
        "🎯 <b>AliceTG</b> 向 @bob_tg 发起PK挑战！\n\n💰 下注：<b>100</b> 积分\n⏰ 请在 <b>5</b> 分钟内回应\n\n💡 点击下方按钮选择接受或拒绝",
        {"inline_keyboard": [[
            {"text": "✅ 接受PK", "callback_data": "pk_accept:42"},
            {"text": "❌ 拒绝PK", "callback_data": "pk_reject:42"},
        ]]},
    )]


def test_cmd_pk_invite_falls_back_to_emby_user_and_preserves_validation(monkeypatch):
    user_bot_service, sent, point_dao, user_bot_dao, media_api, _logger = _reset_pk_invitation_state(monkeypatch)
    user_bot_dao.bindings = {}

    user_bot_service.cmd_pk_invite(10, "tg1", "/upk Bob 50")

    assert media_api.calls == [("/Users", 5)]
    assert point_dao.created_invitations == [("u1", "Alice", "AliceTG", "u2", "Bob", "BobTG", 50, 10, None)]

    sent.clear()
    user_bot_service.cmd_pk_invite(10, "tg1", "/upk Bob nope")
    assert sent == [(10, "❌ 下注积分必须是数字", None)]

    sent.clear()
    user_bot_dao.bindings = {"Alice": {"emby_user_id": "u1", "emby_username": "Alice"}}
    user_bot_service.cmd_pk_invite(10, "tg1", "/upk Alice 10")
    assert sent == [(10, "❌ 不能PK自己", None)]


def test_cmd_pk_invite_uses_safe_error_message_on_exception(monkeypatch):
    user_bot_service, sent, point_dao, _user_bot_dao, _media_api, logger = _reset_pk_invitation_state(monkeypatch)
    point_dao.raise_on_create = RuntimeError("raw pk")

    user_bot_service.cmd_pk_invite(10, "tg1", "/upk Bob 100")

    assert logger.errors == ["[UserBot] PK邀请失败: raw pk"]
    assert sent[-1] == (10, "❌ PK邀请失败：masked:PK邀请异常，请稍后重试", None)


def test_cmd_pk_accept_preserves_result_notifications(monkeypatch):
    user_bot_service, sent, point_dao, _user_bot_dao, _media_api, _logger = _reset_pk_invitation_state(monkeypatch)

    result = user_bot_service.cmd_pk_accept(10, "tg1", "/accept")

    result_msg = "🎲 <b>PK结果</b>\n\nAlice(5点) vs Bob(3点)\n\n🎉 <b>Alice</b> 获胜！\n💰 获得 <b>90</b> 积分（扣10%手续费）"
    assert point_dao.accept_calls == [(42, "u1")]
    assert sent == [(20, result_msg, None), (10, result_msg, None)]
    assert result == {"ok": True, "result": {"message_id": 902}}


def test_cmd_pk_reject_preserves_status_update_and_notifications(monkeypatch):
    user_bot_service, sent, point_dao, _user_bot_dao, _media_api, _logger = _reset_pk_invitation_state(monkeypatch)

    result = user_bot_service.cmd_pk_reject(10, "tg1", "/reject")

    assert point_dao.status_updates == [(42, "rejected")]
    assert sent == [
        (20, "❌ <b>Alice</b> 拒绝了你的PK邀请", None),
        (10, "✅ 已拒绝 <b>Alice</b> 的PK邀请", None),
    ]
    assert result == {"ok": True, "result": {"message_id": 902}}
