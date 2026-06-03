import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import app.plugins as app_plugins
from app.domains.notifications import bot_service


class FakePlaybackStore:
    def __init__(self, responses=None, error=None):
        self.responses = list(responses or [])
        self.error = error
        self.calls = []

    def query(self, sql, params=None):
        self.calls.append((sql, params))
        if self.error:
            raise self.error
        if not self.responses:
            raise AssertionError(f"Unexpected query: {sql}")
        return self.responses.pop(0)


class FakeReportGen:
    def __init__(self, poster=None):
        self.poster = poster
        self.calls = []

    def generate_daily_poster(self, period, tv_list, movie_list):
        self.calls.append((period, tv_list, movie_list))
        return self.poster


class FakeLogger:
    def __init__(self):
        self.errors = []

    def error(self, message):
        self.errors.append(message)


def _capture_bot():
    bot = bot_service.NotificationBot()
    sent_messages = []
    sent_photos = []
    username_calls = []

    bot.send_message = lambda chat_id, text, parse_mode="HTML", reply_markup=None, platform="all": sent_messages.append(
        (chat_id, text, parse_mode, reply_markup, platform)
    )
    bot.send_photo = lambda chat_id, photo, caption="", parse_mode="HTML", reply_markup=None, platform="all", wecom_photo_io=None: sent_photos.append(
        (chat_id, photo, caption, parse_mode, reply_markup, platform, wecom_photo_io)
    )

    def fake_username(user_id):
        username_calls.append(user_id)
        return {"u1": "Alice", "u2": "Bob"}.get(user_id, user_id)

    bot._get_username = fake_username
    return bot, sent_messages, sent_photos, username_calls


def _patch_stats_dependencies(
    monkeypatch,
    *,
    store,
    report_gen=None,
    has_pil=False,
    plugin_config=None,
    base_filter=None,
    cover_url="cover-url",
    logger=None,
):
    monkeypatch.setattr(bot_service, "get_base_filter", base_filter or (lambda user_id: ("WHERE 1=1", [])))
    monkeypatch.setattr(bot_service, "playback_store", store)
    monkeypatch.setattr(bot_service, "report_gen", report_gen or FakeReportGen())
    monkeypatch.setattr(bot_service, "HAS_PIL", has_pil)
    monkeypatch.setattr(bot_service, "REPORT_COVER_URL", cover_url)
    monkeypatch.setattr(bot_service, "logger", logger or FakeLogger())
    monkeypatch.setattr(app_plugins, "get_plugin_config", lambda plugin_id: plugin_config)


def test_stats_command_fallback_text_report_groups_content_and_uses_legacy_dependencies(monkeypatch):
    store = FakePlaybackStore(
        responses=[
            [{"c": 3}],
            [{"c": 5400}],
            [{"c": 2}],
            [{"UserId": "u1", "t": 3600}],
            [
                {"ItemName": "Series One - S01E01", "ItemId": "ep1", "ItemType": "Episode", "C": 2, "Duration": 1800},
                {"ItemName": "Movie One", "ItemId": "m1", "ItemType": "Movie", "C": 1, "Duration": 3600},
            ],
        ]
    )
    _patch_stats_dependencies(monkeypatch, store=store, has_pil=False)
    bot, sent_messages, sent_photos, username_calls = _capture_bot()

    bot._cmd_stats("chat-1", "day", "tg")

    assert len(store.calls) == 5
    assert store.calls[0][0].startswith("SELECT COUNT(*) as c FROM PlaybackActivity WHERE 1=1 AND DateCreated >=")
    assert store.calls[0][1] == []
    assert username_calls == ["u1"]
    assert sent_messages == []
    assert len(sent_photos) == 1
    assert sent_photos[0][0] == "chat-1"
    assert sent_photos[0][1] == "cover-url"
    assert sent_photos[0][3:] == ("HTML", None, "tg", None)
    caption = sent_photos[0][2]
    assert caption.startswith("📊 <b>EmbyPulse 今日日报\n📅 ")
    assert "📈 <b>数据大盘</b>" in caption
    assert "▶️ 总播放量：3 次" in caption
    assert "⏱️ 活跃时长：1.5 小时" in caption
    assert "👥 活跃人数：2 人" in caption
    assert "🥇 Alice (1.0h)" in caption
    assert "Series One\n播放次数: 2 时长: 30 分钟" in caption
    assert "Movie One\n播放次数: 1 时长: 1 小时 0 分钟" not in caption


