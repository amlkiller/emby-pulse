import sys
import types
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeLogger:
    def __init__(self):
        self.infos = []
        self.errors = []

    def info(self, message):
        self.infos.append(message)

    def error(self, message):
        self.errors.append(message)


def _patch_logger(monkeypatch):
    from app.domains.notifications import bot_service

    logger = FakeLogger()
    monkeypatch.setattr(bot_service, "logger", logger)
    return logger


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


def _cq(message_id=77):
    return {"message": {"message_id": message_id}}


def test_plugin_callback_dispatches_cloud115_transfer_and_offline(monkeypatch):
    from app.domains.notifications import bot_service

    logger = _patch_logger(monkeypatch)
    calls = []
    _install_module(
        monkeypatch,
        "app.plugins.cloud115.plugin",
        handle_115_callback=lambda data, cid, cq_id, platform: calls.append(("tf", data, cid, cq_id, platform)) or True,
        handle_115_offline_callback=lambda data, cid, cq_id, platform: calls.append(("ol", data, cid, cq_id, platform)) or True,
    )

    assert bot_service.notification_bot_plugin_callback_service.handle_plugin_callback("p115_tf_1", "chat", "cq", _cq()) is True
    assert bot_service.notification_bot_plugin_callback_service.handle_plugin_callback("p115_ol_2", "chat", "cq", _cq()) is True
    assert calls == [("tf", "p115_tf_1", "chat", "cq", "tg"), ("ol", "p115_ol_2", "chat", "cq", "tg")]
    assert logger.errors == []


def test_plugin_callback_dispatches_hdhive_search_tmdb_and_page(monkeypatch):
    from app.domains.notifications import bot_service

    _patch_logger(monkeypatch)
    calls = []
    _install_module(
        monkeypatch,
        "app.plugins.hdhive.plugin",
        handle_hdhive_search_callback=lambda data, cid, cq_id, platform: calls.append(("search", data, cid, cq_id, platform)) or True,
        handle_hdhive_tmdb_callback=lambda data, cid, cq_id, platform: calls.append(("tmdb", data, cid, cq_id, platform)) or True,
        handle_hdhive_tmdbpage_callback=lambda data, cid, cq_id, platform, message_id: calls.append(
            ("tmdbpage", data, cid, cq_id, platform, message_id)
        )
        or True,
        handle_hdhive_page_callback=lambda data, cid, cq_id, platform, message_id: calls.append(
            ("page", data, cid, cq_id, platform, message_id)
        )
        or True,
    )

    assert bot_service.notification_bot_plugin_callback_service.handle_plugin_callback("hdhive_sr_1", "chat", "cq", _cq()) is True
    assert bot_service.notification_bot_plugin_callback_service.handle_plugin_callback("hdhive_tmdb_2", "chat", "cq", _cq()) is True
    assert bot_service.notification_bot_plugin_callback_service.handle_plugin_callback("hdhive_tmdbpage_3", "chat", "cq", _cq(88)) is True
    assert bot_service.notification_bot_plugin_callback_service.handle_plugin_callback("hdhive_page_4", "chat", "cq", _cq(99)) is True
    assert calls == [
        ("search", "hdhive_sr_1", "chat", "cq", "tg"),
        ("tmdb", "hdhive_tmdb_2", "chat", "cq", "tg"),
        ("tmdbpage", "hdhive_tmdbpage_3", "chat", "cq", "tg", 88),
        ("page", "hdhive_page_4", "chat", "cq", "tg", 99),
    ]


def test_plugin_callback_preserves_tmdb_page_logging_and_false_result(monkeypatch):
    from app.domains.notifications import bot_service

    logger = _patch_logger(monkeypatch)
    _install_module(
        monkeypatch,
        "app.plugins.hdhive.plugin",
        handle_hdhive_tmdbpage_callback=lambda data, cid, cq_id, platform, message_id: False,
    )

    handled = bot_service.notification_bot_plugin_callback_service.handle_plugin_callback(
        "hdhive_tmdbnext_3",
        "chat",
        "cq",
        _cq(88),
    )

    assert handled is False
    assert logger.infos == [
        "[Bot] 检查TMDB分页回调: data=hdhive_tmdbnext_3...",
        "[Bot] 匹配到TMDB分页回调: hdhive_tmdbnext_3",
        "[Bot] TMDB分页回调结果: False",
    ]
    assert logger.errors == []


def test_plugin_callback_logs_tmdb_page_exceptions(monkeypatch):
    from app.domains.notifications import bot_service

    logger = _patch_logger(monkeypatch)

    def raise_page(*_args):
        raise RuntimeError("page down")

    _install_module(monkeypatch, "app.plugins.hdhive.plugin", handle_hdhive_tmdbpage_callback=raise_page)

    handled = bot_service.notification_bot_plugin_callback_service.handle_plugin_callback("hdhive_tmdbprev_3", "chat", "cq", _cq())

    assert handled is False
    assert logger.errors == ["[Bot] TMDB分页回调异常: page down"]


def test_request_hdhive_callback_dispatches_and_logs_errors(monkeypatch):
    from app.domains.notifications import bot_service

    logger = _patch_logger(monkeypatch)
    calls = []
    _install_module(
        monkeypatch,
        "app.plugins.hdhive.plugin",
        handle_request_hdhive_callback=lambda data, cid, cq_id, platform: calls.append((data, cid, cq_id, platform)) or True,
    )

    assert bot_service.notification_bot_plugin_callback_service.handle_request_hdhive_callback("noop", "chat", "cq") is False
    assert bot_service.notification_bot_plugin_callback_service.handle_request_hdhive_callback("req_hdhive_1", "chat", "cq") is True
    assert calls == [("req_hdhive_1", "chat", "cq", "tg")]
    assert logger.errors == []

    def raise_request(*_args):
        raise RuntimeError("request down")

    _install_module(monkeypatch, "app.plugins.hdhive.plugin", handle_request_hdhive_callback=raise_request)
    assert bot_service.notification_bot_plugin_callback_service.handle_request_hdhive_callback("req_hdhive_2", "chat", "cq") is False
    assert logger.errors == ["[Bot] 求片影巢搜索回调异常: request down"]


def test_handle_callback_delegates_plugin_callback_after_answer(monkeypatch):
    from app.domains.notifications import bot_service

    bot = bot_service.NotificationBot()
    calls = []
    monkeypatch.setattr(bot_service, "get_notify_tg_bot_token", lambda: "token")
    monkeypatch.setattr(bot_service, "get_safe_proxies", lambda: {"proxy": "ok"})
    monkeypatch.setattr(
        bot_service.telegram_client,
        "post_api",
        lambda token, method, **kwargs: calls.append(("telegram", token, method, kwargs)),
    )
    monkeypatch.setattr(
        bot_service.notification_bot_plugin_callback_service,
        "handle_plugin_callback",
        lambda data, cid, cq_id, cq: calls.append(("plugin", data, cid, cq_id)) or True,
    )

    bot._handle_callback({"id": "cq", "data": "p115_tf_1", "message": {"chat": {"id": 42}, "message_id": 7}})

    assert calls == [
        (
            "telegram",
            "token",
            "answerCallbackQuery",
            {"json": {"callback_query_id": "cq"}, "proxies": {"proxy": "ok"}, "timeout": 5},
        ),
        ("plugin", "p115_tf_1", "42", "cq"),
    ]
