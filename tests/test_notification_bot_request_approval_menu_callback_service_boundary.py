import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeMediaRequestDao:
    def __init__(self):
        self.summary_by_tmdb = {}
        self.summary_calls = []

    def get_request_summary_by_tmdb(self, tmdb_id):
        self.summary_calls.append(tmdb_id)
        return self.summary_by_tmdb.get(tmdb_id)


class FakeTelegramClient:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def post_api(self, token, method, **kwargs):
        self.calls.append((token, method, kwargs))
        if self.error:
            raise self.error


class FakePlugin:
    def __init__(self, enabled):
        self.enabled = enabled


def _patch_dependencies(monkeypatch, *, pulse_url="https://pulse.example", plugin=None, telegram_error=None):
    from app.domains.notifications import bot_service

    dao = FakeMediaRequestDao()
    telegram = FakeTelegramClient(error=telegram_error)
    plugin_calls = []

    def get_plugin(name):
        plugin_calls.append(name)
        if isinstance(plugin, Exception):
            raise plugin
        return plugin

    monkeypatch.setattr(bot_service, "media_request_dao", dao)
    monkeypatch.setattr(bot_service, "telegram_client", telegram)
    monkeypatch.setattr(bot_service, "get_pulse_url", lambda: pulse_url)
    monkeypatch.setattr(bot_service, "get_plugin", get_plugin)
    return dao, telegram, plugin_calls


def test_request_approval_menu_reject_menu_edits_legacy_keyboard(monkeypatch):
    from app.domains.notifications import bot_service

    dao, telegram, plugin_calls = _patch_dependencies(monkeypatch)

    handled = bot_service.notification_bot_request_approval_menu_callback_service.handle_request_approval_menu_callback(
        "req_reject_menu_123",
        "chat-1",
        7,
        "token",
        {"proxy": "ok"},
    )

    assert handled is True
    assert dao.summary_calls == []
    assert plugin_calls == []
    assert telegram.calls == [
        (
            "token",
            "editMessageReplyMarkup",
            {
                "json": {
                    "chat_id": "chat-1",
                    "message_id": 7,
                    "reply_markup": {
                        "inline_keyboard": [
                            [{"text": "影片未上映", "callback_data": "req_reject_do_123_0"}, {"text": "剧集未开播", "callback_data": "req_reject_do_123_1"}],
                            [{"text": "未找到可用资源", "callback_data": "req_reject_do_123_2"}, {"text": "质量太差等待洗版", "callback_data": "req_reject_do_123_3"}],
                            [{"text": "🔙 取消返回", "callback_data": "req_back_123"}],
                        ]
                    },
                },
                "proxies": {"proxy": "ok"},
                "timeout": 5,
            },
        )
    ]


def test_request_approval_menu_back_includes_hdhive_when_enabled_and_summary_exists(monkeypatch):
    from app.domains.notifications import bot_service

    dao, telegram, plugin_calls = _patch_dependencies(monkeypatch, plugin=FakePlugin(enabled=True))
    dao.summary_by_tmdb["456"] = {"title": "Movie Title_HD", "media_type": "movie"}

    handled = bot_service.notification_bot_request_approval_menu_callback_service.handle_request_approval_menu_callback(
        "req_back_456",
        "chat-2",
        8,
        "token",
        None,
    )

    assert handled is True
    assert plugin_calls == ["hdhive"]
    assert dao.summary_calls == ["456"]
    assert telegram.calls[0][2]["json"]["reply_markup"] == {
        "inline_keyboard": [
            [{"text": "🚀 推送 MP", "callback_data": "req_approve_456"}, {"text": "✋ 手动接单", "callback_data": "req_manual_456"}],
            [{"text": "🔍 影巢搜索", "callback_data": "req_hdhive_456_movie_0_Movie-Title-HD"}, {"text": "❌ 拒绝求片", "callback_data": "req_reject_menu_456"}],
            [{"text": "💻 网页审批", "url": "https://pulse.example/requests_admin"}],
        ]
    }


def test_request_approval_menu_back_uses_fallback_keyboard_without_hdhive(monkeypatch):
    from app.domains.notifications import bot_service

    dao, telegram, plugin_calls = _patch_dependencies(monkeypatch, pulse_url="", plugin=FakePlugin(enabled=False))
    dao.summary_by_tmdb["789"] = {"title": "Ignored", "media_type": "tv"}

    handled = bot_service.notification_bot_request_approval_menu_callback_service.handle_request_approval_menu_callback(
        "req_back_789",
        "chat-3",
        9,
        "token",
        {},
    )

    assert handled is True
    assert plugin_calls == ["hdhive"]
    assert dao.summary_calls == ["789"]
    assert telegram.calls[0][2]["json"]["reply_markup"] == {
        "inline_keyboard": [
            [{"text": "🚀 推送 MP", "callback_data": "req_approve_789"}, {"text": "✋ 手动接单", "callback_data": "req_manual_789"}],
            [{"text": "❌ 拒绝求片", "callback_data": "req_reject_menu_789"}, {"text": "💻 网页审批", "url": "http://127.0.0.1:10307/requests_admin"}],
        ]
    }


def test_request_approval_menu_non_menu_data_is_not_handled(monkeypatch):
    from app.domains.notifications import bot_service

    dao, telegram, plugin_calls = _patch_dependencies(monkeypatch)

    handled = bot_service.notification_bot_request_approval_menu_callback_service.handle_request_approval_menu_callback(
        "req_approve_123",
        "chat",
        1,
        "token",
        None,
    )

    assert handled is False
    assert dao.summary_calls == []
    assert plugin_calls == []
    assert telegram.calls == []


def test_request_approval_menu_swallows_telegram_edit_failures(monkeypatch):
    from app.domains.notifications import bot_service

    dao, telegram, plugin_calls = _patch_dependencies(monkeypatch, telegram_error=RuntimeError("telegram down"))

    handled = bot_service.notification_bot_request_approval_menu_callback_service.handle_request_approval_menu_callback(
        "req_reject_menu_123",
        "chat",
        1,
        "token",
        None,
    )

    assert handled is True
    assert dao.summary_calls == []
    assert plugin_calls == []
    assert len(telegram.calls) == 1
