import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _sample_store_items():
    return [
        {"id": "renew30", "name": "续期30天", "cost": 100, "desc": "延长账号", "type": "renew"},
        {
            "id": "blind",
            "name": "续期盲盒",
            "cost": 80,
            "desc": "随机延期",
            "type": "random_renew",
            "base_days": 30,
            "random_min": -5,
            "random_max": 20,
        },
    ]


class FakePointDao:
    def __init__(self):
        self.points_info = {
            "points": 188,
            "store_items": _sample_store_items(),
        }
        self.redeem_result = {
            "status": "success",
            "item_name": "续期30天",
            "item_type": "renew",
            "cost": 100,
            "balance": 88,
            "new_exp_str": "2026-07-01",
        }
        self.points_calls = []
        self.redeem_calls = []
        self.raise_on_points = None
        self.raise_on_redeem = None

    def get_user_points_info(self, user_id):
        self.points_calls.append(user_id)
        if self.raise_on_points:
            raise self.raise_on_points
        return self.points_info

    def redeem_store_item(self, user_id, user_name, item_id):
        self.redeem_calls.append((user_id, user_name, item_id))
        if self.raise_on_redeem:
            raise self.raise_on_redeem
        return self.redeem_result


class FakeMediaApi:
    def __init__(self):
        self.posts = []
        self.raise_on_post = None

    def post(self, path, json=None, timeout=None):
        self.posts.append((path, json, timeout))
        if self.raise_on_post:
            raise self.raise_on_post
        return object()


class FakeLogger:
    def __init__(self):
        self.errors = []

    def error(self, message):
        self.errors.append(message)


def _reset_shop_state(monkeypatch):
    from tests.user_bot_worker_boundary import user_bot_worker_boundary as user_bot_service
    from app.bot.user_bot import user_bot_shop_commands_service

    sent = []
    replies = []
    tg_calls = []
    unbound = []
    notifications = []
    point_dao = FakePointDao()
    media_api = FakeMediaApi()
    logger = FakeLogger()
    binding = {"emby_user_id": "u1", "emby_username": "Alice"}

    def fake_send(chat_id, text, reply_markup=None):
        sent.append((chat_id, text, reply_markup))

    def fake_reply(chat_id, text, reply_markup=None, msg_id=None):
        replies.append((chat_id, text, reply_markup, msg_id))

    def fake_tg_api(method, data=None):
        tg_calls.append((method, data))

    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: binding)
    monkeypatch.setattr(user_bot_service, "_check_emby_account", lambda _binding: True)
    monkeypatch.setattr(user_bot_service, "_unbind_user", lambda tg_user_id: unbound.append(tg_user_id))
    monkeypatch.setattr(user_bot_service, "_send", fake_send)
    monkeypatch.setattr(user_bot_service, "_reply", fake_reply)
    monkeypatch.setattr(user_bot_service, "_tg_api", fake_tg_api)
    monkeypatch.setattr(user_bot_service, "_main_menu_keyboard", lambda binding_arg=None: {"menu": binding_arg})
    monkeypatch.setattr(user_bot_service, "point_dao", point_dao)
    monkeypatch.setattr(user_bot_service, "media_api", media_api)
    monkeypatch.setattr(user_bot_service, "safe_error_message", lambda _err, fallback: f"masked:{fallback}")
    monkeypatch.setattr(user_bot_service, "logger", logger)
    monkeypatch.setattr(
        user_bot_shop_commands_service,
        "_redeem_notification_sender_provider",
        lambda: (
            lambda uname, target_name, target_type, cost, actual_days: notifications.append(
                (uname, target_name, target_type, cost, actual_days)
            )
        )
    )

    return user_bot_service, sent, replies, tg_calls, unbound, notifications, point_dao, media_api, logger


def test_cmd_shop_renders_store_items_and_random_renew_details(monkeypatch):
    user_bot_service, _sent, replies, _tg_calls, _unbound, _notifications, point_dao, _media_api, _logger = _reset_shop_state(monkeypatch)

    user_bot_service.cmd_shop(10, "tg1", msg_id=5)

    assert point_dao.points_calls == ["u1"]
    assert replies == [(
        10,
        "🏪 <b>积分商城</b>\n💰 你的余额：<b>188</b> 积分\n\n"
        "• <b>续期30天</b> — 100 积分\n  延长账号\n\n"
        "🎲 <b>续期盲盒</b> — 80 积分\n  随机延期\n  ⚡ 基础30天 + 随机-5~20天 (25~50天)",
        {
            "inline_keyboard": [
                [{"text": "🛒 续期30天 (100积分)", "callback_data": "ub_redeem_renew30"}],
                [{"text": "🛒 续期盲盒 (80积分)", "callback_data": "ub_redeem_blind"}],
                [{"text": "🔙 主菜单", "callback_data": "ub_back_menu"}],
            ]
        },
        5,
    )]


