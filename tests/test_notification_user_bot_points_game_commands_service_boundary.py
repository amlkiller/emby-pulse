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
        self.users = [
            {"Id": "u1", "Name": "Alice"},
            {"Id": "u2", "Name": "Bob"},
            {"Id": "u3", "Name": "Charlie"},
        ]
        self.calls = []

    def get(self, path, timeout=None):
        self.calls.append((path, timeout))
        return FakeResponse(self.users)


class FakePointDao:
    def __init__(self):
        self.rank_rows = [
            {"user_id": "u1", "points": 100},
            {"user_id": "u2", "points": 50},
            {"user_id": "deleted", "points": 40},
            {"user_id": "u3", "points": 30},
        ]
        self.rob_result = {"status": "success", "success": True, "amount": 12, "balance": 88}
        self.rob_calls = []
        self.raise_on_rob = None

    def list_point_rank(self, limit=10):
        return self.rank_rows[:limit]

    def rob_points(self, from_user_id, from_user_name, to_user_id, to_user_name):
        self.rob_calls.append((from_user_id, from_user_name, to_user_id, to_user_name))
        if self.raise_on_rob:
            raise self.raise_on_rob
        return self.rob_result


class FakeUserBotDao:
    def __init__(self):
        self.tg_rows = [
            {"emby_user_id": "u1", "tg_display_name": "AliceTG", "tg_username": ""},
            {"emby_user_id": "u2", "tg_display_name": "", "tg_username": "bob_tg"},
        ]
        self.username_map = {"bob": "tg2"}
        self.bindings = {
            "tg2": {"emby_user_id": "u2", "emby_username": "Bob", "tg_display_name": "Bobby"},
            "Bob": {"emby_user_id": "u2", "emby_username": "Bob", "tg_display_name": "Bobby"},
        }
        self.username_calls = []
        self.binding_calls = []

    def list_tg_binding_names(self):
        return self.tg_rows

    def get_tg_user_id_by_username(self, tg_username):
        self.username_calls.append(tg_username)
        return self.username_map.get(tg_username)

    def get_binding_by_tg_user_or_username(self, identifier):
        self.binding_calls.append(identifier)
        return self.bindings.get(identifier)


class FakeLogger:
    def __init__(self):
        self.errors = []

    def error(self, message):
        self.errors.append(message)


def _reset_points_game_state(monkeypatch):
    from app.domains.notifications import user_bot_service

    sent = []
    point_dao = FakePointDao()
    user_bot_dao = FakeUserBotDao()
    media_api = FakeMediaApi()
    logger = FakeLogger()
    binding = {"emby_user_id": "u1", "emby_username": "Alice"}

    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: binding)
    monkeypatch.setattr(user_bot_service, "_send", lambda chat_id, text, reply_markup=None: sent.append((chat_id, text, reply_markup)))
    monkeypatch.setattr(user_bot_service, "point_dao", point_dao)
    monkeypatch.setattr(user_bot_service, "user_bot_dao", user_bot_dao)
    monkeypatch.setattr(user_bot_service, "media_api", media_api)
    monkeypatch.setattr(user_bot_service, "safe_error_message", lambda _err, fallback: f"masked:{fallback}")
    monkeypatch.setattr(user_bot_service, "logger", logger)

    return user_bot_service, sent, point_dao, user_bot_dao, media_api, logger


def test_cmd_rank_filters_deleted_users_and_preserves_name_display(monkeypatch):
    user_bot_service, sent, _point_dao, _user_bot_dao, media_api, _logger = _reset_points_game_state(monkeypatch)

    user_bot_service.cmd_rank(10, "tg1", is_group=True)

    assert media_api.calls == [("/Users", 5)]
    assert sent == [(
        10,
        "🏆 <b>积分排行榜 Top 10</b>\n\n"
        "🥇 <b>AliceTG</b> - 100 积分\n"
        "🥈 <b>@bob_tg</b> - 50 积分\n"
        "🥉 <b>Ch***</b> - 30 积分",
        None,
    )]


def test_cmd_rob_preserves_unbound_message(monkeypatch):
    user_bot_service, sent, point_dao, _user_bot_dao, _media_api, _logger = _reset_points_game_state(monkeypatch)
    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: None)

    user_bot_service.cmd_rob(10, "tg1", "/rob @bob", is_group=True)

    assert sent == [(10, "❌ 请先私聊机器人绑定账号", None)]
    assert point_dao.rob_calls == []


def test_cmd_rob_uses_mention_entity_target_resolution(monkeypatch):
    user_bot_service, sent, point_dao, user_bot_dao, _media_api, _logger = _reset_points_game_state(monkeypatch)

    user_bot_service.cmd_rob(
        10,
        "tg1",
        "/rob @bob",
        entities=[{"type": "mention", "offset": 5, "length": 4}],
    )

    assert user_bot_dao.username_calls == ["bob"]
    assert user_bot_dao.binding_calls == ["tg2"]
    assert point_dao.rob_calls == [("u1", "Alice", "u2", "Bob")]
    assert sent == [(
        10,
        "🎉 <b>打劫成功！</b>\n\n👤 从 <b>Bobby</b> 身上抢到 <b>12</b> 积分\n💰 当前余额：<b>88</b> 积分",
        None,
    )]


def test_cmd_rob_uses_safe_error_message_on_failure(monkeypatch):
    user_bot_service, sent, point_dao, _user_bot_dao, _media_api, logger = _reset_points_game_state(monkeypatch)
    point_dao.raise_on_rob = RuntimeError("raw failure")

    user_bot_service.cmd_rob(10, "tg1", "/rob Bob")

    assert logger.errors == ["[UserBot] 打劫失败: raw failure"]
    assert sent == [(10, "❌ 打劫失败：masked:打劫操作异常，请稍后重试", None)]
