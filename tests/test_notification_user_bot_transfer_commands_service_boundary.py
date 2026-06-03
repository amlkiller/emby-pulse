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
        self.user_info = {"Policy": {"IsAdministrator": True}}
        self.calls = []

    def get(self, path, timeout=None):
        self.calls.append((path, timeout))
        if path == "/Users":
            return FakeResponse(self.users)
        return FakeResponse(self.user_info)


class FakePointDao:
    def __init__(self):
        self.transfer_result = {"status": "success", "balance": 80, "actual_amount": 10, "fee": 1}
        self.config = {"enable_red_packet": 1, "red_packet_admin_only": 1, "red_packet_expire_hours": 12}
        self.red_packet_result = {"status": "success", "packet_id": "p1", "balance": 90}
        self.transfer_calls = []
        self.create_calls = []
        self.saved_messages = []
        self.raise_on_transfer = None

    def transfer_points(self, from_user_id, from_user_name, to_user_id, to_user_name, amount, target_exists=False):
        self.transfer_calls.append((from_user_id, from_user_name, to_user_id, to_user_name, amount, target_exists))
        if self.raise_on_transfer:
            raise self.raise_on_transfer
        return self.transfer_result

    def get_point_config(self):
        return self.config

    def create_red_packet(self, total_amount, total_count, chat_id, creator_id, creator_name):
        self.create_calls.append((total_amount, total_count, chat_id, creator_id, creator_name))
        return self.red_packet_result

    def save_red_packet_message_id(self, packet_id, msg_id):
        self.saved_messages.append((packet_id, msg_id))


class FakeUserBotDao:
    def __init__(self):
        self.username_map = {"bob": "tg2"}
        self.bindings = {
            "tg2": {"emby_user_id": "u2", "emby_username": "Bob", "tg_display_name": "Bobby"},
            "Bob": {"emby_user_id": "u2", "emby_username": "Bob", "tg_display_name": ""},
        }
        self.username_calls = []
        self.binding_calls = []

    def get_tg_user_id_by_username(self, tg_username):
        self.username_calls.append(tg_username)
        return self.username_map.get(tg_username)

    def get_binding_by_tg_user_or_username(self, identifier):
        self.binding_calls.append(identifier)
        return self.bindings.get(identifier)


class FakeLogger:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, message):
        self.errors.append(message)

    def warning(self, message):
        self.warnings.append(message)


def _reset_transfer_state(monkeypatch):
    from tests.user_bot_worker_boundary import user_bot_worker_boundary as user_bot_service

    sent = []
    deleted = []
    point_dao = FakePointDao()
    user_bot_dao = FakeUserBotDao()
    media_api = FakeMediaApi()
    logger = FakeLogger()
    binding = {"emby_user_id": "u1", "emby_username": "Alice"}

    def fake_send(chat_id, text, reply_markup=None):
        sent.append((chat_id, text, reply_markup))
        return {"ok": True, "result": {"message_id": 900 + len(sent)}}

    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: binding)
    monkeypatch.setattr(user_bot_service, "_send", fake_send)
    monkeypatch.setattr(user_bot_service, "_delete_messages_later", lambda chat_id, ids, delay_seconds=30: deleted.append((chat_id, ids, delay_seconds)))
    monkeypatch.setattr(user_bot_service, "point_dao", point_dao)
    monkeypatch.setattr(user_bot_service, "user_bot_dao", user_bot_dao)
    monkeypatch.setattr(user_bot_service, "media_api", media_api)
    monkeypatch.setattr(user_bot_service, "logger", logger)

    return user_bot_service, sent, deleted, point_dao, user_bot_dao, media_api, logger


