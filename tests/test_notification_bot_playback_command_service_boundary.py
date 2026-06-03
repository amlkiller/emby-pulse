import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.domains.notifications import bot_service


class FakeResponse:
    def __init__(self, payload=None):
        self._payload = payload if payload is not None else []

    def json(self):
        return self._payload


class FakeMediaApi:
    def __init__(self, sessions=None, error=None):
        self.sessions = sessions if sessions is not None else []
        self.error = error
        self.calls = []

    def get(self, path, timeout=None):
        self.calls.append((path, timeout))
        if self.error:
            raise self.error
        if path == "/Sessions":
            return FakeResponse(self.sessions)
        return FakeResponse([])


class FakePlaybackStore:
    def __init__(self, rows=None, error=None):
        self.rows = rows if rows is not None else []
        self.error = error
        self.queries = []

    def query(self, sql):
        self.queries.append(sql)
        if self.error:
            raise self.error
        return self.rows


def _capture_bot_messages():
    bot = bot_service.NotificationBot()
    sent = []
    bot.send_message = lambda chat_id, text, parse_mode="HTML", reply_markup=None, platform="all": sent.append(
        (chat_id, text, parse_mode, reply_markup, platform)
    )
    return bot, sent


def test_cmd_now_formats_active_playback_through_legacy_media_api(monkeypatch):
    sessions = [
        {
            "UserName": "Alice",
            "Client": "Infuse",
            "PlayState": {"PositionTicks": 5_000_000_000},
            "NowPlayingItem": {
                "Name": "Pilot",
                "Type": "Episode",
                "SeriesName": "Series One",
                "RunTimeTicks": 10_000_000_000,
            },
        },
        {
            "UserName": "Bob",
            "Client": "Web",
            "PlayState": {"PositionTicks": 12_000_000_000},
            "NowPlayingItem": {
                "Name": "Movie One",
                "Type": "Movie",
                "RunTimeTicks": 10_000_000_000,
            },
        },
    ]
    media = FakeMediaApi(sessions=sessions)
    monkeypatch.setattr(bot_service, "media_api", media)
    bot, sent = _capture_bot_messages()

    bot._cmd_now("chat-1", "tg")

    assert media.calls == [("/Sessions", 5)]
    assert sent == [
        (
            "chat-1",
            (
                "🟢 <b>当前正在播放 (2 人)</b>\n\n"
                "👤 <b>Alice</b> (Infuse)\n"
                "📺 《Series One》 Pilot\n"
                "⏳ <code>[█████⚪️⚪️⚪️⚪️⚪️] 50%</code>\n\n"
                "👤 <b>Bob</b> (Web)\n"
                "📺 《Movie One》\n"
                "⏳ <code>[██████████] 100%</code>"
            ),
            "HTML",
            None,
            "tg",
        )
    ]


def test_cmd_now_sends_empty_or_failure_fallbacks(monkeypatch):
    media = FakeMediaApi(sessions=[{"UserName": "Alice"}])
    monkeypatch.setattr(bot_service, "media_api", media)
    bot, sent = _capture_bot_messages()

    bot._cmd_now("chat-1", "wecom")

    assert media.calls == [("/Sessions", 5)]
    assert sent == [("chat-1", "🟢 当前无人在看", "HTML", None, "wecom")]

    failing_media = FakeMediaApi(error=RuntimeError("offline"))
    monkeypatch.setattr(bot_service, "media_api", failing_media)
    bot, sent = _capture_bot_messages()

    bot._cmd_now("chat-1", "tg")

    assert failing_media.calls == [("/Sessions", 5)]
    assert sent == [("chat-1", "❌ 连接失败", "HTML", None, "tg")]


def test_cmd_recent_formats_playback_history_and_uses_instance_username_helper(monkeypatch):
    rows = [
        {"UserId": "u1", "ItemName": "Series - Episode One", "DateCreated": "2026-06-03T12:34:56"},
        {"UserId": "u2", "ItemName": "Movie Two", "DateCreated": "2026-06-02T01:02:03"},
    ]
    store = FakePlaybackStore(rows=rows)
    monkeypatch.setattr(bot_service, "playback_store", store)
    bot, sent = _capture_bot_messages()
    username_calls = []
    bot._get_username = lambda user_id: username_calls.append(user_id) or {"u1": "Alice", "u2": "Bob"}[user_id]

    bot._cmd_recent("chat-1", "tg")

    assert store.queries == [
        "SELECT UserId, ItemName, DateCreated FROM PlaybackActivity ORDER BY DateCreated DESC LIMIT 10"
    ]
    assert username_calls == ["u1", "u2"]
    assert sent == [
        (
            "chat-1",
            (
                "📜 <b>最近播放记录 (Top 10)</b>\n\n"
                "▫️ <code>06-03 12:34</code> | 👤 <b>Alice</b> > Series Episode One\n"
                "▫️ <code>06-02 01:02</code> | 👤 <b>Bob</b> > Movie Two"
            ),
            "HTML",
            None,
            "tg",
        )
    ]


def test_cmd_recent_sends_empty_or_query_failure_fallbacks(monkeypatch):
    store = FakePlaybackStore(rows=[])
    monkeypatch.setattr(bot_service, "playback_store", store)
    bot, sent = _capture_bot_messages()

    bot._cmd_recent("chat-1", "tg")

    assert store.queries == [
        "SELECT UserId, ItemName, DateCreated FROM PlaybackActivity ORDER BY DateCreated DESC LIMIT 10"
    ]
    assert sent == [("chat-1", "📭 无记录", "HTML", None, "tg")]

    failing_store = FakePlaybackStore(error=RuntimeError("db error"))
    monkeypatch.setattr(bot_service, "playback_store", failing_store)
    bot, sent = _capture_bot_messages()

    bot._cmd_recent("chat-1", "wecom")

    assert failing_store.queries == [
        "SELECT UserId, ItemName, DateCreated FROM PlaybackActivity ORDER BY DateCreated DESC LIMIT 10"
    ]
    assert sent == [("chat-1", "❌ 查询失败", "HTML", None, "wecom")]
