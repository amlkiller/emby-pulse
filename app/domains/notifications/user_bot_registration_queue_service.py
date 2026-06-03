import logging
import threading
from concurrent.futures import ThreadPoolExecutor


logger = logging.getLogger("uvicorn")

MAX_CONCURRENT_TASKS = 4
MAX_WAITING_TASKS = 200
MAX_CONCURRENT_REG = 20
REG_QUEUE_MAX_WAIT = 180

_task_executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_TASKS, thread_name_prefix="userbot")
_active_tasks = 0
_active_tasks_lock = threading.Lock()
_waiting_count = 0
_waiting_count_lock = threading.Lock()
_reg_sema = threading.BoundedSemaphore(MAX_CONCURRENT_REG)
_reg_waiters_lock = threading.Lock()
_reg_waiters = 0
_reg_active = 0

_task_executor_provider = lambda: _task_executor
_active_tasks_lock_provider = lambda: _active_tasks_lock
_waiting_count_lock_provider = lambda: _waiting_count_lock
_get_active_tasks_provider = lambda: _active_tasks
_set_active_tasks_callback = None
_get_waiting_count_provider = lambda: _waiting_count
_set_waiting_count_callback = None
_max_concurrent_tasks_provider = lambda: MAX_CONCURRENT_TASKS
_max_waiting_tasks_provider = lambda: MAX_WAITING_TASKS
_reg_sema_provider = lambda: _reg_sema
_reg_waiters_lock_provider = lambda: _reg_waiters_lock
_get_reg_waiters_provider = lambda: _reg_waiters
_set_reg_waiters_callback = None
_get_reg_active_provider = lambda: _reg_active
_set_reg_active_callback = None
_max_concurrent_reg_provider = lambda: MAX_CONCURRENT_REG
_reg_queue_max_wait_provider = lambda: REG_QUEUE_MAX_WAIT
_send_provider = lambda: (lambda chat_id, text, reply_markup=None: None)
_logger_provider = lambda: logger


def _set_local_active_tasks(value):
    global _active_tasks
    _active_tasks = value


def _set_local_waiting_count(value):
    global _waiting_count
    _waiting_count = value


def _set_local_reg_waiters(value):
    global _reg_waiters
    _reg_waiters = value


def _set_local_reg_active(value):
    global _reg_active
    _reg_active = value


def set_dependency_providers(
    *,
    task_executor_provider=None,
    active_tasks_lock_provider=None,
    waiting_count_lock_provider=None,
    get_active_tasks_provider=None,
    set_active_tasks_callback=None,
    get_waiting_count_provider=None,
    set_waiting_count_callback=None,
    max_concurrent_tasks_provider=None,
    max_waiting_tasks_provider=None,
    reg_sema_provider=None,
    reg_waiters_lock_provider=None,
    get_reg_waiters_provider=None,
    set_reg_waiters_callback=None,
    get_reg_active_provider=None,
    set_reg_active_callback=None,
    max_concurrent_reg_provider=None,
    reg_queue_max_wait_provider=None,
    send_provider=None,
    logger_provider=None,
):
    global _task_executor_provider
    global _active_tasks_lock_provider
    global _waiting_count_lock_provider
    global _get_active_tasks_provider
    global _set_active_tasks_callback
    global _get_waiting_count_provider
    global _set_waiting_count_callback
    global _max_concurrent_tasks_provider
    global _max_waiting_tasks_provider
    global _reg_sema_provider
    global _reg_waiters_lock_provider
    global _get_reg_waiters_provider
    global _set_reg_waiters_callback
    global _get_reg_active_provider
    global _set_reg_active_callback
    global _max_concurrent_reg_provider
    global _reg_queue_max_wait_provider
    global _send_provider
    global _logger_provider

    if task_executor_provider is not None:
        _task_executor_provider = task_executor_provider
    if active_tasks_lock_provider is not None:
        _active_tasks_lock_provider = active_tasks_lock_provider
    if waiting_count_lock_provider is not None:
        _waiting_count_lock_provider = waiting_count_lock_provider
    if get_active_tasks_provider is not None:
        _get_active_tasks_provider = get_active_tasks_provider
    if set_active_tasks_callback is not None:
        _set_active_tasks_callback = set_active_tasks_callback
    if get_waiting_count_provider is not None:
        _get_waiting_count_provider = get_waiting_count_provider
    if set_waiting_count_callback is not None:
        _set_waiting_count_callback = set_waiting_count_callback
    if max_concurrent_tasks_provider is not None:
        _max_concurrent_tasks_provider = max_concurrent_tasks_provider
    if max_waiting_tasks_provider is not None:
        _max_waiting_tasks_provider = max_waiting_tasks_provider
    if reg_sema_provider is not None:
        _reg_sema_provider = reg_sema_provider
    if reg_waiters_lock_provider is not None:
        _reg_waiters_lock_provider = reg_waiters_lock_provider
    if get_reg_waiters_provider is not None:
        _get_reg_waiters_provider = get_reg_waiters_provider
    if set_reg_waiters_callback is not None:
        _set_reg_waiters_callback = set_reg_waiters_callback
    if get_reg_active_provider is not None:
        _get_reg_active_provider = get_reg_active_provider
    if set_reg_active_callback is not None:
        _set_reg_active_callback = set_reg_active_callback
    if max_concurrent_reg_provider is not None:
        _max_concurrent_reg_provider = max_concurrent_reg_provider
    if reg_queue_max_wait_provider is not None:
        _reg_queue_max_wait_provider = reg_queue_max_wait_provider
    if send_provider is not None:
        _send_provider = send_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def _set_active_tasks(value):
    setter = _set_active_tasks_callback or _set_local_active_tasks
    setter(value)


