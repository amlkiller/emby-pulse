import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.bot.notification_bot import bot_service


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else []

    def json(self):
        return self._payload


class FakeMediaApi:
    def __init__(self, response=None, error=None):
        self.response = response or FakeResponse()
        self.error = error
        self.calls = []

    def get(self, path, params=None, timeout=None):
        self.calls.append((path, params, timeout))
        if self.error:
            raise self.error
        return self.response


class FakeLogger:
    def __init__(self):
        self.errors = []

    def error(self, message):
        self.errors.append(message)


def _capture_bot_messages():
    bot = bot_service.NotificationBot()
    sent = []
    bot.send_message = lambda chat_id, text, parse_mode="HTML", reply_markup=None, platform="all": sent.append(
        (chat_id, text, parse_mode, reply_markup, platform)
    )
    return bot, sent


def _expected_latest_params():
    return {
        "IncludeItemTypes": "Movie,Episode",
        "Limit": 8,
        "Fields": "DateCreated,Name,SeriesName,Type,ParentIndexNumber,IndexNumber",
    }


def test_latest_command_missing_admin_id_uses_legacy_admin_provider(monkeypatch):
    media = FakeMediaApi()
    monkeypatch.setattr(bot_service, "media_api", media)
    monkeypatch.setattr(bot_service, "get_admin_id", lambda: None)
    bot, sent = _capture_bot_messages()

    bot._cmd_latest("chat-1", "tg")

    assert media.calls == []
    assert sent == [("chat-1", "❌ 错误: 无法获取 Emby 用户身份", "HTML", None, "tg")]


def test_latest_command_non_200_response_sends_query_failure(monkeypatch):
    media = FakeMediaApi(response=FakeResponse(status_code=500))
    monkeypatch.setattr(bot_service, "media_api", media)
    monkeypatch.setattr(bot_service, "get_admin_id", lambda: "admin-1")
    bot, sent = _capture_bot_messages()

    bot._cmd_latest("chat-1", "wecom")

    assert media.calls == [("/Users/admin-1/Items/Latest", _expected_latest_params(), 10)]
    assert sent == [("chat-1", "❌ 查询失败", "HTML", None, "wecom")]


def test_latest_command_empty_items_sends_empty_message(monkeypatch):
    media = FakeMediaApi(response=FakeResponse(payload=[]))
    monkeypatch.setattr(bot_service, "media_api", media)
    monkeypatch.setattr(bot_service, "get_admin_id", lambda: "admin-1")
    bot, sent = _capture_bot_messages()

    bot._cmd_latest("chat-1", "tg")

    assert media.calls == [("/Users/admin-1/Items/Latest", _expected_latest_params(), 10)]
    assert sent == [("chat-1", "📭 最近没有新入库的资源", "HTML", None, "tg")]


def test_latest_command_formats_movie_episode_and_unknown_dates(monkeypatch):
    media = FakeMediaApi(
        response=FakeResponse(
            payload=[
                {
                    "Name": "Movie One",
                    "Type": "Movie",
                    "DateCreated": "2026-06-03T12:34:56",
                },
                {
                    "Name": "Pilot",
                    "Type": "Episode",
                    "SeriesName": "Series One",
                    "ParentIndexNumber": 2,
                    "IndexNumber": 7,
                    "DateCreated": "2026-06-02T01:02:03",
                },
                {
                    "Name": "Special",
                    "Type": "Episode",
                    "SeriesName": "Series Two",
                    "ParentIndexNumber": None,
                    "IndexNumber": None,
                },
            ]
        )
    )
    monkeypatch.setattr(bot_service, "media_api", media)
    monkeypatch.setattr(bot_service, "get_admin_id", lambda: "admin-1")
    bot, sent = _capture_bot_messages()

    bot._cmd_latest("chat-1", "tg")

    assert media.calls == [("/Users/admin-1/Items/Latest", _expected_latest_params(), 10)]
    assert sent == [
        (
            "chat-1",
            (
                "🆕 <b>最近入库 (Top 8)</b>\n\n"
                "🎬 <code>2026-06-03</code> | <b>《Movie One》</b>\n"
                "📺 <code>2026-06-02</code> | <b>《Series One》 S02E07 Pilot</b>\n"
                "📺 <code>未知时间</code> | <b>《Series Two》 S01EXX Special</b>"
            ),
            "HTML",
            None,
            "tg",
        )
    ]


def test_latest_command_exception_logs_and_sends_failure(monkeypatch):
    media = FakeMediaApi(error=RuntimeError("media failed"))
    logger = FakeLogger()
    monkeypatch.setattr(bot_service, "media_api", media)
    monkeypatch.setattr(bot_service, "get_admin_id", lambda: "admin-1")
    monkeypatch.setattr(bot_service, "logger", logger)
    bot, sent = _capture_bot_messages()

    bot._cmd_latest("chat-1", "tg")

    assert media.calls == [("/Users/admin-1/Items/Latest", _expected_latest_params(), 10)]
    assert logger.errors == ["[Bot] latest query error: media failed"]
    assert sent == [("chat-1", "❌ 查询异常", "HTML", None, "tg")]
