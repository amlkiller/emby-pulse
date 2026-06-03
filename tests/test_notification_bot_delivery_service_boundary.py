import io
import json
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.bot.notification_bot import bot_service


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text="ok", content=b""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.content = content

    def json(self):
        return self._payload


class FakeLogger:
    def __init__(self):
        self.debugs = []
        self.infos = []
        self.errors = []

    def debug(self, message):
        self.debugs.append(message)

    def info(self, message):
        self.infos.append(message)

    def error(self, message):
        self.errors.append(message)


class FakeTelegramClient:
    def __init__(self, photo_status=200):
        self.calls = []
        self.photo_status = photo_status

    def send_photo(self, token, data=None, files=None, proxies=None, timeout=None):
        self.calls.append(("send_photo", token, data, files, proxies, timeout))
        return FakeResponse(
            status_code=self.photo_status,
            payload={"result": {"message_id": 101}},
            text="photo-ok" if self.photo_status == 200 else "photo-fail",
        )

    def send_message(self, token, data, proxies=None, timeout=None):
        self.calls.append(("send_message", token, data, proxies, timeout))
        return FakeResponse(payload={"result": {"message_id": 202}}, text="message-ok")

    def post_api(self, token, method, json=None, proxies=None, timeout=None):
        self.calls.append(("post_api", token, method, json, proxies, timeout))
        return FakeResponse(status_code=200, text="edit-ok")


class FakeNetworkClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, proxies=None, headers=None, timeout=None):
        self.calls.append((url, proxies, headers, timeout))
        return self.response


def _patch_common(monkeypatch, fake_tg=None, fake_logger=None):
    fake_tg = fake_tg or FakeTelegramClient()
    fake_logger = fake_logger or FakeLogger()
    submit_calls = []
    record_calls = []

    monkeypatch.setattr(bot_service, "telegram_client", fake_tg)
    monkeypatch.setattr(bot_service, "logger", fake_logger)
    monkeypatch.setattr(bot_service, "get_safe_proxies", lambda: {"https": "proxy"})
    monkeypatch.setattr(bot_service, "get_notify_tg_bot_token", lambda: "tg-token")
    monkeypatch.setattr(bot_service, "get_tg_chat_id", lambda: "100, 200")
    monkeypatch.setattr(bot_service, "get_wecom_corpid", lambda: "corp-id")
    monkeypatch.setattr(bot_service, "get_wecom_touser", lambda: "wecom-user")
    monkeypatch.setattr(bot_service, "_submit_bot_task", lambda fn, *args: submit_calls.append((fn, args)))
    monkeypatch.setattr(bot_service, "_extract_request_tmdb_id", lambda reply_markup: 9988)
    monkeypatch.setattr(
        bot_service,
        "_record_request_admin_message",
        lambda tmdb_id, chat_id, message_id, is_caption, original_text: record_calls.append(
            (tmdb_id, chat_id, message_id, is_caption, original_text)
        ),
    )
    return fake_tg, fake_logger, submit_calls, record_calls


def test_send_message_fans_out_to_telegram_and_submits_wecom_task(monkeypatch):
    fake_tg, fake_logger, submit_calls, record_calls = _patch_common(monkeypatch)

    bot = bot_service.NotificationBot()
    reply_markup = {"inline_keyboard": [[{"text": "Approve", "callback_data": "req_approve_9988"}]]}

    bot.send_message("sys_notify", "hello", reply_markup=reply_markup, platform="all")

    assert len(submit_calls) == 1
    assert submit_calls[0][0] == bot._send_wecom_message
    assert submit_calls[0][1] == ("hello", reply_markup, "wecom-user")

    send_calls = [call for call in fake_tg.calls if call[0] == "send_message"]
    assert [call[2]["chat_id"] for call in send_calls] == ["100", "200"]
    assert json.loads(send_calls[0][2]["reply_markup"]) == reply_markup
    assert send_calls[0][3] == {"https": "proxy"}
    assert record_calls == [
        (9988, "100", 202, False, "hello"),
        (9988, "200", 202, False, "hello"),
    ]
    assert fake_logger.infos[0].startswith("[Bot] 📤 发送消息 -> sys_notify: hello")


def test_send_photo_downloads_url_sends_photo_and_records_caption(monkeypatch):
    fake_tg, _fake_logger, submit_calls, record_calls = _patch_common(monkeypatch)
    fake_network = FakeNetworkClient(FakeResponse(content=b"poster-bytes"))
    monkeypatch.setattr(bot_service, "network_client", fake_network)

    bot = bot_service.NotificationBot()
    reply_markup = {"inline_keyboard": [[{"text": "Open", "url": "https://example.test"}]]}

    bot.send_photo("user_300", "https://image.tmdb.org/poster.jpg", "caption", reply_markup=reply_markup, platform="all")

    assert fake_network.calls == [
        (
            "https://image.tmdb.org/poster.jpg",
            {"https": "proxy"},
            {"User-Agent": "Mozilla/5.0"},
            10,
        )
    ]
    assert len(submit_calls) == 1
    assert submit_calls[0][0] == bot._send_wecom_photo
    assert submit_calls[0][1] == (b"poster-bytes", "caption", reply_markup, "wecom-user")

    photo_call = fake_tg.calls[0]
    assert photo_call[0] == "send_photo"
    assert photo_call[2]["chat_id"] == "300"
    assert photo_call[3]["photo"][1].read() == b"poster-bytes"
    assert record_calls == [(9988, "300", 101, True, "caption")]


def test_send_photo_falls_back_to_instance_send_message_on_photo_failure(monkeypatch):
    fake_tg, _fake_logger, _submit_calls, record_calls = _patch_common(monkeypatch, fake_tg=FakeTelegramClient(photo_status=500))
    fallback_calls = []

    bot = bot_service.NotificationBot()
    bot.send_message = lambda chat_id, text, parse_mode="HTML", reply_markup=None, platform="all": fallback_calls.append(
        (chat_id, text, parse_mode, reply_markup, platform)
    )

    bot.send_photo("admin-chat", io.BytesIO(b"image-bytes"), "caption", platform="tg")

    assert fake_tg.calls[0][0] == "send_photo"
    assert fallback_calls == [("admin-chat", "caption", "HTML", None, "tg")]
    assert record_calls == []


def test_edit_message_returns_telegram_result(monkeypatch):
    fake_tg, _fake_logger, _submit_calls, _record_calls = _patch_common(monkeypatch)

    bot = bot_service.NotificationBot()
    result = bot.edit_message("chat-1", 42, "edited", reply_markup={"inline_keyboard": []})

    assert result is True
    assert fake_tg.calls[-1] == (
        "post_api",
        "tg-token",
        "editMessageText",
        {
            "chat_id": "chat-1",
            "message_id": 42,
            "text": "edited",
            "parse_mode": "HTML",
            "reply_markup": json.dumps({"inline_keyboard": []}),
        },
        {"https": "proxy"},
        10,
    )
