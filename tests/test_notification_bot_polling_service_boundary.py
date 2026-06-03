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


class RaisingTelegramClient:
    def get_updates(self, *args, **kwargs):
        raise RuntimeError("network down")


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


def test_polling_loop_filters_messages_appends_links_and_submits_callbacks_via_legacy_entry(monkeypatch):
    from app.bot.notification_bot import bot_service

    updates = [
        {
            "update_id": 10,
            "message": {
                "chat": {"id": -100, "type": "group"},
                "text": "ignored group",
            },
        },
        {
            "update_id": 11,
            "message": {
                "chat": {"id": 999, "type": "private"},
                "text": "ignored non-admin",
            },
        },
        {
            "update_id": 12,
            "message": {
                "chat": {"id": 123, "type": "private"},
                "text": "hello",
                "entities": [
                    {"type": "text_link", "url": "https://example.test/text"},
                    {"type": "bold", "url": "https://example.test/bold"},
                ],
            },
        },
        {
            "update_id": 13,
            "message": {
                "chat": {"id": "456", "type": "private"},
                "caption": "caption",
                "caption_entities": [
                    {"type": "text_link", "url": "https://example.test/caption"},
                ],
            },
        },
        {
            "update_id": 14,
            "callback_query": {
                "id": "ignored-cq",
                "message": {"chat": {"id": 999}, "message_id": 1},
            },
        },
        {
            "update_id": 15,
            "callback_query": {
                "id": "admin-cq",
                "message": {"chat": {"id": 123}, "message_id": 2},
            },
        },
    ]
    telegram = FakeTelegramClient(FakeResponse(200, updates))
    proxies = {"https": "http://proxy.local:8080"}
    submitted = []
    handled_messages = []

    bot = bot_service.NotificationBot()
    bot.running = True
    bot._stop_event = FakeStopEvent()

    def handle_message(text, chat_id, platform=None):
        handled_messages.append((text, chat_id, platform))

    def handle_callback(_callback_query):
        return None

    def fake_submit_task(func, payload):
        submitted.append((func, payload))
        bot.running = False
        return True

    bot._handle_message = handle_message
    bot._handle_callback = handle_callback
    monkeypatch.setattr(bot_service, "get_notify_tg_bot_token", lambda: "tg-token")
    monkeypatch.setattr(bot_service, "get_tg_chat_id", lambda: "123，456")
    monkeypatch.setattr(bot_service, "get_safe_proxies", lambda: proxies)
    monkeypatch.setattr(bot_service, "telegram_client", telegram)
    monkeypatch.setattr(bot_service, "_submit_bot_task", fake_submit_task)

    bot._polling_loop()

    assert telegram.calls == [("tg-token", {"offset": 0, "timeout": 30}, proxies, 35)]
    assert bot.offset == 16
    assert handled_messages == [
        ("hello https://example.test/text", "123", "tg"),
        ("caption https://example.test/caption", "456", "tg"),
    ]
    assert submitted == [
        (
            handle_callback,
            {
                "id": "admin-cq",
                "message": {"chat": {"id": 123}, "message_id": 2},
            },
        )
    ]
    assert bot._stop_event.waits == []


def test_polling_loop_retries_non_200_with_five_second_stop_wait(monkeypatch):
    from app.bot.notification_bot import bot_service

    stop_event = FakeStopEvent()
    bot = bot_service.NotificationBot()
    bot.running = True
    bot._stop_event = stop_event
    telegram = FakeTelegramClient(FakeResponse(500))

    monkeypatch.setattr(bot_service, "get_notify_tg_bot_token", lambda: "tg-token")
    monkeypatch.setattr(bot_service, "get_tg_chat_id", lambda: "123")
    monkeypatch.setattr(bot_service, "get_safe_proxies", lambda: {})
    monkeypatch.setattr(bot_service, "telegram_client", telegram)

    bot._polling_loop()

    assert telegram.calls == [("tg-token", {"offset": 0, "timeout": 30}, {}, 35)]
    assert stop_event.waits == [5]


def test_polling_loop_retries_exceptions_with_five_second_stop_wait(monkeypatch):
    from app.bot.notification_bot import bot_service

    stop_event = FakeStopEvent()
    bot = bot_service.NotificationBot()
    bot.running = True
    bot._stop_event = stop_event

    monkeypatch.setattr(bot_service, "get_notify_tg_bot_token", lambda: "tg-token")
    monkeypatch.setattr(bot_service, "get_tg_chat_id", lambda: "123")
    monkeypatch.setattr(bot_service, "get_safe_proxies", lambda: {})
    monkeypatch.setattr(bot_service, "telegram_client", RaisingTelegramClient())

    bot._polling_loop()

    assert stop_event.waits == [5]
