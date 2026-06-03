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
            return real_datetime.datetime(2026, 6, 3, 20, 0, 0)


class FakeRandom:
    def __init__(self):
        self.randint_values = [1, 2, 3, 4]
        self.sample_calls = []

    def randint(self, start, end):
        assert (start, end) == (0, 9)
        return self.randint_values.pop(0)

    def sample(self, population, count):
        self.sample_calls.append((population, count))
        return population[:count]


class FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code


class FakeMediaApi:
    def __init__(self):
        self.calls = []
        self.status_by_path = {}
        self.raise_paths = set()

    def get(self, path, timeout=None):
        self.calls.append((path, timeout))
        if path in self.raise_paths:
            raise RuntimeError("media offline")
        return FakeResponse(self.status_by_path.get(path, 200))


class FakePointDao:
    def __init__(self):
        self.draw_context = {
            "already_drawn": False,
            "winning_numbers": "",
            "total_pool": 1000,
            "tickets": [
                {"id": 1, "user_id": "u1", "username": "Alice", "numbers": "1234"},
                {"id": 2, "user_id": "u2", "username": "Bob", "numbers": "1235"},
                {"id": 3, "user_id": "u3", "username": "Deleted", "numbers": "1234"},
            ],
        }
        self.config = {
            "lottery_pool_ratio_1": 50,
            "lottery_pool_ratio_2": 20,
            "lottery_pool_ratio_3": 10,
            "lottery_pool_ratio_4": 5,
            "lottery_lucky_count": 1,
            "lottery_lucky_ratio": 5,
        }
        self.saved = []
        self.save_result = {"status": "success"}

    def get_lottery_draw_context(self, draw_date):
        assert draw_date == "2026-06-03"
        return self.draw_context

    def get_point_config(self):
        return self.config

    def save_lottery_draw_result(self, draw_date, winning_numbers, winners_by_level, lucky_winners, remaining_pool):
        self.saved.append((draw_date, winning_numbers, winners_by_level, lucky_winners, remaining_pool))
        return self.save_result


class FakeUserBotDao:
    def __init__(self):
        self.names = {}
        self.calls = []

    def get_bot_user_name(self, tg_user_id):
        self.calls.append(tg_user_id)
        return self.names.get(tg_user_id)


class FakeLogger:
    def __init__(self):
        self.infos = []
        self.warnings = []
        self.errors = []

    def info(self, message):
        self.infos.append(message)

    def warning(self, message):
        self.warnings.append(message)

    def error(self, message):
        self.errors.append(message)


def _reset_lottery_draw_state(monkeypatch):
    from app.bot.user_bot import user_bot_lottery_draw_service
    from app.bot.user_bot import user_bot_service

    sent = []
    point_dao = FakePointDao()
    media_api = FakeMediaApi()
    random_source = FakeRandom()
    user_bot_dao = FakeUserBotDao()
    logger = FakeLogger()
    bindings = {"u1": {"tg_user_id": "tg1"}}
    user_bot_dao.names["tg1"] = "AliceTG"

    monkeypatch.setattr(user_bot_service, "datetime", FakeDateTime)
    monkeypatch.setattr(user_bot_service, "random", random_source)
    monkeypatch.setattr(user_bot_service, "point_dao", point_dao)
    monkeypatch.setattr(user_bot_service, "media_api", media_api)
    monkeypatch.setattr(user_bot_service, "get_user_bot_allowed_groups", lambda: "-1001\n-1002")
    monkeypatch.setattr(user_bot_service, "_get_binding_by_emby_id", lambda user_id: bindings.get(user_id))
    monkeypatch.setattr(user_bot_service, "user_bot_dao", user_bot_dao)
    monkeypatch.setattr(user_bot_service, "_send", lambda chat_id, text, reply_markup=None: sent.append((chat_id, text, reply_markup)) or {"ok": True})
    monkeypatch.setattr(user_bot_service, "logger", logger)

    monkeypatch.setattr(user_bot_lottery_draw_service, "_datetime_provider", lambda: user_bot_service.datetime)
    monkeypatch.setattr(user_bot_lottery_draw_service, "_random_provider", lambda: user_bot_service.random)
    monkeypatch.setattr(user_bot_lottery_draw_service, "_point_dao_provider", lambda: user_bot_service.point_dao)
    monkeypatch.setattr(user_bot_lottery_draw_service, "_media_api_provider", lambda: user_bot_service.media_api)
    monkeypatch.setattr(
        user_bot_lottery_draw_service,
        "_allowed_groups_provider",
        lambda: user_bot_service.get_user_bot_allowed_groups(),
    )
    monkeypatch.setattr(
        user_bot_lottery_draw_service,
        "_get_binding_by_emby_id_provider",
        lambda: user_bot_service._get_binding_by_emby_id,
    )
    monkeypatch.setattr(user_bot_lottery_draw_service, "_user_bot_dao_provider", lambda: user_bot_service.user_bot_dao)
    monkeypatch.setattr(user_bot_lottery_draw_service, "_send_provider", lambda: user_bot_service._send)
    monkeypatch.setattr(user_bot_lottery_draw_service, "_logger_provider", lambda: user_bot_service.logger)

    return user_bot_service, sent, point_dao, media_api, random_source, user_bot_dao, logger


