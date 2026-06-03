import sys
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeContextLock:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeLogger:
    def __init__(self):
        self.calls = []

    def info(self, message):
        self.calls.append(("info", message))


class FakeCreatedLock:
    def __init__(self, name):
        self.name = name


def _reset_concurrency_state(monkeypatch, now=100.0):
    from app.bot.user_bot import user_bot_service

    monkeypatch.setattr(user_bot_service, "_rate_limit", defaultdict(float))
    monkeypatch.setattr(user_bot_service, "_username_locks", {})
    monkeypatch.setattr(user_bot_service, "_username_locks_lock", FakeContextLock())
    monkeypatch.setattr(user_bot_service, "_USERNAME_LOCK_MAX_SIZE", 4)
    monkeypatch.setattr(user_bot_service, "time", SimpleNamespace(time=lambda: now))
    monkeypatch.setattr(user_bot_service, "logger", FakeLogger())
    return user_bot_service


def test_rate_check_uses_legacy_rate_limit_and_time(monkeypatch):
    user_bot_service = _reset_concurrency_state(monkeypatch, now=100.0)

    assert user_bot_service._rate_check("tg1", cooldown=3) is True
    assert user_bot_service._rate_limit["tg1"] == 100.0

    monkeypatch.setattr(user_bot_service, "time", SimpleNamespace(time=lambda: 101.0))
    assert user_bot_service._rate_check("tg1", cooldown=3) is False
    assert user_bot_service._rate_limit["tg1"] == 100.0

    monkeypatch.setattr(user_bot_service, "time", SimpleNamespace(time=lambda: 104.0))
    assert user_bot_service._rate_check("tg1", cooldown=3) is True
    assert user_bot_service._rate_limit["tg1"] == 104.0


def test_username_lock_reuses_existing_legacy_lock(monkeypatch):
    user_bot_service = _reset_concurrency_state(monkeypatch)
    existing_lock = object()
    user_bot_service._username_locks["alice"] = existing_lock

    assert user_bot_service._get_username_lock("alice") is existing_lock
    assert user_bot_service._username_locks == {"alice": existing_lock}


def test_username_lock_creates_lock_through_legacy_threading(monkeypatch):
    user_bot_service = _reset_concurrency_state(monkeypatch)
    created = []

    def fake_lock_factory():
        lock = FakeCreatedLock(f"lock-{len(created)}")
        created.append(lock)
        return lock

    monkeypatch.setattr(user_bot_service, "threading", SimpleNamespace(Lock=fake_lock_factory))

    lock = user_bot_service._get_username_lock("bob")

    assert lock is created[0]
    assert user_bot_service._username_locks == {"bob": created[0]}


def test_username_lock_cleanup_uses_legacy_max_size_and_logger(monkeypatch):
    user_bot_service = _reset_concurrency_state(monkeypatch)
    existing = {f"user{i}": object() for i in range(5)}
    user_bot_service._username_locks.update(existing)
    created = []

    def fake_lock_factory():
        lock = FakeCreatedLock(f"created-{len(created)}")
        created.append(lock)
        return lock

    monkeypatch.setattr(user_bot_service, "threading", SimpleNamespace(Lock=fake_lock_factory))

    lock = user_bot_service._get_username_lock("new-user")

    assert lock is created[0]
    assert list(user_bot_service._username_locks.keys()) == ["user2", "user3", "user4", "new-user"]
    assert user_bot_service.logger.calls == [("info", "[UserBot] 清理用户名锁，移除 2 个")]
