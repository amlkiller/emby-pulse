import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.bot.notification_bot import bot_service


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


class FakeMediaApi:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def get(self, path, timeout=None):
        self.calls.append((path, timeout))
        if self.error and path == "/System/Info":
            raise self.error
        if path == "/System/Info":
            return FakeResponse(payload={"Version": "4.8.9", "OperatingSystem": "Linux"})
        if path == "/Items/Counts":
            return FakeResponse(payload={"MovieCount": 10, "SeriesCount": 2, "EpisodeCount": 88})
        if path == "/Sessions":
            return FakeResponse(payload=[{"NowPlayingItem": {"Id": "i1"}}, {}, {"NowPlayingItem": {"Id": "i2"}}])
        return FakeResponse(status_code=404)


class FakeNetworkClient:
    def __init__(self, error_urls=None):
        self.calls = []
        self.error_urls = set(error_urls or [])

    def get(self, url, timeout=None):
        self.calls.append((url, timeout))
        if url in self.error_urls:
            raise RuntimeError("route offline")
        return FakeResponse()


class FakeTime:
    def __init__(self, values):
        self.values = list(values)

    def time(self):
        if not self.values:
            raise AssertionError("FakeTime exhausted")
        return self.values.pop(0)


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


def _patch_check_dependencies(
    monkeypatch,
    *,
    public_url="",
    media_error=None,
    network_error_urls=None,
    time_values=None,
):
    media = FakeMediaApi(error=media_error)
    network = FakeNetworkClient(error_urls=network_error_urls)
    logger = FakeLogger()
    fake_time = FakeTime(time_values or [10.0, 10.123])

    monkeypatch.setattr(bot_service, "media_api", media)
    monkeypatch.setattr(bot_service, "network_client", network)
    monkeypatch.setattr(bot_service, "get_media_server_public_url", lambda: public_url)
    monkeypatch.setattr(bot_service, "logger", logger)
    monkeypatch.setattr(bot_service, "time", fake_time)

    return media, network, logger


def test_check_command_formats_online_status_and_json_routes_through_legacy_dependencies(monkeypatch):
    media, network, logger = _patch_check_dependencies(
        monkeypatch,
        public_url='[{"name":"主线路","url":"https://emby.example"}]',
        time_values=[10.0, 10.123, 20.0, 20.050],
    )
    bot, sent = _capture_bot_messages()

    bot._cmd_check("chat-1", "tg")

    assert media.calls == [
        ("/System/Info", 5),
        ("/Items/Counts", 3),
        ("/Sessions", 3),
    ]
    assert network.calls == [("https://emby.example/web/favicon.ico", 3)]
    assert sent == [
        (
            "chat-1",
            (
                "📡 <b>Emby 服务器状态探针</b>\n\n"
                "🟢 <b>运行状态</b>：在线 (响应延迟: 122ms)\n"
                "🏷️ <b>系统版本</b>：Emby Server 4.8.9\n"
                "💻 <b>宿主环境</b>：Linux\n\n"
                "📊 <b>媒体库容量</b>\n"
                "🎬 电影：10 部\n"
                "📺 剧集：2 部 (共 88 集)\n\n"
                "👥 <b>当前活跃</b>：2 人正在观看\n\n"
                "🌐 <b>公网节点延迟测速</b>\n"
                "🟢 主线路: 50ms"
            ),
            "HTML",
            None,
            "tg",
        )
    ]
    assert logger.errors == []


def test_check_command_parses_plain_public_url_and_marks_slow_route(monkeypatch):
    _media, network, logger = _patch_check_dependencies(
        monkeypatch,
        public_url="https://plain.example/",
        time_values=[1.0, 1.010, 2.0, 2.250],
    )
    bot, sent = _capture_bot_messages()

    bot._cmd_check("chat-1", "wecom")

    assert network.calls == [("https://plain.example/web/favicon.ico", 3)]
    assert "🌐 <b>公网节点延迟测速</b>" in sent[0][1]
    assert "🟡 默认主线路: 250ms" in sent[0][1]
    assert sent[0][4] == "wecom"
    assert logger.errors == []


def test_check_command_marks_failed_route_offline(monkeypatch):
    _media, network, logger = _patch_check_dependencies(
        monkeypatch,
        public_url='[{"name":"故障线路","url":"https://offline.example"}]',
        network_error_urls={"https://offline.example/web/favicon.ico"},
        time_values=[1.0, 1.020, 2.0],
    )
    bot, sent = _capture_bot_messages()

    bot._cmd_check("chat-1", "tg")

    assert network.calls == [("https://offline.example/web/favicon.ico", 3)]
    assert "🔴 故障线路: 超时/离线" in sent[0][1]
    assert logger.errors == []


def test_check_command_logs_route_config_error_but_sends_base_status(monkeypatch):
    media, network, logger = _patch_check_dependencies(monkeypatch, time_values=[1.0, 1.001])

    def fail_public_url():
        raise RuntimeError("bad route config")

    monkeypatch.setattr(bot_service, "get_media_server_public_url", fail_public_url)
    bot, sent = _capture_bot_messages()

    bot._cmd_check("chat-1", "tg")

    assert media.calls == [("/System/Info", 5), ("/Items/Counts", 3), ("/Sessions", 3)]
    assert network.calls == []
    assert "🌐 <b>公网节点延迟测速</b>" not in sent[0][1]
    assert logger.errors == ["Route ping error in bot check: bad route config"]


def test_check_command_sends_offline_fallback_when_system_info_fails(monkeypatch):
    media, network, logger = _patch_check_dependencies(
        monkeypatch,
        media_error=RuntimeError("media offline"),
        time_values=[1.0],
    )
    bot, sent = _capture_bot_messages()

    bot._cmd_check("chat-1", "tg")

    assert media.calls == [("/System/Info", 5)]
    assert network.calls == []
    assert sent == [("chat-1", "❌ 离线或无法连接到服务器", "HTML", None, "tg")]
    assert logger.errors == []
