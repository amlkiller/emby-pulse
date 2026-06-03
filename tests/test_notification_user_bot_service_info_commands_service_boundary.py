import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeTime:
    def __init__(self, values):
        self.values = list(values)

    def time(self):
        return self.values.pop(0)


class FakeNetworkClient:
    def __init__(self, failures=None):
        self.calls = []
        self.failures = set(failures or [])

    def get(self, url, timeout=None):
        self.calls.append((url, timeout))
        if url in self.failures:
            raise RuntimeError("offline")
        return object()


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.payload = payload or {}

    def json(self):
        return self.payload


class FakeMediaApi:
    def __init__(self):
        self.response = FakeResponse(200, {"MovieCount": 2, "SeriesCount": 3, "EpisodeCount": 40})
        self.error = None
        self.calls = []

    def get(self, path, timeout=None):
        self.calls.append((path, timeout))
        if self.error:
            raise self.error
        return self.response


class FakeLogger:
    def __init__(self):
        self.calls = []

    def error(self, message):
        self.calls.append(("error", message))


def _reset_service_info_state(monkeypatch):
    from app.domains.notifications import user_bot_service

    sent = []
    replies = []
    unbound = []
    routes_calls = []
    network = FakeNetworkClient()
    media_api = FakeMediaApi()
    logger = FakeLogger()
    binding = {"emby_user_id": "u1", "emby_username": "Alice"}
    routes = [{"name": "Main", "url": "https://emby.example"}]

    def fake_reply(chat_id, text, reply_markup=None, msg_id=None):
        replies.append((chat_id, text, reply_markup, msg_id))
        return {"result": {"message_id": 900 + len(replies)}}

    def fake_get_routes(emby_uid=None):
        routes_calls.append(emby_uid)
        return routes

    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: binding)
    monkeypatch.setattr(user_bot_service, "_check_emby_account", lambda _binding: True)
    monkeypatch.setattr(user_bot_service, "_unbind_user", lambda tg_user_id: unbound.append(tg_user_id))
    monkeypatch.setattr(user_bot_service, "_reply", fake_reply)
    monkeypatch.setattr(user_bot_service, "_send", lambda chat_id, text, reply_markup=None: sent.append((chat_id, text, reply_markup)))
    monkeypatch.setattr(user_bot_service, "_main_menu_keyboard", lambda binding_arg=None: {"menu": binding_arg})
    monkeypatch.setattr(user_bot_service, "get_media_server_user_routes", fake_get_routes)
    monkeypatch.setattr(user_bot_service, "network_client", network)
    monkeypatch.setattr(user_bot_service, "media_api", media_api)
    monkeypatch.setattr(user_bot_service, "time", FakeTime([10.0, 10.05, 20.0, 20.35]))
    monkeypatch.setattr(user_bot_service, "logger", logger)

    return user_bot_service, sent, replies, unbound, routes_calls, routes, network, media_api, logger


def test_cmd_server_preserves_deleted_binding_and_unbound_route_lookup(monkeypatch):
    user_bot_service, sent, replies, unbound, routes_calls, _routes, _network, _media, _logger = _reset_service_info_state(monkeypatch)

    monkeypatch.setattr(user_bot_service, "_check_emby_account", lambda _binding: False)
    user_bot_service.cmd_server(10, "tg1", msg_id=5)
    assert unbound == ["tg1"]
    assert replies == [(10, "⚠️ 你的 Emby 账号已被删除，绑定已自动解除。请联系管理员。", {"menu": None}, 5)]
    assert sent == []
    assert routes_calls == []

    replies.clear()
    monkeypatch.setattr(user_bot_service, "_get_binding", lambda _tg_user_id: None)
    monkeypatch.setattr(user_bot_service, "_check_emby_account", lambda _binding: True)
    user_bot_service.cmd_server(10, "tg1", msg_id=6)
    assert routes_calls == [None]


def test_cmd_server_formats_latency_timeout_and_empty_routes(monkeypatch):
    user_bot_service, sent, replies, _unbound, routes_calls, routes, network, _media, _logger = _reset_service_info_state(monkeypatch)
    routes[:] = [
        {"name": "Fast", "url": "https://fast.example/"},
        {"name": "Slow", "url": "https://slow.example"},
    ]
    network.failures = {"https://slow.example/web/favicon.ico"}

    user_bot_service.cmd_server(10, "tg1", msg_id=5)

    assert routes_calls == ["u1"]
    assert network.calls == [
        ("https://fast.example/web/favicon.ico", 3),
        ("https://slow.example/web/favicon.ico", 3),
    ]
    assert replies == [(
        10,
        "📡 <b>服务器线路状态</b>\n\n🟢 <b>Fast</b>：50ms\n🔗 https://fast.example\n\n🔴 <b>Slow</b>：超时/离线\n🔗 https://slow.example",
        {"inline_keyboard": [[{"text": "🔙 主菜单", "callback_data": "ub_back_menu"}]]},
        5,
    )]

    replies.clear()
    sent.clear()
    routes[:] = []
    user_bot_service.cmd_server(10, "tg1")
    assert sent == [(10, "📡 管理员未配置公网地址", None)]
    assert replies == []


def test_cmd_library_preserves_success_non_200_and_exception(monkeypatch):
    user_bot_service, sent, replies, _unbound, _routes_calls, _routes, _network, media_api, _logger = _reset_service_info_state(monkeypatch)

    user_bot_service.cmd_library(10, "tg1", msg_id=5)
    assert media_api.calls == [("/Items/Counts", 5)]
    assert replies == [(
        10,
        "📊 <b>媒体库统计</b>\n\n🎬 电影：<b>2</b> 部\n📺 剧集：<b>3</b> 部\n🎞️ 总集数：<b>40</b> 集",
        {"inline_keyboard": [[{"text": "🔙 主菜单", "callback_data": "ub_back_menu"}]]},
        5,
    )]

    sent.clear()
    media_api.response = FakeResponse(503, {})
    user_bot_service.cmd_library(10, "tg1")
    assert sent == [(10, "❌ 无法获取媒体库信息", None)]

    sent.clear()
    media_api.error = RuntimeError("media down")
    user_bot_service.cmd_library(10, "tg1")
    assert sent == [(10, "❌ 连接服务器失败", None)]


def test_cmd_calendar_preserves_success_and_logged_failure(monkeypatch):
    from app.domains.notifications import calendar_notify

    user_bot_service, _sent, replies, _unbound, _routes_calls, _routes, _network, _media, logger = _reset_service_info_state(monkeypatch)
    monkeypatch.setattr(calendar_notify, "get_today_updates", lambda: ["episode"])
    monkeypatch.setattr(calendar_notify, "format_notify_message", lambda updates: f"formatted:{updates}")

    user_bot_service.cmd_calendar(10, "tg1", msg_id=5)

    assert replies == [(
        10,
        "formatted:['episode']",
        {"inline_keyboard": [[{"text": "🔙 主菜单", "callback_data": "ub_back_menu"}]]},
        5,
    )]

    replies.clear()

    def raise_updates():
        raise RuntimeError("calendar raw")

    monkeypatch.setattr(calendar_notify, "get_today_updates", raise_updates)
    user_bot_service.cmd_calendar(10, "tg1", msg_id=6)
    assert logger.calls == [("error", "[calendar命令] 执行失败: calendar raw")]
    assert replies == [(
        10,
        "❌ 获取今日更新失败，请稍后重试",
        {"inline_keyboard": [[{"text": "🔙 主菜单", "callback_data": "ub_back_menu"}]]},
        6,
    )]
