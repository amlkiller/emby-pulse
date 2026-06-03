import sys
import types
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeLogger:
    def __init__(self):
        self.errors = []

    def error(self, message):
        self.errors.append(message)


class FakeTelegramClient:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def post_api(self, token, method, **kwargs):
        self.calls.append((token, method, kwargs))
        if self.error:
            raise self.error


def _install_module(monkeypatch, module_name, **attrs):
    module = types.ModuleType(module_name)
    for name, value in attrs.items():
        setattr(module, name, value)
    package_name = module_name.rsplit(".", 1)[0]
    package = types.ModuleType(package_name)
    package.__path__ = []
    setattr(package, module_name.rsplit(".", 1)[1], module)
    monkeypatch.setitem(sys.modules, package_name, package)
    monkeypatch.setitem(sys.modules, module_name, module)
    return module


def _patch_dependencies(monkeypatch, *, telegram_error=None):
    from app.bot.notification_bot import bot_service

    logger = FakeLogger()
    telegram = FakeTelegramClient(error=telegram_error)
    monkeypatch.setattr(bot_service, "logger", logger)
    monkeypatch.setattr(bot_service, "telegram_client", telegram)
    return logger, telegram


def test_request_hdhive_search_non_matching_data_is_not_handled(monkeypatch):
    from app.bot.notification_bot import bot_service

    logger, telegram = _patch_dependencies(monkeypatch)

    handled = bot_service.notification_bot_request_hdhive_search_callback_service.handle_request_hdhive_search_callback(
        "req_approve_123",
        "chat",
        "cq",
        7,
        "token",
        None,
    )

    assert handled is False
    assert logger.errors == []
    assert telegram.calls == []


def test_request_hdhive_search_delegates_to_plugin(monkeypatch):
    from app.bot.notification_bot import bot_service

    logger, telegram = _patch_dependencies(monkeypatch)
    calls = []
    _install_module(
        monkeypatch,
        "app.plugins.hdhive.plugin",
        handle_request_hdhive_search=lambda data, cid, cq_id, platform: calls.append((data, cid, cq_id, platform)),
    )

    handled = bot_service.notification_bot_request_hdhive_search_callback_service.handle_request_hdhive_search_callback(
        "req_hdhive_123_movie_0_Title",
        "chat",
        "cq",
        7,
        "token",
        {"proxy": "ok"},
    )

    assert handled is True
    assert calls == [("req_hdhive_123_movie_0_Title", "chat", "cq", "tg")]
    assert logger.errors == []
    assert telegram.calls == []


def test_request_hdhive_search_plugin_failure_logs_and_clears_reply_markup(monkeypatch):
    from app.bot.notification_bot import bot_service

    logger, telegram = _patch_dependencies(monkeypatch)

    def raise_search(*_args):
        raise RuntimeError("search down")

    _install_module(monkeypatch, "app.plugins.hdhive.plugin", handle_request_hdhive_search=raise_search)

    handled = bot_service.notification_bot_request_hdhive_search_callback_service.handle_request_hdhive_search_callback(
        "req_hdhive_456_tv_0_Title",
        "chat-1",
        "cq-1",
        8,
        "token",
        {"proxy": "ok"},
    )

    assert handled is True
    assert logger.errors == ["[Bot] 影巢搜索回调处理失败: search down"]
    assert telegram.calls == [
        (
            "token",
            "editMessageReplyMarkup",
            {
                "json": {"chat_id": "chat-1", "message_id": 8, "reply_markup": {"inline_keyboard": []}},
                "proxies": {"proxy": "ok"},
                "timeout": 5,
            },
        )
    ]


def test_request_hdhive_search_swallows_reply_markup_cleanup_failure(monkeypatch):
    from app.bot.notification_bot import bot_service

    logger, telegram = _patch_dependencies(monkeypatch, telegram_error=RuntimeError("telegram down"))

    def raise_search(*_args):
        raise RuntimeError("search down")

    _install_module(monkeypatch, "app.plugins.hdhive.plugin", handle_request_hdhive_search=raise_search)

    handled = bot_service.notification_bot_request_hdhive_search_callback_service.handle_request_hdhive_search_callback(
        "req_hdhive_789_movie_0_Title",
        "chat-2",
        "cq-2",
        9,
        "token",
        None,
    )

    assert handled is True
    assert logger.errors == ["[Bot] 影巢搜索回调处理失败: search down"]
    assert len(telegram.calls) == 1