def test_lottery_draw_preserves_success_save_and_group_notifications(monkeypatch):
    user_bot_service, sent, point_dao, media_api, random_source, user_bot_dao, logger = _reset_lottery_draw_state(monkeypatch)
    media_api.status_by_path["/Users/u3"] = 404

    result = user_bot_service.do_lottery_draw()

    assert result == {"status": "success", "winning_numbers": "1234", "total_pool": 1000}
    assert media_api.calls == [("/Users/u1", 3), ("/Users/u2", 3), ("/Users/u3", 3)]
    assert point_dao.saved == [
        (
            "2026-06-03",
            "1234",
            {
                1: [{"ticket_id": 1, "user_id": "u1", "username": "Alice", "prize_amount": 500}],
                2: [{"ticket_id": 2, "user_id": "u2", "username": "Bob", "prize_amount": 200}],
                3: [],
                4: [],
            },
            [{"ticket_id": 1, "user_id": "u1", "username": "Alice", "prize_amount": 50}],
            250,
        )
    ]
    assert random_source.sample_calls == [([("u1", (1, "Alice")), ("u2", (2, "Bob"))], 1)]
    assert user_bot_dao.calls == ["tg1", "tg1"]
    assert len(sent) == 2
    assert sent[0][0] == "-1001"
    assert sent[1][0] == "-1002"
    assert "🎲 中奖号码: <b>1234</b>" in sent[0][1]
    assert "<a href='tg://user?id=tg1'>AliceTG</a> - 一等奖 (+500积分)" in sent[0][1]
    assert "Bob - 二等奖 (+200积分)" in sent[0][1]
    assert "幸运奖 (+50积分)" in sent[0][1]
    assert logger.warnings == ["[彩票] 用户 u3(Deleted) 已被删除，跳过"]
    assert logger.errors == []


def test_lottery_draw_preserves_already_drawn_skip(monkeypatch):
    user_bot_service, sent, point_dao, media_api, _random_source, _user_bot_dao, logger = _reset_lottery_draw_state(monkeypatch)
    point_dao.draw_context = {
        "already_drawn": True,
        "winning_numbers": "9876",
        "total_pool": 1000,
        "tickets": [],
    }

    result = user_bot_service.do_lottery_draw()

    assert result is None
    assert point_dao.saved == []
    assert media_api.calls == []
    assert sent == []
    assert logger.infos == ["[彩票] 今天已开奖: 9876"]


def test_lottery_draw_preserves_ticket_when_media_check_raises(monkeypatch):
    user_bot_service, sent, point_dao, media_api, _random_source, _user_bot_dao, logger = _reset_lottery_draw_state(monkeypatch)
    point_dao.draw_context["tickets"] = [
        {"id": 1, "user_id": "u1", "username": "Alice", "numbers": "1234"},
    ]
    media_api.raise_paths.add("/Users/u1")
    monkeypatch.setattr(user_bot_service, "get_user_bot_allowed_groups", lambda: "")

    result = user_bot_service.do_lottery_draw()

    assert result == {"status": "success", "winning_numbers": "1234", "total_pool": 1000}
    assert media_api.calls == [("/Users/u1", 3)]
    assert point_dao.saved[0][2][1] == [{"ticket_id": 1, "user_id": "u1", "username": "Alice", "prize_amount": 500}]
    assert point_dao.saved[0][4] == 450
    assert sent == []
    assert logger.warnings == []
    assert logger.errors == []
