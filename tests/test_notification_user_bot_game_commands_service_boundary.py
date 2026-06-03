import datetime as real_datetime
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeDateTime:
    timedelta = real_datetime.timedelta

    class datetime:
        @classmethod
        def now(cls):
            return real_datetime.datetime(2026, 6, 3, 12, 0, 0)


class FakePointDao:
    def __init__(self):
        self.config = {
            "enable_lottery": 1,
            "lottery_cost": 10,
            "lottery_max_per_day": 3,
            "lottery_draw_hour": 20,
            "lottery_pool_ratio_1": 50,
            "lottery_pool_ratio_2": 20,
            "lottery_pool_ratio_3": 10,
            "lottery_pool_ratio_4": 5,
            "lottery_lucky_count": 1,
            "lottery_lucky_ratio": 5,
        }
        self.grab_result = {
            "status": "success",
            "amount": 12,
            "balance": 88,
            "is_last_one": False,
        }
        self.grab_calls = []
        self.ticket_numbers = []
        self.balance = 100
        self.buy_result = {"status": "success", "new_points": 80}
        self.buy_calls = []
        self.winning_numbers = {}
        self.user_tickets = []
        self.pool_info = {"today_pool": 1000, "today_tickets": 4}

    def get_point_config(self):
        return self.config

    def grab_red_packet(self, packet_id, user_id, username, allow_creator=False):
        self.grab_calls.append((packet_id, user_id, username, allow_creator))
        return self.grab_result

    def list_user_lottery_tickets(self, user_id):
        return self.user_tickets

    def get_lottery_winning_numbers(self, draw_date):
        return self.winning_numbers.get(draw_date)

    def get_latest_lottery_result(self):
        return None

    def list_lottery_winners_for_date(self, draw_date):
        return []

    def get_lottery_pool_info(self, user_id, today, target_date):
        return self.pool_info

    def list_lottery_ticket_numbers(self, user_id, draw_date):
        return self.ticket_numbers

    def get_user_points_balance(self, user_id):
        return self.balance

    def buy_lottery_tickets(self, user_id, username, count, cost, max_per_day, draw_date, numbers):
        self.buy_calls.append((user_id, username, count, cost, max_per_day, draw_date, numbers))
        return self.buy_result


class FakeLogger:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.infos = []

    def error(self, message):
        self.errors.append(message)

    def warning(self, message):
        self.warnings.append(message)

    def info(self, message):
        self.infos.append(message)


def _reset_game_state(monkeypatch):
    from tests.user_bot_worker_boundary import user_bot_worker_boundary as user_bot_service

    sent = []
    deleted = []
    point_dao = FakePointDao()
    logger = FakeLogger()
    binding = {"emby_user_id": "u1", "emby_username": "Alice"}

    def fake_send(chat_id, text, reply_markup=None):
        sent.append((chat_id, text, reply_markup))
        return {"ok": True, "result": {"message_id": 900 + len(sent)}}

    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: binding)
    monkeypatch.setattr(user_bot_service, "_send", fake_send)
    monkeypatch.setattr(
        user_bot_service,
        "_delete_messages_later",
        lambda chat_id, ids, delay_seconds=30: deleted.append((chat_id, ids, delay_seconds)),
    )
    monkeypatch.setattr(user_bot_service, "point_dao", point_dao)
    monkeypatch.setattr(user_bot_service, "datetime", FakeDateTime)
    monkeypatch.setattr(user_bot_service, "logger", logger)

    return user_bot_service, sent, deleted, point_dao, logger


def test_cmd_grab_preserves_unbound_message(monkeypatch):
    user_bot_service, sent, _deleted, point_dao, _logger = _reset_game_state(monkeypatch)
    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: None)

    user_bot_service.cmd_grab(10, "tg1", "/grab 123", is_group=True, tg_name="AliceTG", user_msg_id=77)

    assert sent == [(10, "❌ 请先私聊机器人绑定账号", None)]
    assert point_dao.grab_calls == []