def test_cmd_shop_renders_config_store_items(monkeypatch):
    user_bot_service, _sent, replies, _tg_calls, _unbound, _notifications, point_dao, _media_api, _logger = (
        _reset_shop_state(monkeypatch)
    )
    point_dao.points_info = {"points": 188, "config": {"store_items": _sample_store_items()}}

    user_bot_service.cmd_shop(10, "tg1", msg_id=5)

    assert point_dao.points_calls == ["u1"]
    assert replies == [(
        10,
        "🏪 <b>积分商城</b>\n💰 你的余额：<b>188</b> 积分\n\n"
        "• <b>续期30天</b> — 100 积分\n  延长账号\n\n"
        "🎲 <b>续期盲盒</b> — 80 积分\n  随机延期\n  ⚡ 基础30天 + 随机-5~20天 (25~50天)",
        {
            "inline_keyboard": [
                [{"text": "🛒 续期30天 (100积分)", "callback_data": "ub_redeem_renew30"}],
                [{"text": "🛒 续期盲盒 (80积分)", "callback_data": "ub_redeem_blind"}],
                [{"text": "🔙 主菜单", "callback_data": "ub_back_menu"}],
            ]
        },
        5,
    )]


def test_cmd_shop_preserves_unbound_deleted_and_empty_store_paths(monkeypatch):
    user_bot_service, sent, replies, _tg_calls, unbound, _notifications, point_dao, _media_api, _logger = _reset_shop_state(monkeypatch)

    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: None)
    user_bot_service.cmd_shop(10, "tg1")
    assert sent == [(10, "❌ 请先绑定账号：/bind 用户名", None)]

    sent.clear()
    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: {"emby_user_id": "u1", "emby_username": "Alice"})
    monkeypatch.setattr(user_bot_service, "_check_emby_account", lambda _binding: False)
    user_bot_service.cmd_shop(10, "tg1")
    assert unbound == ["tg1"]
    assert sent == [(10, "⚠️ 你的 Emby 账号已被删除，绑定已自动解除。请联系管理员。", {"menu": None})]

    sent.clear()
    monkeypatch.setattr(user_bot_service, "_check_emby_account", lambda _binding: True)
    point_dao.points_info = {"points": 0, "store_items": []}
    user_bot_service.cmd_shop(10, "tg1", msg_id=6)
    assert replies == [(
        10,
        "🏪 积分商城暂无商品",
        {"inline_keyboard": [[{"text": "🔙 主菜单", "callback_data": "ub_back_menu"}]]},
        6,
    )]


def test_cmd_redeem_callback_preserves_success_side_effects(monkeypatch):
    user_bot_service, sent, _replies, tg_calls, _unbound, notifications, point_dao, media_api, _logger = _reset_shop_state(monkeypatch)

    user_bot_service.cmd_redeem_callback(10, "tg1", "renew30", "cq1")

    assert tg_calls == [("answerCallbackQuery", {"callback_query_id": "cq1"})]
    assert point_dao.redeem_calls == [("u1", "Alice", "renew30")]
    assert media_api.posts == [("/Users/u1/Policy", {"IsDisabled": False}, 3)]
    assert sent == [(
        10,
        "✅ <b>兑换成功！</b>\n\n🛒 续期30天\n💰 花费 100 积分，余额 88\n📅 账号已续期至 2026-07-01",
        None,
    )]
    assert notifications == [("Alice", "续期30天", "renew", 100, 0)]


def test_cmd_redeem_callback_preserves_business_error_and_masked_exception(monkeypatch):
    user_bot_service, sent, _replies, tg_calls, _unbound, _notifications, point_dao, _media_api, logger = _reset_shop_state(monkeypatch)
    point_dao.redeem_result = {"status": "error", "message": "积分不足"}

    user_bot_service.cmd_redeem_callback(10, "tg1", "renew30", "cq1")

    assert tg_calls == [("answerCallbackQuery", {"callback_query_id": "cq1"})]
    assert sent == [(10, "❌ 积分不足", None)]

    sent.clear()
    tg_calls.clear()
    point_dao.raise_on_redeem = RuntimeError("raw redeem")
    user_bot_service.cmd_redeem_callback(10, "tg1", "renew30", "cq2")
    assert tg_calls == [("answerCallbackQuery", {"callback_query_id": "cq2"})]
    assert logger.errors == ["[兑换] 执行失败: raw redeem"]
    assert sent == [(10, "❌ 兑换失败：masked:兑换操作异常，请稍后重试", None)]
