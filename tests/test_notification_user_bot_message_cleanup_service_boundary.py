import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeThread:
    instances = []

    def __init__(self, target, daemon=False):
        self.target = target
        self.daemon = daemon
        self.started = False
        FakeThread.instances.append(self)

    def start(self):
        self.started = True


class RunningThread(FakeThread):
    def start(self):
        self.started = True
        self.target()


class FakeTelegramClient:
    def __init__(self, fail_message_ids=None):
        self.calls = []
        self.fail_message_ids = set(fail_message_ids or [])

    def post_api(self, token, method, json=None, proxies=None, timeout=None):
        self.calls.append((token, method, json, proxies, timeout))
        if json and json.get("message_id") in self.fail_message_ids:
            raise RuntimeError("delete failed")
        return {"ok": True}


def _reset_message_cleanup_state(monkeypatch, thread_cls=FakeThread):
    from tests.user_bot_worker_boundary import user_bot_worker_boundary as user_bot_service

    FakeThread.instances = []
    monkeypatch.setattr(user_bot_service, "threading", SimpleNamespace(Thread=thread_cls))
    return user_bot_service


def test_delete_messages_later_starts_daemon_thread_through_legacy_wrapper(monkeypatch):
    user_bot_service = _reset_message_cleanup_state(monkeypatch)

    user_bot_service._delete_messages_later("chat-1", [10], delay_seconds=15)

    assert len(FakeThread.instances) == 1
    thread = FakeThread.instances[0]
    assert callable(thread.target)
    assert thread.daemon is True
    assert thread.started is True


def test_delete_messages_later_waits_and_skips_when_token_missing(monkeypatch):
    user_bot_service = _reset_message_cleanup_state(monkeypatch, thread_cls=RunningThread)
    sleeps = []
    telegram = FakeTelegramClient()

    monkeypatch.setattr(user_bot_service, "time", SimpleNamespace(sleep=lambda seconds: sleeps.append(seconds)))
    monkeypatch.setattr(user_bot_service, "get_user_bot_token", lambda: "")
    monkeypatch.setattr(user_bot_service, "telegram_client", telegram)
    monkeypatch.setattr(user_bot_service, "get_safe_proxies", lambda: {"https": "http://proxy"})

    user_bot_service._delete_messages_later("chat-1", [10], delay_seconds=12)

    assert sleeps == [12]
    assert telegram.calls == []


def test_delete_messages_later_deletes_truthy_message_ids_with_runtime_proxies(monkeypatch):
    user_bot_service = _reset_message_cleanup_state(monkeypatch, thread_cls=RunningThread)
    sleeps = []
    telegram = FakeTelegramClient()

    monkeypatch.setattr(user_bot_service, "time", SimpleNamespace(sleep=lambda seconds: sleeps.append(seconds)))
    monkeypatch.setattr(user_bot_service, "get_user_bot_token", lambda: "legacy-token")
    monkeypatch.setattr(user_bot_service, "telegram_client", telegram)
    monkeypatch.setattr(user_bot_service, "get_safe_proxies", lambda: {"https": "http://proxy"})

    user_bot_service._delete_messages_later("chat-1", [10, None, 0, 11], delay_seconds=5)

    assert sleeps == [5]
    assert telegram.calls == [
        (
            "legacy-token",
            "deleteMessage",
            {"chat_id": "chat-1", "message_id": 10},
            {"https": "http://proxy"},
            10,
        ),
        (
            "legacy-token",
            "deleteMessage",
            {"chat_id": "chat-1", "message_id": 11},
            {"https": "http://proxy"},
            10,
        ),
    ]


def test_delete_messages_later_swallows_per_message_delete_errors(monkeypatch):
    user_bot_service = _reset_message_cleanup_state(monkeypatch, thread_cls=RunningThread)
    telegram = FakeTelegramClient(fail_message_ids={10})

    monkeypatch.setattr(user_bot_service, "time", SimpleNamespace(sleep=lambda _seconds: None))
    monkeypatch.setattr(user_bot_service, "get_user_bot_token", lambda: "legacy-token")
    monkeypatch.setattr(user_bot_service, "telegram_client", telegram)
    monkeypatch.setattr(user_bot_service, "get_safe_proxies", lambda: None)

    user_bot_service._delete_messages_later("chat-1", [10, 11], delay_seconds=0)

    assert [call[2]["message_id"] for call in telegram.calls] == [10, 11]