def test_stats_command_poster_mode_sends_generated_poster(monkeypatch):
    store = FakePlaybackStore(
        responses=[
            [{"c": 4}],
            [{"c": 7200}],
            [{"c": 1}],
            [{"UserId": "u1", "t": 7200}],
            [{"ItemName": "Movie One", "ItemId": "m1", "ItemType": "Movie", "C": 4, "Duration": 7200}],
        ]
    )
    report_gen = FakeReportGen(poster="poster-bytes")
    _patch_stats_dependencies(monkeypatch, store=store, report_gen=report_gen, has_pil=True)
    bot, sent_messages, sent_photos, username_calls = _capture_bot()

    bot._cmd_stats("chat-1", "week", "wecom")

    assert username_calls == ["u1"]
    assert report_gen.calls == [
        (
            "week",
            [],
            [{"ItemName": "Movie One", "ItemId": "m1", "C": 4, "Duration": 7200}],
        )
    ]
    assert sent_messages == []
    assert len(sent_photos) == 1
    assert sent_photos[0][0] == "chat-1"
    assert sent_photos[0][1] == "poster-bytes"
    assert sent_photos[0][5] == "wecom"
    assert "📊 日均播放：" in sent_photos[0][2]
    assert "🎬 <b>电影排名</b>" in sent_photos[0][2]


def test_stats_command_plugin_exclude_types_extend_query_params(monkeypatch):
    store = FakePlaybackStore(
        responses=[
            [{"c": 1}],
            [{"c": 60}],
            [{"c": 1}],
            [],
            [],
        ]
    )
    _patch_stats_dependencies(
        monkeypatch,
        store=store,
        has_pil=False,
        plugin_config={"exclude_types": "Trailer, Episode ", "top_content_limit": "2"},
        base_filter=lambda user_id: ("WHERE 1=1", ["hidden-user"]),
    )
    bot, sent_messages, sent_photos, username_calls = _capture_bot()

    bot._cmd_stats("chat-1", "month", "tg")

    assert username_calls == []
    assert sent_messages == []
    assert len(sent_photos) == 1
    for sql, params in store.calls:
        assert "AND ItemType NOT IN (?, ?)" in sql
        assert params == ("hidden-user", "Trailer", "Episode")
    assert "📊 日均播放：" not in sent_photos[0][2]
    assert "暂无数据" in sent_photos[0][2]


def test_stats_command_no_user_or_content_data_uses_empty_labels(monkeypatch):
    store = FakePlaybackStore(
        responses=[
            [{"c": 0}],
            [{"c": None}],
            [],
            [],
            [],
        ]
    )
    _patch_stats_dependencies(monkeypatch, store=store, has_pil=False)
    bot, sent_messages, sent_photos, username_calls = _capture_bot()

    bot._cmd_stats("chat-1", "year", "tg")

    assert username_calls == []
    assert sent_messages == []
    assert len(sent_photos) == 1
    assert "▶️ 总播放量：0 次" in sent_photos[0][2]
    assert "⏱️ 活跃时长：0.0 小时" in sent_photos[0][2]
    assert "👥 活跃人数：0 人" in sent_photos[0][2]
    assert "🏆 <b>活跃用户 Top 5</b>\n暂无数据" in sent_photos[0][2]
    assert "🔥 <b>热门内容 Top 10</b>\n暂无数据" in sent_photos[0][2]


def test_stats_command_logs_and_sends_failure_on_db_error(monkeypatch):
    logger = FakeLogger()
    store = FakePlaybackStore(error=RuntimeError("db failed"))
    _patch_stats_dependencies(monkeypatch, store=store, has_pil=False, logger=logger)
    bot, sent_messages, sent_photos, username_calls = _capture_bot()

    bot._cmd_stats("chat-1", "day", "tg")

    assert username_calls == []
    assert sent_photos == []
    assert logger.errors == ["[Bot] _cmd_stats error: db failed"]
    assert sent_messages == [("chat-1", "❌ 统计失败: db failed", "HTML", None, "tg")]
