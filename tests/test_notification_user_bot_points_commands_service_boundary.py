import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakePointDao:
    def __init__(self):
        self.checkin_result = {
            "reward": 10,
            "streak_bonus": 3,
            "streak_count": 2,
            "balance": 88,
        }
        self.checkin_error = None
        self.points_balance = 42
        self.points_error = None
        self.checkin_calls = []
        self.balance_calls = []

    def perform_user_checkin(self, user_id, username):
        self.checkin_calls.append((user_id, username))
        if self.checkin_error:
            raise self.checkin_error
        return self.checkin_result

    def get_user_points_balance(self, user_id):
        self.balance_calls.append(user_id)
        if self.points_error:
            raise self.points_error
        return self.points_balance


class FakeLogger:
    def __init__(self):
        self.calls = []

    def error(self, message):
        self.calls.append(("error", message))


def _reset_points_command_state(monkeypatch):
    from tests.user_bot_worker_boundary import user_bot_worker_boundary as user_bot_service

    replies = []
    sent = []
    deleted = []
    unbound = []
    point_dao = FakePointDao()
    logger = FakeLogger()
    binding = {"emby_user_id": "u1", "emby_username": "Alice"}

    def fake_reply(chat_id, text, reply_markup=None, msg_id=None):
        replies.append((chat_id, text, reply_markup, msg_id))
        return {"result": {"message_id": 900 + len(replies)}}

    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: binding)
    monkeypatch.setattr(user_bot_service, "_check_emby_account", lambda _binding: True)
    monkeypatch.setattr(user_bot_service, "_unbind_user", lambda tg_user_id: unbound.append(tg_user_id))
    monkeypatch.setattr(user_bot_service, "_reply", fake_reply)
    monkeypatch.setattr(user_bot_service, "_send", lambda chat_id, text, reply_markup=None: sent.append((chat_id, text, reply_markup)))
    monkeypatch.setattr(user_bot_service, "_main_menu_keyboard", lambda binding_arg=None: {"menu": binding_arg})
    monkeypatch.setattr(
        user_bot_service,
        "_delete_messages_later",
        lambda chat_id, message_ids, delay_seconds=30: deleted.append((chat_id, message_ids, delay_seconds)),
    )
    monkeypatch.setattr(user_bot_service, "point_dao", point_dao)
    monkeypatch.setattr(user_bot_service, "safe_error_message", lambda exc, fallback: f"safe:{fallback}")
    monkeypatch.setattr(user_bot_service, "logger", logger)

    return user_bot_service, replies, sent, deleted, unbound, point_dao, logger


def test_cmd_checkin_private_unbound_uses_legacy_reply(monkeypatch):
    user_bot_service, replies, _sent, deleted, _unbound, point_dao, _logger = _reset_points_command_state(monkeypatch)
    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: None)

    user_bot_service.cmd_checkin(10, "tg1", msg_id=5)

    assert replies == [(10, "❌ 请先绑定账号", None, 5)]
    assert deleted == []
    assert point_dao.checkin_calls == []


def test_cmd_checkin_group_unbound_schedules_command_cleanup(monkeypatch):
    user_bot_service, replies, _sent, deleted, _unbound, _point_dao, _logger = _reset_points_command_state(monkeypatch)
    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: None)

    user_bot_service.cmd_checkin("group-1", "tg1", msg_id=5, is_group=True, user_msg_id=77)

    assert replies == [("group-1", "❌ 请先私聊机器人绑定账号后再签到", None, 5)]
    assert deleted == [("group-1", [901, 77], 30)]


def test_cmd_checkin_deleted_emby_account_unbinds_and_uses_private_menu(monkeypatch):
    user_bot_service, replies, _sent, deleted, unbound, _point_dao, _logger = _reset_points_command_state(monkeypatch)
    monkeypatch.setattr(user_bot_service, "_check_emby_account", lambda _binding: False)

    user_bot_service.cmd_checkin(10, "tg1", msg_id=5)

    assert unbound == ["tg1"]
    assert replies == [(10, "⚠️ 你的 Emby 账号已被删除，绑定已自动解除。请联系管理员。", {"menu": None}, 5)]
    assert deleted == []


