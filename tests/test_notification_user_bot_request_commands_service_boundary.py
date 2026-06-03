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


class FakeTmdbClient:
    def __init__(self):
        self.api_key = "tmdb-key"
        self.search_payload = {
            "results": [
                {"media_type": "movie", "id": 100, "title": "Movie A", "release_date": "2025-01-02"},
                {"media_type": "tv", "id": 200, "name": "Show B", "first_air_date": "2024-03-04"},
                {"media_type": "person", "id": 300, "name": "Actor"},
            ]
        }
        self.movie_detail = {
            "title": "Movie A",
            "release_date": "2025-01-02",
            "poster_path": "/poster.jpg",
        }
        self.tv_detail = {
            "name": "Show B",
            "first_air_date": "2024-03-04",
            "poster_path": "",
            "seasons": [{"season_number": 0}, {"season_number": 1}, {"season_number": 2}],
        }
        self.calls = []

    def search_multi(self, query, proxies=None, timeout=None, page=None):
        self.calls.append(("search_multi", query, proxies, timeout, page))
        return FakeResponse(self.search_payload)

    def get_tv_details(self, tmdb_id, proxies=None, timeout=None):
        self.calls.append(("get_tv_details", tmdb_id, proxies, timeout))
        return FakeResponse(self.tv_detail)

    def get_movie_details(self, tmdb_id, proxies=None, timeout=None):
        self.calls.append(("get_movie_details", tmdb_id, proxies, timeout))
        return FakeResponse(self.movie_detail)


class FakeMediaRequestDao:
    def __init__(self):
        self.submit_result = {
            "ok": True,
            "need_cost": True,
            "request_cost": 20,
            "user_req_free": 0,
            "user_req_free_count": -1,
        }
        self.recent_rows = [
            {"media_type": "movie", "title": "Movie A", "year": "2025", "season": 0, "status": 0},
            {"media_type": "tv", "title": "Show B", "year": "2024", "season": 2, "status": 2},
        ]
        self.submit_calls = []
        self.recent_calls = []

    def submit_single_media_request(self, user_id, user_name, tmdb_id, media_type, title, year, poster, season):
        self.submit_calls.append((user_id, user_name, tmdb_id, media_type, title, year, poster, season))
        return self.submit_result

    def list_user_recent_requests(self, user_id):
        self.recent_calls.append(user_id)
        return self.recent_rows


class FakeLogger:
    def __init__(self):
        self.errors = []

    def error(self, message):
        self.errors.append(message)


def _reset_request_state(monkeypatch):
    from app.bot.user_bot import user_bot_request_commands_service
    from tests.user_bot_worker_boundary import user_bot_worker_boundary as user_bot_service

    sent = []
    replies = []
    tg_calls = []
    unbound = []
    notifications = []
    tmdb = FakeTmdbClient()
    request_dao = FakeMediaRequestDao()
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
    monkeypatch.setattr(user_bot_service, "tmdb_client", tmdb)
    monkeypatch.setattr(user_bot_service, "get_safe_proxies", lambda: {"https": "proxy"})
    monkeypatch.setattr(user_bot_service, "media_request_dao", request_dao)
    monkeypatch.setattr(user_bot_service, "get_user_bot_portal_url", lambda: "https://portal.example")
    monkeypatch.setattr(user_bot_service, "get_media_server_main_public_url", lambda: "https://emby.example")
    monkeypatch.setattr(user_bot_service, "safe_error_message", lambda _err, fallback: f"masked:{fallback}")
    monkeypatch.setattr(user_bot_service, "logger", logger)
    monkeypatch.setattr(
        user_bot_request_commands_service,
        "_request_notification_sender_provider",
        lambda: (
            lambda uname, title, year, season_str, tmdb_id, poster_path: notifications.append(
                (uname, title, year, season_str, tmdb_id, poster_path)
            )
        ),
    )

    return user_bot_service, sent, replies, tg_calls, unbound, notifications, tmdb, request_dao, logger


def test_cmd_request_preserves_tmdb_unavailable_and_search_rendering(monkeypatch):
    user_bot_service, sent, _replies, _tg_calls, _unbound, _notifications, tmdb, _dao, _logger = _reset_request_state(monkeypatch)

    tmdb.api_key = ""
    user_bot_service.cmd_request(10, "tg1", "matrix")
    assert sent == [(10, "❌ 服务器未配置 TMDB，求片功能不可用", None)]

    sent.clear()
    tmdb.api_key = "tmdb-key"
    user_bot_service.cmd_request(10, "tg1", "matrix")

    assert tmdb.calls == [("search_multi", "matrix", {"https": "proxy"}, 10, 1)]
    assert sent == [(
        10,
        "🔍 <b>搜索结果：matrix</b>\n\n🎬 Movie A (2025)\n📺 Show B (2024)\n\n点击下方按钮提交求片：",
        {
            "inline_keyboard": [
                [{"text": "🎬 Movie A (2025)", "callback_data": "ub_req_movie_100"}],
                [{"text": "📺 Show B (2024)", "callback_data": "ub_req_tv_200"}],
                [{"text": "🔙 主菜单", "callback_data": "ub_back_menu"}],
            ]
        },
    )]


