import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.bot.notification_bot import bot_service


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text="ok"):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class FakeLogger:
    def __init__(self):
        self.debugs = []
        self.infos = []
        self.warnings = []
        self.errors = []

    def debug(self, message):
        self.debugs.append(message)

    def info(self, message):
        self.infos.append(message)

    def warning(self, message):
        self.warnings.append(message)

    def error(self, message):
        self.errors.append(message)


class FakeTime:
    def __init__(self, now):
        self.now = now

    def time(self):
        return self.now


class FakeWeComClient:
    def __init__(self):
        self.calls = []
        self.access_token_response = {"errcode": 0, "access_token": "new-token", "expires_in": 7200}
        self.upload_response = FakeResponse(status_code=200, payload={"errcode": 40001}, text="fail")
        self.send_response = FakeResponse(payload={"errcode": 0})

    def get_access_token(self, base_url, corpid, corpsecret, *, timeout=10):
        self.calls.append(("get_access_token", base_url, corpid, corpsecret, timeout))
        return FakeResponse(payload=self.access_token_response)

    def create_menu(self, base_url, access_token, agentid, payload, *, timeout=5):
        self.calls.append(("create_menu", base_url, access_token, agentid, payload, timeout))
        return FakeResponse(payload={"errcode": 0})

    def upload_image(self, base_url, access_token, files, *, timeout=10):
        self.calls.append(("upload_image", base_url, access_token, files, timeout))
        return self.upload_response

    def send_message(self, base_url, access_token, payload, *, timeout=10):
        self.calls.append(("send_message", base_url, access_token, payload, timeout))
        return self.send_response


def _patch_common_wecom(monkeypatch, fake_client=None, fake_logger=None):
    fake_client = fake_client or FakeWeComClient()
    fake_logger = fake_logger or FakeLogger()
    monkeypatch.setattr(bot_service, "wecom_client", fake_client)
    monkeypatch.setattr(bot_service, "logger", fake_logger)
    monkeypatch.setattr(bot_service, "get_safe_wecom_base", lambda: "https://wecom.example")
    monkeypatch.setattr(bot_service, "get_wecom_corpid", lambda: "corp-id")
    monkeypatch.setattr(bot_service, "get_wecom_corpsecret", lambda: "corp-secret")
    monkeypatch.setattr(bot_service, "get_wecom_agentid", lambda: "1000001")
    return fake_client, fake_logger


def test_wecom_token_uses_instance_cache_and_legacy_dependencies(monkeypatch):
    fake_client, fake_logger = _patch_common_wecom(monkeypatch)
    monkeypatch.setattr(bot_service, "time", FakeTime(1000))

    bot = bot_service.NotificationBot()

    assert bot._get_wecom_token() == "new-token"
    assert bot.wecom_token == "new-token"
    assert bot.wecom_token_expires == 8140
    assert fake_client.calls == [
        ("get_access_token", "https://wecom.example", "corp-id", "corp-secret", 5)
    ]

    assert bot._get_wecom_token() == "new-token"
    assert fake_client.calls == [
        ("get_access_token", "https://wecom.example", "corp-id", "corp-secret", 5)
    ]
    assert "获取 access_token 成功" in fake_logger.infos[0]


def test_wecom_html_to_text_preserves_legacy_conversion():
    bot = bot_service.NotificationBot()

    text = bot._html_to_wecom_text(
        "<b>标题</b> <i>说明</i> <code>CODE</code> <a href=\"https://example.test\">链接</a>",
        {"inline_keyboard": [[{"text": "打开", "url": "https://open.test"}]]},
    )

    assert text == "【标题】 说明 CODE 链接: https://example.test\n\n🔗 打开: https://open.test"


def test_wecom_message_send_uses_cached_token_and_converted_text(monkeypatch):
    fake_client, fake_logger = _patch_common_wecom(monkeypatch)
    bot = bot_service.NotificationBot()
    bot.wecom_token = "cached-token"
    bot.wecom_token_expires = 9999999999

    bot._send_wecom_message(
        "<b>标题</b>\n<a href=\"https://detail.test\">详情</a>",
        {"inline_keyboard": [[{"text": "操作", "url": "https://action.test"}]]},
        "user-a",
    )

    send_call = fake_client.calls[-1]
    assert send_call[0] == "send_message"
    assert send_call[1] == "https://wecom.example"
    assert send_call[2] == "cached-token"
    assert send_call[3] == {
        "touser": "user-a",
        "msgtype": "text",
        "agentid": 1000001,
        "text": {
            "content": "【标题】\n详情: https://detail.test\n\n🔗 操作: https://action.test",
        },
    }
    assert "消息发送成功" in fake_logger.infos[-1]


def test_wecom_photo_send_builds_news_payload_with_emby_cover_fallback(monkeypatch):
    fake_client, _fake_logger = _patch_common_wecom(monkeypatch)
    monkeypatch.setattr(bot_service, "REPORT_COVER_URL", "https://cover.default/report.jpg")
    monkeypatch.setattr(bot_service, "get_media_server_main_public_or_host", lambda: "https://emby.example")
    monkeypatch.setattr(bot_service, "get_media_server_host", lambda: "https://fallback-emby.example")
    monkeypatch.setattr(bot_service, "get_media_server_api_key", lambda: "api-key")
    monkeypatch.setattr(bot_service, "get_pulse_url", lambda: "https://pulse.example")

    bot = bot_service.NotificationBot()
    bot.wecom_token = "cached-token"
    bot.wecom_token_expires = 9999999999

    bot._send_wecom_photo(
        b"image-bytes",
        "<b>Movie Title</b>\nLine 1\nLine 2",
        {"inline_keyboard": [[{"text": "Play", "url": "https://emby.example/web/index.html#!/item?id=item1"}]]},
        "user-a",
    )

    assert fake_client.calls[0][0] == "upload_image"
    send_call = fake_client.calls[-1]
    assert send_call[0] == "send_message"
    payload = send_call[3]
    article = payload["news"]["articles"][0]
    assert payload["touser"] == "user-a"
    assert payload["msgtype"] == "news"
    assert payload["agentid"] == 1000001
    assert article == {
        "title": "Movie Title",
        "description": "Line 1\nLine 2",
        "url": "https://emby.example/web/index.html#!/item?id=item1",
        "picurl": "https://emby.example/emby/Items/item1/Images/Backdrop?maxWidth=800&api_key=api-key",
    }
