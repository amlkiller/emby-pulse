import sys
import threading
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeLogger:
    def __init__(self):
        self.calls = []

    def warning(self, message):
        self.calls.append(("warning", message))

    def info(self, message):
        self.calls.append(("info", message))

    def exception(self, message):
        self.calls.append(("exception", message))


class FakeMediaResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _reset_registration_quota_state(monkeypatch, now=100.0):
    from tests.user_bot_worker_boundary import user_bot_worker_boundary as user_bot_service

    monkeypatch.setattr(user_bot_service, "_quota_lock", threading.RLock())
    monkeypatch.setattr(user_bot_service, "_quota_reserved", 0)
    monkeypatch.setattr(user_bot_service, "_user_count_cache", {"count": None, "users": None, "ts": 0.0})
    monkeypatch.setattr(user_bot_service, "_batch_used_lock", threading.RLock())
    monkeypatch.setattr(user_bot_service, "_batch_used_mem", None)
    monkeypatch.setattr(user_bot_service, "_batch_used_dirty", 0)
    monkeypatch.setattr(user_bot_service, "_batch_flush_stop", threading.Event())
    monkeypatch.setattr(user_bot_service, "_batch_flush_thread", None)
    monkeypatch.setattr(user_bot_service, "time", SimpleNamespace(time=lambda: now))
    monkeypatch.setattr(user_bot_service, "logger", FakeLogger())
    return user_bot_service


def test_batch_load_and_flush_use_legacy_settings_functions(monkeypatch):
    user_bot_service = _reset_registration_quota_state(monkeypatch)
    writes = []

    monkeypatch.setattr(user_bot_service, "get_user_bot_registration_batch_used", lambda: "7")
    monkeypatch.setattr(user_bot_service, "set_user_bot_registration_batch_used", lambda value: writes.append(value))

    user_bot_service._load_batch_used_from_cfg()

    assert user_bot_service._batch_used_mem == 7
    assert user_bot_service._batch_used_dirty == 0

    user_bot_service._batch_used_dirty = 2
    user_bot_service._flush_batch_used()

    assert writes == [7]
    assert user_bot_service._batch_used_dirty == 0


def test_get_batch_used_snapshot_prefers_legacy_memory_then_settings(monkeypatch):
    user_bot_service = _reset_registration_quota_state(monkeypatch)
    calls = []

    monkeypatch.setattr(
        user_bot_service,
        "get_user_bot_registration_batch_used",
        lambda: calls.append(("get_batch_used",)) or 11,
    )

    assert user_bot_service.get_batch_used_snapshot() == 11
    assert calls == [("get_batch_used",)]

    user_bot_service._batch_used_mem = 12
    assert user_bot_service.get_batch_used_snapshot() == 12
    assert calls == [("get_batch_used",)]


def test_user_count_cache_uses_legacy_media_hidden_users_and_time(monkeypatch):
    user_bot_service = _reset_registration_quota_state(monkeypatch, now=200.0)
    calls = []
    users = [
        {"Name": "visible", "Policy": {"IsAdministrator": False}},
        {"Name": "hidden", "Policy": {"IsAdministrator": False}},
        {"Name": "admin", "Policy": {"IsAdministrator": True}},
    ]

    def fake_media_get(path, timeout=None):
        calls.append(("media_get", path, timeout))
        return FakeMediaResponse(users)

    monkeypatch.setattr(user_bot_service.media_api, "get", fake_media_get)
    monkeypatch.setattr(user_bot_service, "get_hidden_users", lambda: ["hidden"])

    assert user_bot_service.get_cached_user_count_for_api(force=True) == 1
    assert user_bot_service.get_users_list_cached() is users
    assert user_bot_service._user_count_cache == {"count": 1, "users": users, "ts": 200.0}
    assert calls == [("media_get", "/Users", 5)]


def test_quota_reserve_release_mutates_legacy_reserved_and_cache(monkeypatch):
    user_bot_service = _reset_registration_quota_state(monkeypatch, now=300.0)
    users = [{"Name": "existing", "Policy": {"IsAdministrator": False}}]
    closed = []
    notified = []

    monkeypatch.setattr(user_bot_service.media_api, "get", lambda path, timeout=None: FakeMediaResponse(users))
    monkeypatch.setattr(user_bot_service, "get_hidden_users", lambda: [])
    monkeypatch.setattr(user_bot_service, "set_user_bot_open_reg_enabled", lambda enabled: closed.append(enabled))
    monkeypatch.setattr(user_bot_service, "_send_open_reg_closed_notify", lambda reason: notified.append(reason))

    ok, reason = user_bot_service._reserve_quota_slot("total", 2)

    assert (ok, reason) == (True, None)
    assert user_bot_service._quota_reserved == 1

    users.append({"Name": "new", "Policy": {"IsAdministrator": False}})
    user_bot_service._release_quota_slot(committed=True, quota_mode="total", quota=2)

    assert user_bot_service._quota_reserved == 0
    assert user_bot_service._user_count_cache["count"] == 2
    assert closed == [False]
    assert notified == ["用户总数已达上限"]


def test_inc_batch_used_closes_open_registration_through_legacy_hooks(monkeypatch):
    user_bot_service = _reset_registration_quota_state(monkeypatch)
    writes = []
    closed = []
    notified = []

    monkeypatch.setattr(user_bot_service, "get_user_bot_registration_batch_used", lambda: 1)
    monkeypatch.setattr(user_bot_service, "set_user_bot_registration_batch_used", lambda value: writes.append(value))
    monkeypatch.setattr(user_bot_service, "set_user_bot_open_reg_enabled", lambda enabled: closed.append(enabled))
    monkeypatch.setattr(user_bot_service, "_send_open_reg_closed_notify", lambda reason: notified.append(reason))

    user_bot_service._inc_batch_used(quota=2)

    assert user_bot_service._batch_used_mem == 2
    assert user_bot_service._batch_used_dirty == 0
    assert writes == [2]
    assert closed == [False]
    assert notified == ["批次名额已满"]


def test_batch_flush_thread_lifecycle_uses_legacy_threading_and_state(monkeypatch):
    user_bot_service = _reset_registration_quota_state(monkeypatch)

    class FakeThread:
        instances = []

        def __init__(self, target=None, daemon=False, name=None):
            self.target = target
            self.daemon = daemon
            self.name = name
            self.started = False
            self.alive = False
            self.join_timeout = None
            FakeThread.instances.append(self)

        def start(self):
            self.started = True
            self.alive = True

        def is_alive(self):
            return self.alive

        def join(self, timeout=None):
            self.join_timeout = timeout
            self.alive = False

    monkeypatch.setattr(user_bot_service.threading, "Thread", FakeThread)

    user_bot_service._start_batch_flush_thread()
    user_bot_service._start_batch_flush_thread()

    assert len(FakeThread.instances) == 1
    assert user_bot_service._batch_flush_stop.is_set() is False
    assert user_bot_service._batch_flush_thread is FakeThread.instances[0]
    assert user_bot_service._batch_flush_thread.target is user_bot_service._batch_flush_loop
    assert user_bot_service._batch_flush_thread.daemon is True
    assert user_bot_service._batch_flush_thread.name == "batch-flush"

    user_bot_service._stop_batch_flush_thread()

    assert user_bot_service._batch_flush_stop.is_set() is True
    assert FakeThread.instances[0].join_timeout == 1
    assert user_bot_service._batch_flush_thread is None