def test_cmd_request_callback_preserves_tv_season_selection_and_legacy_submit_provider(monkeypatch):
    user_bot_service, sent, _replies, tg_calls, _unbound, _notifications, tmdb, _dao, _logger = _reset_request_state(monkeypatch)
    submitted = []

    user_bot_service.cmd_request_callback(10, "tg1", "tv", "200", "cq1")

    assert tg_calls == [("answerCallbackQuery", {"callback_query_id": "cq1"})]
    assert sent == [(
        10,
        "📺 <b>Show B</b>\n\n请选择要求片的季数：",
        {
            "inline_keyboard": [
                [
                    {"text": "第 1 季", "callback_data": "ub_reqsn_200_1"},
                    {"text": "第 2 季", "callback_data": "ub_reqsn_200_2"},
                ],
                [{"text": "🔙 返回", "callback_data": "ub_back_menu"}],
            ]
        },
    )]

    sent.clear()
    tg_calls.clear()
    tmdb.tv_detail["seasons"] = [{"season_number": 1}]
    monkeypatch.setattr(
        user_bot_service,
        "_submit_request",
        lambda chat_id, tg_user_id, media_type, tmdb_id, season: submitted.append(
            (chat_id, tg_user_id, media_type, tmdb_id, season)
        ),
    )
    user_bot_service.cmd_request_callback(10, "tg1", "tv", "200", "cq2")
    assert tg_calls == [("answerCallbackQuery", {"callback_query_id": "cq2"})]
    assert submitted == [(10, "tg1", "tv", "200", 1)]


def test_submit_request_preserves_success_message_cost_and_notification(monkeypatch):
    user_bot_service, sent, _replies, _tg_calls, _unbound, notifications, tmdb, request_dao, _logger = _reset_request_state(monkeypatch)

    user_bot_service._submit_request(10, "tg1", "movie", "100", 0)

    assert tmdb.calls == [("get_movie_details", "100", {"https": "proxy"}, 10)]
    assert request_dao.submit_calls == [(
        "u1",
        "Alice",
        100,
        "movie",
        "Movie A",
        "2025",
        "https://image.tmdb.org/t/p/w500/poster.jpg",
        0,
    )]
    assert sent == [(
        10,
        "✅ <b>求片已提交！</b>\n\n🎬 Movie A (2025)\n💰 消耗 20 积分\n📋 状态：等待管理员审批",
        {"inline_keyboard": [[{"text": "📋 我的求片", "callback_data": "ub_menu_myrequests"}, {"text": "🔙 主菜单", "callback_data": "ub_back_menu"}]]},
    )]
    assert notifications == [("Alice", "Movie A", "2025", "", "100", "/poster.jpg")]


def test_submit_request_preserves_dao_failure(monkeypatch):
    user_bot_service, sent, _replies, _tg_calls, _unbound, notifications, _tmdb, request_dao, _logger = _reset_request_state(monkeypatch)
    request_dao.submit_result = {"ok": False, "message": "今日次数已用完"}

    user_bot_service._submit_request(10, "tg1", "movie", "100", 0)

    assert sent == [(10, "❌ 今日次数已用完", None)]
    assert notifications == []


def test_cmd_myrequests_preserves_history_rendering_and_empty_state(monkeypatch):
    user_bot_service, _sent, replies, _tg_calls, _unbound, _notifications, _tmdb, request_dao, _logger = _reset_request_state(monkeypatch)

    user_bot_service.cmd_myrequests(10, "tg1", msg_id=5)

    assert request_dao.recent_calls == ["u1"]
    assert replies == [(
        10,
        "📋 <b>我的求片</b>\n\n"
        "🎬 <b>Movie A</b> (2025)\n   ⏳ 待审批\n\n"
        "📺 <b>Show B</b> (2024) 第2季\n   ✅ 已完成",
        {"inline_keyboard": [[{"text": "🎬 继续求片", "callback_data": "ub_menu_request"}, {"text": "🔙 主菜单", "callback_data": "ub_back_menu"}]]},
        5,
    )]

    replies.clear()
    request_dao.recent_rows = []
    user_bot_service.cmd_myrequests(10, "tg1", msg_id=6)
    assert replies == [(
        10,
        "📋 <b>我的求片</b>\n\n暂无求片记录",
        {"inline_keyboard": [[{"text": "🎬 去求片", "callback_data": "ub_menu_request"}, {"text": "🔙 主菜单", "callback_data": "ub_back_menu"}]]},
        6,
    )]
