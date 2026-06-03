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
        self.user_info = {"Policy": {"IsAdministrator": True}}
        self.calls = []

    def get(self, path, timeout=None):
        self.calls.append((path, timeout))
        return FakeResponse(self.user_info)


class FakeRandom:
    def __init__(self):
        self.random_values = [0.001, 0.05, 0.2, 0.8]
        self.randint_calls = []
        self.choice_calls = []
        self.shuffled = []

    def random(self):
        return self.random_values.pop(0)

    def choice(self, values):
        self.choice_calls.append(tuple(values))
        return 888

    def randint(self, start, end):
        self.randint_calls.append((start, end))
        return start

    def shuffle(self, values):
        self.shuffled.append(list(values))


class FakePointDao:
    def __init__(self):
        self.config = {
            "enable_scratch": 1,
            "scratch_cost": 100,
            "scratch_admin_only": 0,
            "scratch_slots": 4,
            "scratch_big_prize_rate": 1,
            "scratch_medium_prize_rate": 10,
        }
        self.active_card = {
            "id": 7,
            "total_slots": 4,
            "filled_slots": 1,
            "price": 100,
            "status": "active",
        }
        self.slots = [
            (1, 1, "Bob"),
            (2, 0, ""),
            (3, 0, ""),
            (4, 0, ""),
        ]
        self.created_cards = []
        self.saved_messages = []
        self.card = {
            "id": 7,
            "total_slots": 4,
            "filled_slots": 1,
            "price": 100,
            "status": "active",
            "chat_id": "20",
            "message_id": 66,
        }
        self.update_result = {
            "status": "success",
            "new_points": 80,
            "new_filled": 2,
            "total_slots": 4,
            "chat_id": "20",
            "message_id": 66,
        }
        self.update_calls = []
        self.completed_slots = [
            {"slot_number": 1, "prize_amount": 888, "user_id": "u1", "username": "Alice"},
            {"slot_number": 2, "prize_amount": 8, "user_id": "u2", "username": ""},
        ]
        self.origin = {"chat_id": "20", "message_id": 66}

    def get_point_config(self):
        return self.config

    def get_active_scratch_card(self):
        return self.active_card

    def get_scratch_card_slots(self, card_id):
        return self.slots

    def create_scratch_card(self, total_slots=9, price=100, created_by="", chat_id=None, prizes=None):
        self.created_cards.append((total_slots, price, created_by, chat_id, prizes))
        return {"status": "success", "card_id": 7}

    def save_scratch_card_message_id(self, card_id, message_id):
        self.saved_messages.append((card_id, message_id))

    def get_scratch_card(self, card_id):
        return self.card

    def update_scratch_card_slot(self, card_id, slot_number, user_id, username, price, display_name):
        self.update_calls.append((card_id, slot_number, user_id, username, price, display_name))
        return self.update_result

    def complete_scratch_card(self, card_id):
        return self.completed_slots

    def get_scratch_card_origin(self, card_id):
        return self.origin


class FakeLogger:
    def __init__(self):
        self.errors = []
        self.infos = []

    def error(self, message):
        self.errors.append(message)

    def info(self, message):
        self.infos.append(message)


def _reset_scratch_state(monkeypatch):
    from tests.user_bot_worker_boundary import user_bot_worker_boundary as user_bot_service

    sent = []
    deleted = []
    tg_calls = []
    point_dao = FakePointDao()
    media_api = FakeMediaApi()
    fake_random = FakeRandom()
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
    monkeypatch.setattr(user_bot_service, "_tg_api", lambda method, data: tg_calls.append((method, data)))
    monkeypatch.setattr(user_bot_service, "point_dao", point_dao)
    monkeypatch.setattr(user_bot_service, "media_api", media_api)
    monkeypatch.setattr(user_bot_service, "random", fake_random)
    monkeypatch.setattr(user_bot_service, "logger", logger)

    return user_bot_service, sent, deleted, tg_calls, point_dao, media_api, fake_random, logger


def test_cmd_scratch_preserves_disabled_and_info_view(monkeypatch):
    user_bot_service, sent, _deleted, _tg_calls, point_dao, _media_api, _random, _logger = _reset_scratch_state(monkeypatch)

    point_dao.config["enable_scratch"] = 0
    user_bot_service.cmd_scratch(10, "tg1", "/scratch")
    assert sent == [(10, "❌ 刮刮乐功能未开启", None)]

    sent.clear()
    point_dao.config["enable_scratch"] = 1
    user_bot_service.cmd_scratch(10, "tg1", "/scratch")

    assert sent == [(
        10,
        "🎰 <b>刮刮乐 #7</b>\n\n💰 售价: 100 积分/次\n📊 进度: 1/4 已刮\n\n⚠️ 点击下方按钮刮奖，每人只能刮一次！",
        {"inline_keyboard": [[
            {"text": "1✅", "callback_data": "scratch_done_7_1"},
            {"text": "2", "callback_data": "scratch_7_2"},
            {"text": "3", "callback_data": "scratch_7_3"},
        ], [
            {"text": "4", "callback_data": "scratch_7_4"},
        ]]},
    )]


