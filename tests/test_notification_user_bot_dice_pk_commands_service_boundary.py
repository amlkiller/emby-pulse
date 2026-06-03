import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeRandom:
    def __init__(self, values=None):
        self.values = list(values or [4, 4, 4, 4])
        self.calls = []

    def randint(self, start, end):
        self.calls.append((start, end))
        return self.values.pop(0) if self.values else start


class FakePointDao:
    def __init__(self):
        self.config = {
            "enable_pk": 1,
            "pk_min": 10,
            "pk_max": 500,
            "pk_max_per_day": 10,
        }
        self.today_count = 0
        self.balance = 1000
        self.point_result = {"status": "success", "points": 1100}
        self.count_calls = []
        self.balance_calls = []
        self.change_calls = []

    def get_point_config(self):
        return self.config

    def count_today_point_logs(self, user_id, action_like=None):
        self.count_calls.append((user_id, action_like))
        return self.today_count

    def get_user_points_balance(self, user_id):
        self.balance_calls.append(user_id)
        return self.balance

    def apply_game_point_change(self, user_id, username, action, amount, require_min_points=None):
        self.change_calls.append((user_id, username, action, amount, require_min_points))
        return self.point_result


class FakeLogger:
    def __init__(self):
        self.errors = []

    def error(self, message):
        self.errors.append(message)


def _reset_dice_pk_state(monkeypatch, dice_values=None):
    from app.domains.notifications import user_bot_service

    sent = []
    deleted = []
    tg_calls = []
    sleeps = []
    point_dao = FakePointDao()
    random = FakeRandom()
    logger = FakeLogger()
    binding = {"emby_user_id": "u1", "emby_username": "Alice"}
    dice_values = [5, 3] if dice_values is None else list(dice_values)

    def fake_send(chat_id, text, reply_markup=None):
        sent.append((chat_id, text, reply_markup))
        return {"ok": True, "result": {"message_id": 900 + len(sent)}}

    def fake_tg_api(method, data):
        tg_calls.append((method, data))
        if method == "sendDice":
            if not dice_values:
                return None
            value = dice_values.pop(0)
            if value is None:
                return {"ok": True, "result": {"message_id": 500 + len(tg_calls)}}
            return {"ok": True, "result": {"message_id": 500 + len(tg_calls), "dice": {"value": value}}}
        return {"ok": True}

    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: binding)
    monkeypatch.setattr(user_bot_service, "_send", fake_send)
    monkeypatch.setattr(user_bot_service, "_tg_api", fake_tg_api)
    monkeypatch.setattr(
        user_bot_service,
        "_delete_messages_later",
        lambda chat_id, ids, delay_seconds=30: deleted.append((chat_id, ids, delay_seconds)),
    )
    monkeypatch.setattr(user_bot_service, "point_dao", point_dao)
    monkeypatch.setattr(user_bot_service, "random", random)
    monkeypatch.setattr(user_bot_service.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(user_bot_service, "logger", logger)

    return user_bot_service, sent, deleted, tg_calls, sleeps, point_dao, random, logger


def test_cmd_pk_preserves_unbound_usage_and_validation_messages(monkeypatch):
    user_bot_service, sent, _deleted, _tg_calls, _sleeps, point_dao, _random, _logger = _reset_dice_pk_state(monkeypatch)

    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: None)
    user_bot_service.cmd_pk(10, "tg1", "/pk 100")
    assert sent == [(10, "❌ 请先私聊机器人绑定账号", None)]

    sent.clear()
    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: {"emby_user_id": "u1", "emby_username": "Alice"})
    user_bot_service.cmd_pk(10, "tg1", "/pk")
    assert sent == [(10, "💡 使用方法：/pk 积分\n示例：/pk 100\n\n🎲 和机器人掷骰子比大小，赢了翻倍，输了扣分", None)]

    sent.clear()
    user_bot_service.cmd_pk(10, "tg1", "/pk nope")
    assert sent == [(10, "❌ 积分必须是数字", None)]

    sent.clear()
    user_bot_service.cmd_pk(10, "tg1", "/pk 0")
    assert sent == [(10, "❌ 积分必须大于0", None)]

    sent.clear()
    point_dao.config["enable_pk"] = 0
    user_bot_service.cmd_pk(10, "tg1", "/pk 100")
    assert sent == [(10, "❌ PK功能未开启", None)]

    sent.clear()
    point_dao.config["enable_pk"] = 1
    user_bot_service.cmd_pk(10, "tg1", "/pk 5")
    assert sent == [(10, "❌ PK积分需在 10-500 之间", None)]

    sent.clear()
    point_dao.today_count = 10
    user_bot_service.cmd_pk(10, "tg1", "/pk 100")
    assert sent == [(10, "❌ 今天PK次数已达上限 (10次)\n\n💡 明天再来吧！", None)]

    sent.clear()
    point_dao.today_count = 0
    point_dao.balance = 50
    user_bot_service.cmd_pk(10, "tg1", "/pk 100")
    assert sent == [(10, "❌ 积分不足！当前积分: 50", None)]


