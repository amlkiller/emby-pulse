import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeResponse:
    def __init__(self, status_code, result=None):
        self.status_code = status_code
        self.result = result or []

    def json(self):
        return {"result": self.result}


class FakeTelegramClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get_updates(self, token, params=None, proxies=None, timeout=None):
        self.calls.append((token, params, proxies, timeout))
        return self.response


class FakeStopEvent:
    def __init__(self):
        self.waits = []
        self.stopped = False

    def wait(self, seconds):
        self.waits.append(seconds)
        self.stopped = True
        return True

    def is_set(self):
        return self.stopped


class FakeLogger:
    def __init__(self):
        self.errors = []
        self.debugs = []

    def error(self, message):
        self.errors.append(message)

    def debug(self, message):
        self.debugs.append(message)


def test_polling_loop_preserves_update_submit_offset_and_busy_message_via_legacy_providers(monkeypatch):
    from app.bot.user_bot import user_bot_polling_service, user_bot_service

    updates = [
        {"update_id": 10, "message": {"chat": {"id": 123}, "text": "/start"}},
        {"update_id": 11, "callback_query": {"id": "cq-1"}},
    ]
    telegram_client = FakeTelegramClient(FakeResponse(200, updates))
    logger = FakeLogger()
    submitted = []
    sent = []
    offsets = [7]
    loop_count = 0

    def running():
        nonlocal loop_count
        loop_count += 1
        return loop_count == 1

    def fake_submit_task(func, payload):
        submitted.append((func.__name__, payload))
        return func.__name__ != "on_message"

    monkeypatch.setattr(user_bot_service, "telegram_client", telegram_client)
    monkeypatch.setattr(user_bot_service, "get_safe_proxies", lambda: {"https": "proxy"})
    monkeypatch.setattr(user_bot_service, "_submit_task", fake_submit_task)
    monkeypatch.setattr(user_bot_service, "_send", lambda chat_id, text, reply_markup=None: sent.append((chat_id, text, reply_markup)))
    monkeypatch.setattr(user_bot_service, "logger", logger)

    def on_message(_payload):
        return None

    def on_callback(_payload):
        return None

    user_bot_polling_service.run_polling_loop(
        "token",
        running,
        FakeStopEvent(),
        lambda: offsets[-1],
        lambda offset: offsets.append(offset),
        lambda: on_message,
        lambda: on_callback,
    )

    assert telegram_client.calls == [("token", {"offset": 7, "timeout": 30}, {"https": "proxy"}, 35)]
    assert offsets == [7, 11, 12]
    assert submitted == [
        ("on_message", {"chat": {"id": 123}, "text": "/start"}),
        ("on_callback", {"id": "cq-1"}),
    ]
    assert sent == [("123", "⏳ 当前请求人数过多，请稍后再试...", None)]
    assert logger.errors == []
    assert logger.debugs == []


def test_polling_loop_preserves_retry_waits_for_non_200_and_exceptions(monkeypatch):
    from app.bot.user_bot import user_bot_polling_service, user_bot_service

    logger = FakeLogger()
    stop_event = FakeStopEvent()
    monkeypatch.setattr(user_bot_service, "telegram_client", FakeTelegramClient(FakeResponse(500)))
    monkeypatch.setattr(user_bot_service, "get_safe_proxies", lambda: {})
    monkeypatch.setattr(user_bot_service, "logger", logger)

    user_bot_polling_service.run_polling_loop(
        "token",
        lambda: True,
        stop_event,
        lambda: 0,
        lambda _offset: None,
        lambda: None,
        lambda: None,
    )

    assert stop_event.waits == [3]
    assert logger.debugs == []

    class RaisingTelegramClient:
        def get_updates(self, *args, **kwargs):
            raise RuntimeError("network down")

    logger = FakeLogger()
    stop_event = FakeStopEvent()
    monkeypatch.setattr(user_bot_service, "telegram_client", RaisingTelegramClient())
    monkeypatch.setattr(user_bot_service, "logger", logger)

    user_bot_polling_service.run_polling_loop(
        "token",
        lambda: True,
        stop_event,
        lambda: 0,
        lambda _offset: None,
        lambda: None,
        lambda: None,
    )

    assert stop_event.waits == [5]
    assert logger.debugs == ["[UserBot] polling 异常: network down"]