def _set_waiting_count(value):
    setter = _set_waiting_count_callback or _set_local_waiting_count
    setter(value)


def _set_reg_waiters(value):
    setter = _set_reg_waiters_callback or _set_local_reg_waiters
    setter(value)


def _set_reg_active(value):
    setter = _set_reg_active_callback or _set_local_reg_active
    setter(value)


def submit_task(func, *args, **kwargs):
    """提交任务到线程池，支持排队"""
    with _waiting_count_lock_provider():
        waiting_count = _get_waiting_count_provider()
        if waiting_count >= _max_waiting_tasks_provider():
            return False
        _set_waiting_count(waiting_count + 1)

    def wrapper():
        with _waiting_count_lock_provider():
            _set_waiting_count(_get_waiting_count_provider() - 1)
        with _active_tasks_lock_provider():
            _set_active_tasks(_get_active_tasks_provider() + 1)

        try:
            func(*args, **kwargs)
        finally:
            with _active_tasks_lock_provider():
                _set_active_tasks(_get_active_tasks_provider() - 1)

    _task_executor_provider().submit(wrapper)
    return True


def get_queue_status():
    """获取当前队列状态"""
    with _active_tasks_lock_provider():
        with _waiting_count_lock_provider():
            return {
                "active": _get_active_tasks_provider(),
                "waiting": _get_waiting_count_provider(),
                "max_active": _max_concurrent_tasks_provider(),
                "max_waiting": _max_waiting_tasks_provider(),
            }


def enter_reg_queue(chat_id):
    """进入注册队列。超出并发上限时阻塞排队并发送位置提示，超时返回 False。"""
    with _reg_waiters_lock_provider():
        reg_waiters = _get_reg_waiters_provider() + 1
        _set_reg_waiters(reg_waiters)
        pos = reg_waiters
        active = _get_reg_active_provider()
    if active >= _max_concurrent_reg_provider():
        _send_provider()(
            chat_id,
            f"⏳ 当前注册人数较多，你排在第 {pos} 位，请稍候（最长等待 {_reg_queue_max_wait_provider() // 60} 分钟）...",
        )
    got = _reg_sema_provider().acquire(timeout=_reg_queue_max_wait_provider())
    with _reg_waiters_lock_provider():
        _set_reg_waiters(_get_reg_waiters_provider() - 1)
        if got:
            _set_reg_active(_get_reg_active_provider() + 1)
    if not got:
        _send_provider()(chat_id, "⌛ 注册排队等待超时，请稍后重试")
        return False
    return True


def leave_reg_queue():
    """离开注册队列，释放信号量。"""
    with _reg_waiters_lock_provider():
        _set_reg_active(max(0, _get_reg_active_provider() - 1))
    try:
        _reg_sema_provider().release()
    except ValueError:
        _logger_provider().exception("[UserBot] _reg_sema release 异常")
