import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeMediaRequestDao:
    def __init__(self):
        self.rows_by_tmdb = {}
        self.list_calls = []
        self.status_updates = []

    def list_pending_requests_by_tmdb(self, tmdb_id):
        self.list_calls.append(tmdb_id)
        return self.rows_by_tmdb.get(tmdb_id, [])

    def update_media_request_status(self, tmdb_id, season, status, reject_reason=None):
        self.status_updates.append((tmdb_id, season, status, reject_reason))


class FakeMoviePilotClient:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def subscribe(self, url, token, payload, timeout=None):
        self.calls.append((url, token, payload, timeout))
        if self.error:
            raise self.error


class FakeTelegramClient:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def post_api(self, token, method, **kwargs):
        self.calls.append((token, method, kwargs))
        if self.error:
            raise self.error


def _patch_dependencies(monkeypatch, *, mp_url="http://mp.local", mp_token="mp-token", moviepilot_error=None, telegram_error=None):
    from app.domains.notifications import bot_service

    dao = FakeMediaRequestDao()
    moviepilot = FakeMoviePilotClient(error=moviepilot_error)
    telegram = FakeTelegramClient(error=telegram_error)
    recorded = []
    synced = []

    monkeypatch.setattr(bot_service, "media_request_dao", dao)
    monkeypatch.setattr(bot_service, "moviepilot_client", moviepilot)
    monkeypatch.setattr(bot_service, "telegram_client", telegram)
    monkeypatch.setattr(bot_service, "get_moviepilot_url", lambda: mp_url)
    monkeypatch.setattr(bot_service, "get_moviepilot_token", lambda: mp_token)
    monkeypatch.setattr(bot_service, "_record_request_admin_message", lambda *args: recorded.append(args))
    monkeypatch.setattr(bot_service, "_sync_request_admin_messages", lambda *args: synced.append(args))
    return dao, moviepilot, telegram, recorded, synced


def test_request_approval_action_approve_subscribes_and_updates_rows(monkeypatch):
    from app.domains.notifications import bot_service

    dao, moviepilot, telegram, recorded, synced = _patch_dependencies(monkeypatch)
    dao.rows_by_tmdb["123"] = [
        {"title": "Movie A", "year": 2025, "media_type": "movie", "season": None},
        {"title": "Show B", "year": 2024, "media_type": "tv", "season": 2},
    ]
    cq = {"message": {"text": "求片请求"}, "from": {"first_name": "Alice"}}

    handled = bot_service.notification_bot_request_approval_action_callback_service.handle_request_approval_action_callback(
        "req_approve_123",
        cq,
        "chat-1",
        7,
        "token",
        {"proxy": "ok"},
    )

    assert handled is True
    assert dao.list_calls == ["123"]
    assert moviepilot.calls == [
        ("http://mp.local", "mp-token", {"name": "Movie A", "tmdbid": 123, "year": "2025", "type": "电影"}, 10),
        ("http://mp.local", "mp-token", {"name": "Show B", "tmdbid": 123, "year": "2024", "type": "电视剧", "season": 2}, 10),
    ]
    assert dao.status_updates == [("123", None, 1, None), ("123", 2, 1, None)]
    assert telegram.calls == []
    assert recorded == [("123", "chat-1", 7, False, "求片请求")]
    assert synced == [("123", "✅ 已审批：推送 MP 自动下载", "Alice", "token", {"proxy": "ok"}, "求片请求", False)]


def test_request_approval_action_manual_updates_without_moviepilot(monkeypatch):
    from app.domains.notifications import bot_service

    dao, moviepilot, _telegram, recorded, synced = _patch_dependencies(monkeypatch)
    dao.rows_by_tmdb["456"] = [{"title": "Movie", "year": 2025, "media_type": "movie", "season": 1}]

    handled = bot_service.notification_bot_request_approval_action_callback_service.handle_request_approval_action_callback(
        "req_manual_456",
        {"message": {"text": "求片请求"}, "from": {"first_name": "Bob"}},
        "chat-2",
        8,
        "token",
        None,
    )

    assert handled is True
    assert moviepilot.calls == []
    assert dao.status_updates == [("456", 1, 4, None)]
    assert recorded == [("456", "chat-2", 8, False, "求片请求")]
    assert synced == [("456", "✅ 已审批：管理员手动接单", "Bob", "token", None, "求片请求", False)]