def test_cmd_grab_sends_last_packet_notice_and_schedules_group_cleanup(monkeypatch):
    user_bot_service, sent, deleted, point_dao, _logger = _reset_game_state(monkeypatch)
    point_dao.grab_result = {
        "status": "success",
        "amount": 12,
        "balance": 88,
        "is_last_one": True,
        "creator_name": "Bob",
        "total_amount": 100,
        "total_count": 2,
        "grab_logs": [{"user_name": "AliceTG", "amount": 12}],
        "chat_id": "20",
        "message_id": 66,
    }

    result = user_bot_service.cmd_grab(10, "tg1", "/grab 123", is_group=True, tg_name="AliceTG", user_msg_id=77)

    assert point_dao.grab_calls == [(123, "u1", "AliceTG", False)]
    assert sent == [
        (
            "20",
            "🧧 <b>红包已抢完</b>\n\n"
            "👤 <b>发红包</b>: Bob\n"
            "💰 <b>总金额</b>: 100 积分\n"
            "📦 <b>总个数</b>: 2 个\n\n"
            "📋 <b>领取明细</b>:\n"
            "1. AliceTG: 12 积分\n",
            None,
        ),
        (
            10,
            "🎉 <b>恭喜你！</b>\n\n🧧 抢到 <b>12</b> 积分\n💰 余额：<b>88</b> 积分",
            None,
        ),
    ]
    assert deleted == [(20, [66], 15), (10, [902, 77], 15)]
    assert result == {"ok": True, "result": {"message_id": 902}}


def test_cmd_grab_preserves_numeric_and_raw_exception_errors(monkeypatch):
    user_bot_service, sent, _deleted, point_dao, logger = _reset_game_state(monkeypatch)

    user_bot_service.cmd_grab(10, "tg1", "/grab abc")
    assert sent == [(10, "❌ 红包ID必须是数字", None)]

    sent.clear()

    def raise_grab(*_args, **_kwargs):
        raise RuntimeError("raw grab")

    point_dao.grab_red_packet = raise_grab
    user_bot_service.cmd_grab(10, "tg1", "/grab 123")

    assert logger.errors == ["[UserBot] 抢红包失败: raw grab"]
    assert sent == [(10, "❌ 抢红包失败：raw grab", None)]


def test_cmd_lottery_preserves_disabled_and_my_ticket_view(monkeypatch):
    user_bot_service, sent, _deleted, point_dao, _logger = _reset_game_state(monkeypatch)

    point_dao.config["enable_lottery"] = 0
    user_bot_service.cmd_lottery(10, "tg1", "/lottery")
    assert sent == [(10, "❌ 彩票功能未开启", None)]

    sent.clear()
    point_dao.config["enable_lottery"] = 1
    point_dao.user_tickets = [{"numbers": "1234", "cost": 10, "draw_date": "2026-06-02"}]
    point_dao.winning_numbers["2026-06-02"] = {"winning_numbers": "1234"}

    user_bot_service.cmd_lottery(10, "tg1", "/lottery my")

    assert sent == [(10, "🎫 <b>我的彩票</b>\n\n📅 2026-06-02\n  1234 | 🏆 一等奖\n", None)]


def test_cmd_lottery_preserves_pool_view_and_purchase_group_cleanup(monkeypatch):
    user_bot_service, sent, deleted, point_dao, _logger = _reset_game_state(monkeypatch)

    user_bot_service.cmd_lottery(10, "tg1", "/lottery pool")

    assert sent == [(
        10,
        "🎰 <b>当前奖池</b> (2026-06-03)\n\n"
        "💰 奖池总额: <b>1000</b> 积分\n"
        "🎫 本期购票: <b>4</b> 张\n\n"
        "📋 本期状态: ⏳ 未开奖\n"
        "⏰ 下次开奖: 今天 20:00\n\n"
        "📊 奖池分配:\n"
        "• 一等奖: 50% = 500 积分\n"
        "• 二等奖: 20% = 200 积分\n"
        "• 三等奖: 10% = 100 积分\n"
        "• 三等奖: 10% = 100 积分\n"
        "• 安慰奖: 5% = 50 积分\n"
        "• 幸运奖: 5% = 50 积分 (抽1人)\n",
        None,
    )]

    sent.clear()
    user_bot_service.cmd_lottery(10, "tg1", "/lottery 1234 5678", is_group=True, user_msg_id=77)

    assert point_dao.buy_calls == [("u1", "Alice", 2, 10, 3, "2026-06-03", ["1234", "5678"])]
    assert sent == [(
        10,
        "🎫 <b>购买成功！</b>\n\n"
        "1. 号码: <b>1234</b>\n"
        "2. 号码: <b>5678</b>\n"
        "\n💰 花费: 20 积分\n📊 余额: 80 积分\n\n⏰ 开奖时间: 今天 20:00",
        None,
    )]
    assert deleted == [(10, [901, 77], 15)]
