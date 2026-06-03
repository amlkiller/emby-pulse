import logging
import threading
import time
from collections import defaultdict


logger = logging.getLogger("uvicorn")

USERNAME_LOCK_MAX_SIZE = 1000

_rate_limit = defaultdict(float)
_username_locks = {}
_username_locks_lock = threading.Lock()

_rate_limit_provider = lambda: _rate_limit
_username_locks_provider = lambda: _username_locks
_username_locks_lock_provider = lambda: _username_locks_lock
_username_lock_max_size_provider = lambda: USERNAME_LOCK_MAX_SIZE
_threading_provider = lambda: threading
_time_provider = lambda: time
_logger_provider = lambda: logger


def set_dependency_providers(
    *,
    rate_limit_provider=None,
    username_locks_provider=None,
    username_locks_lock_provider=None,
    username_lock_max_size_provider=None,
    threading_provider=None,
    time_provider=None,
    logger_provider=None,
):
    global _rate_limit_provider
    global _username_locks_provider
    global _username_locks_lock_provider
    global _username_lock_max_size_provider
    global _threading_provider
    global _time_provider
    global _logger_provider

    if rate_limit_provider is not None:
        _rate_limit_provider = rate_limit_provider
    if username_locks_provider is not None:
        _username_locks_provider = username_locks_provider
    if username_locks_lock_provider is not None:
        _username_locks_lock_provider = username_locks_lock_provider
    if username_lock_max_size_provider is not None:
        _username_lock_max_size_provider = username_lock_max_size_provider
    if threading_provider is not None:
        _threading_provider = threading_provider
    if time_provider is not None:
        _time_provider = time_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def rate_check(tg_user_id, cooldown=3):
    rate_limit = _rate_limit_provider()
    now = _time_provider().time()
    if now - rate_limit[tg_user_id] < cooldown:
        return False
    rate_limit[tg_user_id] = now
    return True


def get_username_lock(username_lower):
    """获取用户名锁（防止并发注册时用户名冲突），带清理机制"""
    with _username_locks_lock_provider():
        username_locks = _username_locks_provider()
        max_size = _username_lock_max_size_provider()
        if len(username_locks) > max_size:
            keys_to_remove = list(username_locks.keys())[:max_size // 2]
            for key in keys_to_remove:
                del username_locks[key]
            _logger_provider().info(f"[UserBot] 清理用户名锁，移除 {len(keys_to_remove)} 个")

        if username_lower not in username_locks:
            username_locks[username_lower] = _threading_provider().Lock()
        return username_locks[username_lower]