def test_cmd_transfer_uses_mention_target_and_schedules_group_cleanup(monkeypatch):
    user_bot_service, sent, deleted, point_dao, user_bot_dao, _media_api, _logger = _reset_transfer_state(monkeypatch)

    result = user_bot_service.cmd_transfer(
        10,
        "tg1",
        "/transfer @bob 10",
        is_group=True,
        entities=[{"type": "mention", "offset": 10, "length": 4}],
    )

    assert user_bot_dao.username_calls == ["bob"]
    assert user_bot_dao.binding_calls == ["tg2"]
    assert point_dao.transfer_calls == [("u1", "Alice", "u2", "Bob", 10, True)]
    assert sent == [(10, "✅ 转赠成功！\n\n💰 已转赠 <b>10</b> 积分给 <b>Bobby</b>\n💸 手续费：1 积分\n📊 余额：80", None)]
    assert deleted == [(10, [901], 15)]
    assert result == {"ok": True, "result": {"message_id": 901}}


def test_cmd_transfer_falls_back_to_emby_user_and_preserves_errors(monkeypatch):
    user_bot_service, sent, _deleted, point_dao, user_bot_dao, media_api, logger = _reset_transfer_state(monkeypatch)
    user_bot_dao.bindings = {}

    user_bot_service.cmd_transfer(10, "tg1", "/transfer Bob 5")
    assert media_api.calls == [("/Users", 5)]
    assert point_dao.transfer_calls == [("u1", "Alice", "u2", "Bob", 5, True)]

    sent.clear()
    point_dao.raise_on_transfer = RuntimeError("raw transfer")
    user_bot_service.cmd_transfer(10, "tg1", "/transfer Bob 5")
    assert logger.errors == ["[UserBot] 转赠失败: raw transfer"]
    assert sent == [(10, "❌ 转赠失败：raw transfer", None)]


def test_cmd_transfer_preserves_unbound_and_numeric_validation(monkeypatch):
    user_bot_service, sent, _deleted, point_dao, _user_bot_dao, _media_api, _logger = _reset_transfer_state(monkeypatch)
    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: None)

    user_bot_service.cmd_transfer(10, "tg1", "/transfer @bob 10")
    assert sent == [(10, "❌ 请先私聊机器人绑定账号", None)]
    assert point_dao.transfer_calls == []

    sent.clear()
    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: {"emby_user_id": "u1", "emby_username": "Alice"})
    user_bot_service.cmd_transfer(10, "tg1", "/transfer @bob abc")
    assert sent == [(10, "❌ 积分必须是数字", None)]


def test_cmd_redpacket_preserves_success_message_save_and_group_cleanup(monkeypatch):
    user_bot_service, sent, deleted, point_dao, _user_bot_dao, media_api, _logger = _reset_transfer_state(monkeypatch)

    result = user_bot_service.cmd_redpacket(10, "tg1", "/hb 100 5", is_group=True, tg_name="AliceTG", user_msg_id=77)

    assert media_api.calls == [("/Users/u1", 5)]
    assert point_dao.create_calls == [(100, 5, "10", "u1", "AliceTG")]
    assert point_dao.saved_messages == [("p1", 901)]
    assert sent == [(
        10,
        "🧧 <b>积分红包</b>\n\n🆔 红包ID：<b>#p1</b>\n💰 总金额：<b>100</b> 积分\n📦 共 <b>5</b> 个\n⏰ 12小时后过期\n\n💡 发送 /grab p1 抢红包",
        None,
    )]
    assert deleted == [(10, [77], 15)]
    assert result == {"ok": True, "result": {"message_id": 901}}


def test_cmd_redpacket_preserves_disabled_admin_and_numeric_errors(monkeypatch):
    user_bot_service, sent, _deleted, point_dao, _user_bot_dao, media_api, _logger = _reset_transfer_state(monkeypatch)

    point_dao.config["enable_red_packet"] = 0
    user_bot_service.cmd_redpacket(10, "tg1", "/hb 100 5")
    assert sent == [(10, "❌ 积分红包功能未开启", None)]

    sent.clear()
    point_dao.config["enable_red_packet"] = 1
    media_api.user_info = {"Policy": {"IsAdministrator": False}}
    user_bot_service.cmd_redpacket(10, "tg1", "/hb 100 5")
    assert sent == [(10, "❌ 仅管理员可发红包", None)]

    sent.clear()
    user_bot_service.cmd_redpacket(10, "tg1", "/hb abc 5")
    assert sent == [(10, "❌ 参数必须是数字", None)]
