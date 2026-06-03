import datetime as real_datetime
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeDateTime:
    class datetime:
        @classmethod
        def now(cls):
            return real_datetime.datetime(2026, 6, 3, 12, 0, 0)

        @classmethod
        def fromisoformat(cls, value):
            return real_datetime.datetime.fromisoformat(value)


class FakePointDao:
    def __init__(self):
        self.invite = {
            "target_id": "u2",
            "challenger_name": "Alice",
            "challenger_tg_name": "AliceTG",
            "target_name": "Bob",
            "target_tg_name": "BobTG",
            "points": 100,
            "message_id": 222,
            "command_message_id": 111,
            "expires_at": "2026-06-03T13:00:00",
            "chat_id": 20,
        }
        self.accept_result = {
            "status": "success",
            "winner_name": "Alice",
            "win_amount": 180,
            "tax_rate": 10,
        }
        self.accept_calls = []
        self.expired = []
        self.status_updates = []

    def get_pending_pk_invitation(self, invite_id):
        return self.invite

    def mark_pk_invitation_expired(self, invite_id):
        self.expired.append(invite_id)

    def accept_pk_invitation(self, invite_id, user_id, **kwargs):
        self.accept_calls.append((invite_id, user_id, kwargs))
        return self.accept_result

    def set_pk_invitation_status(self, invite_id, status):
        self.status_updates.append((invite_id, status))


class FakeLogger:
    def __init__(self):
        self.errors = []

    def error(self, message):
        self.errors.append(message)


def _reset_callback_state(monkeypatch):
    from tests.user_bot_worker_boundary import user_bot_worker_boundary as user_bot_service

    calls = []
    edits = []
    sent = []
    sleeps = []
    point_dao = FakePointDao()
    logger = FakeLogger()
    binding = {"emby_user_id": "u2", "emby_username": "Bob", "tg_name": "BobTG"}
    dice_responses = [
        {"ok": True, "result": {"message_id": 501, "dice": {"value": 5}}},
        {"ok": True, "result": {"message_id": 502, "dice": {"value": 3}}},
    ]

    def fake_tg_api(method, data):
        calls.append((method, data))
        if method == "sendDice":
            return dice_responses.pop(0)
        return {"ok": True}

    def fake_edit(chat_id, msg_id, text, reply_markup=None):
        edits.append((chat_id, msg_id, text, reply_markup))
        return {"ok": True}

    def fake_send(chat_id, text, reply_markup=None):
        sent.append((chat_id, text, reply_markup))
        return {"ok": True, "result": {"message_id": 900 + len(sent)}}

    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: binding)
    monkeypatch.setattr(user_bot_service, "_tg_api", fake_tg_api)
    monkeypatch.setattr(user_bot_service, "_edit", fake_edit)
    monkeypatch.setattr(user_bot_service, "_send", fake_send)
    monkeypatch.setattr(user_bot_service, "point_dao", point_dao)
    monkeypatch.setattr(user_bot_service, "datetime", FakeDateTime)
    monkeypatch.setattr(user_bot_service.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(user_bot_service, "logger", logger)

    return user_bot_service, calls, edits, sent, sleeps, point_dao, logger


def test_pk_accept_callback_preserves_success_dice_and_cleanup(monkeypatch):
    user_bot_service, calls, edits, sent, sleeps, point_dao, _logger = _reset_callback_state(monkeypatch)

    user_bot_service._handle_pk_accept_callback(10, "tg2", "inv-1", "cq-1", 333)

    assert point_dao.accept_calls == [(
        "inv-1",
        "u2",
        {"challenger_roll": 5, "target_roll": 3, "cancel_on_insufficient": True},
    )]
    assert sleeps == [2, 2, 5]
    assert edits == [(
        10,
        333,
        "🎲 <b>PK开始！</b>\n\nAliceTG vs BobTG\n💰 下注：100 积分\n\n🎲 正在掷骰子...",
        None,
    )]
    assert sent == [(
        10,
        "🎲 <b>PK结果</b>\n\nAliceTG(5点) vs BobTG(3点)\n\n"
        "🎉 <b>Alice</b> 获胜！\n💰 获得 <b>180</b> 积分（扣10%手续费）",
        None,
    )]
    assert calls[:4] == [
        ("answerCallbackQuery", {"callback_query_id": "cq-1", "text": "🎲 掷骰子中..."}),
        ("sendDice", {"chat_id": 10}),
        ("sendDice", {"chat_id": 10}),
        ("answerCallbackQuery", {"callback_query_id": "cq-1", "text": "Alice获胜！"}),
    ]
    assert calls[4:] == [
        ("deleteMessage", {"chat_id": 10, "message_id": 111}),
        ("deleteMessage", {"chat_id": 10, "message_id": 222}),
        ("deleteMessage", {"chat_id": 10, "message_id": 501}),
        ("deleteMessage", {"chat_id": 10, "message_id": 502}),
        ("deleteMessage", {"chat_id": 10, "message_id": 901}),
    ]


def test_pk_accept_callback_preserves_expired_invite_handling(monkeypatch):
    user_bot_service, calls, edits, sent, sleeps, point_dao, _logger = _reset_callback_state(monkeypatch)
    point_dao.invite["expires_at"] = "2026-06-03T11:00:00"

    user_bot_service._handle_pk_accept_callback(10, "tg2", "inv-1", "cq-1", 333)

    assert point_dao.expired == ["inv-1"]
    assert point_dao.accept_calls == []
    assert sent == []
    assert sleeps == []
    assert calls == [("answerCallbackQuery", {"callback_query_id": "cq-1", "text": "PK邀请已过期", "show_alert": True})]
    assert edits == [(10, 333, "❌ PK邀请已过期", None)]


def test_pk_accept_callback_preserves_wrong_target_validation(monkeypatch):
    user_bot_service, calls, edits, sent, sleeps, point_dao, _logger = _reset_callback_state(monkeypatch)
    point_dao.invite["target_id"] = "other-user"

    user_bot_service._handle_pk_accept_callback(10, "tg2", "inv-1", "cq-1", 333)

    assert point_dao.accept_calls == []
    assert edits == []
    assert sent == []
    assert sleeps == []
    assert calls == [("answerCallbackQuery", {"callback_query_id": "cq-1", "text": "这不是发给你的PK邀请", "show_alert": True})]


def test_pk_reject_callback_preserves_status_notification_and_cleanup(monkeypatch):
    user_bot_service, calls, edits, sent, sleeps, point_dao, _logger = _reset_callback_state(monkeypatch)

    user_bot_service._handle_pk_reject_callback(10, "tg2", "inv-1", "cq-1", 333)

    assert point_dao.status_updates == [("inv-1", "rejected")]
    assert calls == [
        ("answerCallbackQuery", {"callback_query_id": "cq-1", "text": "已拒绝PK邀请"}),
        ("deleteMessage", {"chat_id": 10, "message_id": 111}),
        ("deleteMessage", {"chat_id": 10, "message_id": 222}),
        ("deleteMessage", {"chat_id": 10, "message_id": 333}),
    ]
    assert edits == [(10, 333, "❌ <b>BobTG</b> 已拒绝 <b>AliceTG</b> 的PK邀请", None)]
    assert sent == [(20, "❌ <b>BobTG</b> 拒绝了你的PK邀请", None)]
    assert sleeps == [5]