def test_cmd_scratch_create_preserves_admin_check_message_save_and_group_cleanup(monkeypatch):
    user_bot_service, sent, deleted, _tg_calls, point_dao, media_api, fake_random, _logger = _reset_scratch_state(monkeypatch)
    point_dao.config["scratch_admin_only"] = 1

    result = user_bot_service.cmd_scratch(10, "tg1", "/scratch 开始", is_group=True, tg_name="AliceTG", user_msg_id=77)

    assert media_api.calls == [("/Users/u1", 5)]
    assert point_dao.created_cards == [(4, 100, "AliceTG", 10, [888, 50, 10, 1])]
    assert fake_random.choice_calls == [(666, 888, 999)]
    assert fake_random.randint_calls == [(50, 200), (10, 50), (1, 10)]
    assert point_dao.saved_messages == [(7, 901)]
    assert sent == [(
        10,
        "🎰 <b>刮刮乐开始！</b>\n\n"
        "👤 发起人: AliceTG\n"
        "💰 售价: 100 积分/次\n"
        "🎯 共 4 个格子\n\n"
        "🏆 大奖: 666/888/999 积分\n"
        "🎯 中奖: 50-200 积分\n"
        "🎁 小奖: 10-50 积分\n"
        "😅 保底: 1-10 积分\n\n"
        "⚠️ 每人只能刮一次！",
        {"inline_keyboard": [[
            {"text": "1", "callback_data": "scratch_7_1"},
            {"text": "2", "callback_data": "scratch_7_2"},
            {"text": "3", "callback_data": "scratch_7_3"},
        ], [
            {"text": "4", "callback_data": "scratch_7_4"},
        ]]},
    )]
    assert deleted == [(10, [77], 15)]
    assert result == {"ok": True, "result": {"message_id": 901}}


def test_handle_scratch_uses_legacy_update_wrapper_and_sends_progress(monkeypatch):
    user_bot_service, sent, _deleted, _tg_calls, point_dao, _media_api, _random, _logger = _reset_scratch_state(monkeypatch)
    updates = []
    monkeypatch.setattr(user_bot_service, "_update_scratch_message", lambda chat_id, msg_id, card_id: updates.append((chat_id, msg_id, card_id)))

    user_bot_service._handle_scratch(10, "tg1", 7, 2, tg_name="AliceTG")

    assert point_dao.update_calls == [(7, 2, "u1", "Alice", 100, "AliceTG")]
    assert updates == [("20", 66, 7)]
    assert sent == [(
        10,
        "✅ <b>AliceTG 刮开了格子 2</b>\n\n📊 进度: 2/4 已刮\n💳 余额: 80 积分\n\n⏳ 等待其他 2 个格子被刮开...",
        None,
    )]


def test_handle_scratch_uses_legacy_draw_wrapper_for_last_slot(monkeypatch):
    user_bot_service, sent, _deleted, _tg_calls, point_dao, _media_api, _random, _logger = _reset_scratch_state(monkeypatch)
    point_dao.update_result["new_filled"] = 4
    draws = []
    monkeypatch.setattr(user_bot_service, "_scratch_draw_result", lambda chat_id, card_id: draws.append((chat_id, card_id)))

    user_bot_service._handle_scratch(10, "tg1", 7, 4)

    assert draws == [(10, 7)]
    assert sent == []


def test_update_scratch_message_and_draw_result_preserve_side_effects(monkeypatch):
    user_bot_service, sent, deleted, tg_calls, point_dao, _media_api, _random, _logger = _reset_scratch_state(monkeypatch)

    user_bot_service._update_scratch_message("20", 66, 7)
    assert tg_calls == [(
        "editMessageReplyMarkup",
        {
            "chat_id": "20",
            "message_id": 66,
            "reply_markup": {"inline_keyboard": [[
                {"text": "1✅", "callback_data": "scratch_done_7_1"},
                {"text": "2", "callback_data": "scratch_7_2"},
                {"text": "3", "callback_data": "scratch_7_3"},
            ], [
                {"text": "4", "callback_data": "scratch_7_4"},
            ]]},
        },
    )]

    user_bot_service._scratch_draw_result(10, 7)

    assert deleted == [(20, [66], 15)]
    assert sent == [(
        10,
        "🎊 <b>刮刮乐 #7 开奖！</b>\n\n"
        "📋 中奖明细:\n"
        "1. 🏆 Alice: 888 积分\n"
        "2. 😅 未知: 8 积分\n"
        "\n💰 总发放: 896 积分",
        None,
    )]