def test_request_approval_action_reject_maps_reason_and_syncs_caption(monkeypatch):
    from app.domains.notifications import bot_service

    dao, moviepilot, _telegram, recorded, synced = _patch_dependencies(monkeypatch)
    dao.rows_by_tmdb["789"] = [{"title": "Movie", "year": 2025, "media_type": "movie", "season": 3}]

    handled = bot_service.notification_bot_request_approval_action_callback_service.handle_request_approval_action_callback(
        "req_reject_do_789_2",
        {"message": {"caption": "带图求片"}, "from": {}},
        "chat-3",
        9,
        "token",
        {},
    )

    assert handled is True
    assert moviepilot.calls == []
    assert dao.status_updates == [("789", 3, 3, "未找到可用资源")]
    assert recorded == [("789", "chat-3", 9, True, "带图求片")]
    assert synced == [("789", "❌ 已拒绝 (未找到可用资源)", "Admin", "token", {}, "带图求片", True)]


def test_request_approval_action_empty_rows_clears_reply_markup(monkeypatch):
    from app.domains.notifications import bot_service

    dao, moviepilot, telegram, recorded, synced = _patch_dependencies(monkeypatch)

    handled = bot_service.notification_bot_request_approval_action_callback_service.handle_request_approval_action_callback(
        "req_approve_321",
        {"message": {"text": "求片请求"}},
        "chat-4",
        10,
        "token",
        None,
    )

    assert handled is True
    assert dao.list_calls == ["321"]
    assert dao.status_updates == []
    assert moviepilot.calls == []
    assert telegram.calls == [
        (
            "token",
            "editMessageReplyMarkup",
            {
                "json": {"chat_id": "chat-4", "message_id": 10, "reply_markup": {"inline_keyboard": []}},
                "proxies": None,
                "timeout": 5,
            },
        )
    ]
    assert recorded == []
    assert synced == []


def test_request_approval_action_non_action_data_is_not_handled(monkeypatch):
    from app.domains.notifications import bot_service

    dao, moviepilot, telegram, recorded, synced = _patch_dependencies(monkeypatch)

    handled = bot_service.notification_bot_request_approval_action_callback_service.handle_request_approval_action_callback(
        "req_reject_menu_123",
        {"message": {"text": "求片请求"}},
        "chat",
        1,
        "token",
        None,
    )

    assert handled is False
    assert dao.list_calls == []
    assert moviepilot.calls == []
    assert telegram.calls == []
    assert recorded == []
    assert synced == []


def test_request_approval_action_swallows_subscribe_and_clear_failures(monkeypatch):
    from app.domains.notifications import bot_service

    dao, moviepilot, telegram, _recorded, _synced = _patch_dependencies(
        monkeypatch,
        moviepilot_error=RuntimeError("mp down"),
        telegram_error=RuntimeError("telegram down"),
    )
    dao.rows_by_tmdb["654"] = [{"title": "Movie", "year": 2025, "media_type": "movie", "season": None}]

    handled = bot_service.notification_bot_request_approval_action_callback_service.handle_request_approval_action_callback(
        "req_approve_654",
        {"message": {"text": "求片请求"}, "from": {"first_name": "Root"}},
        "chat",
        1,
        "token",
        None,
    )

    assert handled is True
    assert len(moviepilot.calls) == 1
    assert dao.status_updates == [("654", None, 1, None)]

    dao.rows_by_tmdb["999"] = []
    handled = bot_service.notification_bot_request_approval_action_callback_service.handle_request_approval_action_callback(
        "req_manual_999",
        {"message": {"text": "求片请求"}},
        "chat",
        2,
        "token",
        None,
    )

    assert handled is True
    assert len(telegram.calls) == 1
