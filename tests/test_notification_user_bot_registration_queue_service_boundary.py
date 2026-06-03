import sys
import threading
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeLogger:
    def __init__(self):
        self.calls = []

    def exception(self, message):
        self.calls.append(("exception", message))


class FakeExecutor:
    def __init__(self):
        self.submitted = []

    def submit(self, func):
        self.submitted.append(func)


class FakeSemaphore:
    def __init__(self, acquire_result=True, release_error=False):
        self.acquire_result = acquire_result
        self.release_error = release_error
        self.acquire_calls = []
        self.release_calls = 0

    def acquire(self, timeout=None):
        self.acquire_calls.append(timeout)
        return self.acquire_result

    def release(self):
        self.release_calls += 1
        if self.release_error:
            raise ValueError("released too many times")


def _reset_registration_queue_state(monkeypatch):
    from app.bot.user_bot import user_bot_service

    monkeypatch.setattr(user_bot_service, "_active_tasks_lock", threading.RLock())
    monkeypatch.setattr(user_bot_service, "_waiting_count_lock", threading.RLock())
    monkeypatch.setattr(user_bot_service, "_active_tasks", 0)
    monkeypatch.setattr(user_bot_service, "_waiting_count", 0)
    monkeypatch.setattr(user_bot_service, "MAX_CONCURRENT_TASKS", 3)
    monkeypatch.setattr(user_bot_service, "MAX_WAITING_TASKS", 2)
    monkeypatch.setattr(user_bot_service, "_task_executor", FakeExecutor())
    monkeypatch.setattr(user_bot_service, "_reg_waiters_lock", threading.RLock())
    monkeypatch.setattr(user_bot_service, "_reg_waiters", 0)
    monkeypatch.setattr(user_bot_service, "_reg_active", 0)
    monkeypatch.setattr(user_bot_service, "MAX_CONCURRENT_REG", 2)
    monkeypatch.setattr(user_bot_service, "REG_QUEUE_MAX_WAIT", 6)
    monkeypatch.setattr(user_bot_service, "_reg_sema", FakeSemaphore())
    monkeypatch.setattr(user_bot_service, "logger", FakeLogger())
    return user_bot_service


def test_submit_task_uses_legacy_executor_and_counters(monkeypatch):
    user_bot_service = _reset_registration_queue_state(monkeypatch)
    calls = []

    assert user_bot_service._submit_task(lambda value, flag=False: calls.append((value, flag)), "x", flag=True) is True
    assert user_bot_service._waiting_count == 1
    assert user_bot_service._active_tasks == 0
    assert len(user_bot_service._task_executor.submitted) == 1

    user_bot_service._task_executor.submitted[0]()

    assert calls == [("x", True)]
    assert user_bot_service._waiting_count == 0
    assert user_bot_service._active_tasks == 0


def test_submit_task_rejects_when_legacy_waiting_limit_is_full(monkeypatch):
    user_bot_service = _reset_registration_queue_state(monkeypatch)
    user_bot_service._waiting_count = 2

    assert user_bot_service._submit_task(lambda: None) is False
    assert user_bot_service._waiting_count == 2
    assert user_bot_service._task_executor.submitted == []


def test_get_queue_status_reads_legacy_state_and_limits(monkeypatch):
    user_bot_service = _reset_registration_queue_state(monkeypatch)
    user_bot_service._active_tasks = 1
    user_bot_service._waiting_count = 2

    assert user_bot_service._get_queue_status() == {
        "active": 1,
        "waiting": 2,
        "max_active": 3,
        "max_waiting": 2,
    }


def test_enter_reg_queue_updates_legacy_state_and_sends_position(monkeypatch):
    user_bot_service = _reset_registration_queue_state(monkeypatch)
    sent = []
    sema = FakeSemaphore(acquire_result=True)

    user_bot_service._reg_active = 2
    monkeypatch.setattr(user_bot_service, "_reg_sema", sema)
    monkeypatch.setattr(user_bot_service, "_send", lambda chat_id, text, reply_markup=None: sent.append((chat_id, text)))

    assert user_bot_service._enter_reg_queue(chat_id=123) is True

    assert user_bot_service._reg_waiters == 0
    assert user_bot_service._reg_active == 3
    assert sema.acquire_calls == [6]
    assert sent == [(123, "⏳ 当前注册人数较多，你排在第 1 位，请稍候（最长等待 0 分钟）...")]


def test_enter_reg_queue_timeout_sends_legacy_timeout_message(monkeypatch):
    user_bot_service = _reset_registration_queue_state(monkeypatch)
    sent = []
    sema = FakeSemaphore(acquire_result=False)

    monkeypatch.setattr(user_bot_service, "_reg_sema", sema)
    monkeypatch.setattr(user_bot_service, "_send", lambda chat_id, text, reply_markup=None: sent.append((chat_id, text)))

    assert user_bot_service._enter_reg_queue(chat_id=456) is False

    assert user_bot_service._reg_waiters == 0
    assert user_bot_service._reg_active == 0
    assert sema.acquire_calls == [6]
    assert sent == [(456, "⌛ 注册排队等待超时，请稍后重试")]


def test_leave_reg_queue_updates_legacy_state_and_logs_release_error(monkeypatch):
    user_bot_service = _reset_registration_queue_state(monkeypatch)
    sema = FakeSemaphore(release_error=True)

    user_bot_service._reg_active = 1
    monkeypatch.setattr(user_bot_service, "_reg_sema", sema)

    user_bot_service._leave_reg_queue()

    assert user_bot_service._reg_active == 0
    assert sema.release_calls == 1
    assert user_bot_service.logger.calls == [("exception", "[UserBot] _reg_sema release 异常")]