def test_cmd_checkin_success_preserves_message_buttons_and_group_cleanup(monkeypatch):
    user_bot_service, replies, _sent, deleted, _unbound, point_dao, _logger = _reset_points_command_state(monkeypatch)

    user_bot_service.cmd_checkin(10, "tg1", msg_id=5)

    assert point_dao.checkin_calls == [("u1", "Alice")]
    assert replies == [(
        10,
        "🎉 签到成功！\n\n🎲 获得 <b>10</b> 积分\n🔥 连续签到 <b>2</b> 天，额外奖励 <b>3</b> 积分\n💰 当前余额：<b>88</b> 积分",
        {"inline_keyboard": [[
            {"text": "🏪 去商城逛逛", "callback_data": "ub_menu_shop"},
            {"text": "🔙 主菜单", "callback_data": "ub_back_menu"},
        ]]},
        5,
    )]

    replies.clear()
    user_bot_service.cmd_checkin("group-1", "tg1", msg_id=6, is_group=True, group_name="影院群", user_msg_id=77)

    assert replies == [(
        "group-1",
        "🎉 <b>Alice</b> 在 <b>影院群</b> 签到成功！\n\n\n🎲 获得 <b>10</b> 积分\n🔥 连续签到 <b>2</b> 天，额外奖励 <b>3</b> 积分\n💰 当前余额：<b>88</b> 积分",
        None,
        6,
    )]
    assert deleted == [("group-1", [901, 77], 30)]


def test_cmd_checkin_already_checked_in_branch_and_failure_send(monkeypatch):
    user_bot_service, replies, sent, deleted, _unbound, point_dao, logger = _reset_points_command_state(monkeypatch)
    point_dao.checkin_result = {"status": "error"}

    user_bot_service.cmd_checkin("group-1", "tg1", msg_id=5, is_group=True, user_msg_id=77)

    assert replies == [("group-1", "😊 今天已经签到过了，明天再来吧！", None, 5)]
    assert deleted == [("group-1", [901, 77], 30)]

    point_dao.checkin_error = RuntimeError("raw checkin failure")
    user_bot_service.cmd_checkin(10, "tg1", msg_id=6)

    assert logger.calls == [("error", "[签到] 执行失败: raw checkin failure")]
    assert sent == [(10, "❌ 签到失败：safe:签到操作异常，请稍后重试", None)]


def test_cmd_points_private_group_deleted_and_failure_branches(monkeypatch):
    user_bot_service, replies, _sent, _deleted, unbound, point_dao, _logger = _reset_points_command_state(monkeypatch)

    result = user_bot_service.cmd_points(10, "tg1", msg_id=5)

    assert result == {"result": {"message_id": 901}}
    assert point_dao.balance_calls == ["u1"]
    assert replies[-1] == (
        10,
        "💰 <b>Alice</b> 的积分余额\n\n🪙 当前积分：<b>42</b>",
        {"inline_keyboard": [[
            {"text": "✅ 签到", "callback_data": "ub_menu_checkin"},
            {"text": "🏪 商城", "callback_data": "ub_menu_shop"},
            {"text": "🔙 主菜单", "callback_data": "ub_back_menu"},
        ]]},
        5,
    )

    user_bot_service.cmd_points("group-1", "tg1", msg_id=6, is_group=True)
    assert replies[-1] == ("group-1", "💰 <b>Alice</b> 的积分余额：<b>42</b>", None, 6)

    monkeypatch.setattr(user_bot_service, "_check_emby_account", lambda _binding: False)
    user_bot_service.cmd_points(10, "tg1", msg_id=7)
    assert unbound == ["tg1"]
    assert replies[-1] == (10, "⚠️ 你的 Emby 账号已被删除，绑定已自动解除。请联系管理员。", {"menu": None}, 7)

    monkeypatch.setattr(user_bot_service, "_check_emby_account", lambda _binding: True)
    point_dao.points_error = RuntimeError("points failure")
    user_bot_service.cmd_points(10, "tg1", msg_id=8)
    assert replies[-1] == (10, "❌ 查询失败", None, 8)