def test_cmd_pk_preserves_win_result_group_cleanup_and_dice_side_effects(monkeypatch):
    user_bot_service, sent, deleted, tg_calls, sleeps, point_dao, random, _logger = _reset_dice_pk_state(monkeypatch, [5, 3])

    result = user_bot_service.cmd_pk(10, "tg1", "/pk 100", is_group=True, tg_name="AliceTG", user_msg_id=77)

    user_at = "<a href='tg://user?id=tg1'>AliceTG</a>"
    assert result == {"ok": True, "result": {"message_id": 902}}
    assert tg_calls == [
        ("sendDice", {"chat_id": 10, "emoji": "🎲"}),
        ("sendDice", {"chat_id": 10, "emoji": "🎲"}),
    ]
    assert sleeps == [1.5]
    assert point_dao.count_calls == [("u1", "PK%")]
    assert point_dao.balance_calls == ["u1"]
    assert point_dao.change_calls == [("u1", "Alice", "PK赢了 (骰子5vs3)", 100, None)]
    assert sent == [
        (
            10,
            f"🎲 <b>PK 开始！</b>\n\n👤 {user_at} 发起挑战\n💰 赌注：<b>100</b> 积分\n\n⏳ 正在掷骰子...",
            None,
        ),
        (
            10,
            f"🎉 <b>{user_at} 赢了！</b>\n\n🎲 掷出 <b>5</b> 点，机器人掷出 <b>3</b> 点\n💰 获得 <b>+100</b> 积分\n📊 余额：<b>1100</b> 积分",
            None,
        ),
    ]
    assert deleted == [(10, [77, 901, 501, 502, 902], 15)]
    assert random.calls == [(1, 6), (1, 6)]


def test_cmd_pk_preserves_loss_private_result(monkeypatch):
    user_bot_service, sent, deleted, _tg_calls, _sleeps, point_dao, _random, _logger = _reset_dice_pk_state(monkeypatch, [2, 6])
    point_dao.point_result = {"status": "success", "points": 900}

    result = user_bot_service.cmd_pk(10, "tg1", "/pk 100")

    assert result == {"ok": True, "result": {"message_id": 902}}
    assert point_dao.change_calls == [("u1", "Alice", "PK输了 (骰子2vs6)", -100, 100)]
    assert sent[-1] == (
        10,
        "😢 <b>你 输了！</b>\n\n🎲 掷出 <b>2</b> 点，机器人掷出 <b>6</b> 点\n💰 扣除 <b>-100</b> 积分\n📊 余额：<b>900</b> 积分",
        None,
    )
    assert deleted == []


def test_cmd_pk_preserves_dice_failure_and_point_failure(monkeypatch):
    user_bot_service, sent, _deleted, _tg_calls, _sleeps, point_dao, _random, _logger = _reset_dice_pk_state(monkeypatch, [])

    user_bot_service.cmd_pk(10, "tg1", "/pk 100")
    assert sent[-1] == (10, "❌ 发送骰子失败，请稍后重试", None)

    sent.clear()
    user_bot_service, sent, _deleted, _tg_calls, _sleeps, point_dao, _random, _logger = _reset_dice_pk_state(monkeypatch, [5, 3])
    point_dao.point_result = {"status": "failed", "message": "余额不足"}
    user_bot_service.cmd_pk(10, "tg1", "/pk 100")
    assert sent[-1] == (10, "❌ 余额不足", None)


def test_cmd_pk_preserves_tie_exception_fallback(monkeypatch):
    user_bot_service, sent, _deleted, _tg_calls, _sleeps, point_dao, _random, logger = _reset_dice_pk_state(monkeypatch, [4, 4])
    point_dao.point_result = {"status": "success", "points": 1000}

    user_bot_service.cmd_pk(10, "tg1", "/pk 100")

    assert point_dao.change_calls == [("u1", "Alice", "PK平局 (骰子4vs4)", 0, None)]
    assert logger.errors and logger.errors[0].startswith("[UserBot] PK失败: ")
    assert sent[-1][0] == 10
    assert sent[-1][1].startswith("❌ PK失败：")


def test_cmd_pk_preserves_raw_exception_message(monkeypatch):
    user_bot_service, sent, _deleted, _tg_calls, _sleeps, point_dao, _random, logger = _reset_dice_pk_state(monkeypatch, [5, 3])

    def raise_config():
        raise RuntimeError("raw pk")

    point_dao.get_point_config = raise_config
    user_bot_service.cmd_pk(10, "tg1", "/pk 100")

    assert logger.errors == ["[UserBot] PK失败: raw pk"]
    assert sent == [(10, "❌ PK失败：raw pk", None)]
