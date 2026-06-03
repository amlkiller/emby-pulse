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
    from app.bot.user_bot import user_bot_registration_queue_service

    monkeypatch.setattr(user_bot_registration_queue_service, "_active_tasks_lock", threading.RLock())
    monkeypatch.setattr(user_bot_registration_queue_service, "_waiting_count_lock", threading.RLock())
    monkeypatch.setattr(user_bot_registration_queue_service, "_active_tasks", 0)
    monkeypatch.setattr(user_bot_registration_queue_service, "_waiting_count", 0)
    monkeypatch.setattr(user_bot_registration_queue_service, "MAX_CONCURRENT_TASKS", 3)
    monkeypatch.setattr(user_bot_registration_queue_service, "MAX_WAITING_TASKS", 2)
    monkeypatch.setattr(user_bot_registration_queue_service, "_task_executor", FakeExecutor())
    monkeypatch.setattr(user_bot_registration_queue_service, "_reg_waiters_lock", threading.RLock())
    monkeypatch.setattr(user_bot_registration_queue_service, "_reg_waiters", 0)
    monkeypatch.setattr(user_bot_registration_queue_service, "_reg_active", 0)
    monkeypatch.setattr(user_bot_registration_queue_service, "MAX_CONCURRENT_REG", 2)
    monkeypatch.setattr(user_bot_registration_queue_service, "REG_QUEUE_MAX_WAIT", 6)
    monkeypatch.setattr(user_bot_registration_queue_service, "_reg_sema", FakeSemaphore())
    monkeypatch.setattr(user_bot_registration_queue_service, "logger", FakeLogger())
    user_bot_registration_queue_service.set_dependency_providers(
        task_executor_provider=lambda: user_bot_registration_queue_service._task_executor,
        active_tasks_lock_provider=lambda: user_bot_registration_queue_service._active_tasks_lock,
        waiting_count_lock_provider=lambda: user_bot_registration_queue_service._waiting_count_lock,
        get_active_tasks_provider=lambda: user_bot_registration_queue_service._active_tasks,
        set_active_tasks_callback=None,
        get_waiting_count_provider=lambda: user_bot_registration_queue_service._waiting_count,
        set_waiting_count_callback=None,
        max_concurrent_tasks_provider=lambda: user_bot_registration_queue_service.MAX_CONCURRENT_TASKS,
        max_waiting_tasks_provider=lambda: user_bot_registration_queue_service.MAX_WAITING_TASKS,
        reg_sema_provider=lambda: user_bot_registration_queue_service._reg_sema,
        reg_waiters_lock_provider=lambda: user_bot_registration_queue_service._reg_waiters_lock,
        get_reg_waiters_provider=lambda: user_bot_registration_queue_service._reg_waiters,
        set_reg_waiters_callback=None,
        get_reg_active_provider=lambda: user_bot_registration_queue_service._reg_active,
        set_reg_active_callback=None,
        max_concurrent_reg_provider=lambda: user_bot_registration_queue_service.MAX_CONCURRENT_REG,
        reg_queue_max_wait_provider=lambda: user_bot_registration_queue_service.REG_QUEUE_MAX_WAIT,
        send_provider=lambda: (lambda chat_id, text, reply_markup=None: None),
        logger_provider=lambda: user_bot_registration_queue_service.logger,
    )
    return user_bot_registration_queue_service


def test_submit_task_uses_legacy_executor_and_counters(monkeypatch):
    queue_service = _reset_registration_queue_state(monkeypatch)
    calls = []

    assert queue_service.submit_task(lambda value, flag=False: calls.append((value, flag)), "x", flag=True) is True
    assert queue_service._waiting_count == 1
    assert queue_service._active_tasks == 0
    assert len(queue_service._task_executor.submitted) == 1

    queue_service._task_executor.submitted[0]()

    assert calls == [("x", True)]
    assert queue_service._waiting_count == 0
    assert queue_service._active_tasks == 0


def test_submit_task_rejects_when_legacy_waiting_limit_is_full(monkeypatch):
    queue_service = _reset_registration_queue_state(monkeypatch)
    queue_service._waiting_count = 2

    assert queue_service.submit_task(lambda: None) is False
    assert queue_service._waiting_count == 2
    assert queue_service._task_executor.submitted == []


def test_get_queue_status_reads_legacy_state_and_limits(monkeypatch):
    queue_service = _reset_registration_queue_state(monkeypatch)
    queue_service._active_tasks = 1
    queue_service._waiting_count = 2

    assert queue_service.get_queue_status() == {
        "active": 1,
        "waiting": 2,
        "max_active": 3,
        "max_waiting": 2,
    }


def test_enter_reg_queue_updates_legacy_state_and_sends_position(monkeypatch):
    queue_service = _reset_registration_queue_state(monkeypatch)
    sent = []
    sema = FakeSemaphore(acquire_result=True)

    queue_service._reg_active = 2
    monkeypatch.setattr(queue_service, "_reg_sema", sema)
    queue_service.set_dependency_providers(
        reg_sema_provider=lambda: queue_service._reg_sema,
        send_provider=lambda: (lambda chat_id, text, reply_markup=None: sent.append((chat_id, text))),
    )

    assert queue_service.enter_reg_queue(chat_id=123) is True

    assert queue_service._reg_waiters == 0
    assert queue_service._reg_active == 3
    assert sema.acquire_calls == [6]
    assert sent == [(123, "⏳ 当前注册人数较多，你排在第 1 位，请稍候（最长等待 0 分钟）...")]


def test_enter_reg_queue_timeout_sends_legacy_timeout_message(monkeypatch):
    queue_service = _reset_registration_queue_state(monkeypatch)
    sent = []
    sema = FakeSemaphore(acquire_result=False)

    monkeypatch.setattr(queue_service, "_reg_sema", sema)
    queue_service.set_dependency_providers(
        reg_sema_provider=lambda: queue_service._reg_sema,
        send_provider=lambda: (lambda chat_id, text, reply_markup=None: sent.append((chat_id, text))),
    )

    assert queue_service.enter_reg_queue(chat_id=456) is False

    assert queue_service._reg_waiters == 0
    assert queue_service._reg_active == 0
    assert sema.acquire_calls == [6]
    assert sent == [(456, "⌛ 注册排队等待超时，请稍后重试")]


def test_leave_reg_queue_updates_legacy_state_and_logs_release_error(monkeypatch):
    queue_service = _reset_registration_queue_state(monkeypatch)
    sema = FakeSemaphore(release_error=True)

    queue_service._reg_active = 1
    monkeypatch.setattr(queue_service, "_reg_sema", sema)
    queue_service.set_dependency_providers(reg_sema_provider=lambda: queue_service._reg_sema)

    queue_service.leave_reg_queue()

    assert queue_service._reg_active == 0
    assert sema.release_calls == 1
    assert queue_service.logger.calls == [("exception", "[UserBot] _reg_sema release 异常")]
