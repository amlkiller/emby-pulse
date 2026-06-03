import logging
import threading
import time

from app.infra.clients.media_server_client import media_api
from app.infra.config.user_bot_settings import (
    get_user_bot_registration_batch_used,
    set_user_bot_open_reg_enabled,
    set_user_bot_registration_batch_used,
)
from app.infra.config.user_visibility_settings import get_hidden_users


logger = logging.getLogger("uvicorn")

USER_COUNT_CACHE_TTL = 30
USER_COUNT_NEAR_LIMIT_MARGIN = 3
BATCH_FLUSH_INTERVAL = 10
BATCH_FLUSH_THRESHOLD = 5

_quota_lock = threading.Lock()
_quota_reserved = 0
_user_count_cache = {"count": None, "users": None, "ts": 0.0}
_batch_used_lock = threading.Lock()
_batch_used_mem = None
_batch_used_dirty = 0
_batch_flush_stop = threading.Event()
_batch_flush_thread = None

_media_api_provider = lambda: media_api
_get_hidden_users_provider = lambda: get_hidden_users
_get_registration_batch_used_provider = lambda: get_user_bot_registration_batch_used
_set_registration_batch_used_provider = lambda: set_user_bot_registration_batch_used
_set_open_reg_enabled_provider = lambda: set_user_bot_open_reg_enabled
_send_open_reg_closed_notify_provider = lambda: (lambda reason="": None)
_logger_provider = lambda: logger
_time_provider = lambda: time
_threading_provider = lambda: threading
_quota_lock_provider = lambda: _quota_lock
_get_quota_reserved_provider = lambda: _quota_reserved
_set_quota_reserved_callback = None
_user_count_cache_provider = lambda: _user_count_cache
_batch_used_lock_provider = lambda: _batch_used_lock
_get_batch_used_mem_provider = lambda: _batch_used_mem
_set_batch_used_mem_callback = None
_get_batch_used_dirty_provider = lambda: _batch_used_dirty
_set_batch_used_dirty_callback = None
_batch_flush_stop_provider = lambda: _batch_flush_stop
_get_batch_flush_thread_provider = lambda: _batch_flush_thread
_set_batch_flush_thread_callback = None
_user_count_cache_ttl_provider = lambda: USER_COUNT_CACHE_TTL
_user_count_near_limit_margin_provider = lambda: USER_COUNT_NEAR_LIMIT_MARGIN
_batch_flush_interval_provider = lambda: BATCH_FLUSH_INTERVAL
_batch_flush_threshold_provider = lambda: BATCH_FLUSH_THRESHOLD


def _set_local_quota_reserved(value):
    global _quota_reserved
    _quota_reserved = value


def _set_local_batch_used_mem(value):
    global _batch_used_mem
    _batch_used_mem = value


def _set_local_batch_used_dirty(value):
    global _batch_used_dirty
    _batch_used_dirty = value


def _set_local_batch_flush_thread(value):
    global _batch_flush_thread
    _batch_flush_thread = value


def set_dependency_providers(
    *,
    media_api_provider=None,
    get_hidden_users_provider=None,
    get_registration_batch_used_provider=None,
    set_registration_batch_used_provider=None,
    set_open_reg_enabled_provider=None,
    send_open_reg_closed_notify_provider=None,
    logger_provider=None,
    time_provider=None,
    threading_provider=None,
    quota_lock_provider=None,
    get_quota_reserved_provider=None,
    set_quota_reserved_callback=None,
    user_count_cache_provider=None,
    batch_used_lock_provider=None,
    get_batch_used_mem_provider=None,
    set_batch_used_mem_callback=None,
    get_batch_used_dirty_provider=None,
    set_batch_used_dirty_callback=None,
    batch_flush_stop_provider=None,
    get_batch_flush_thread_provider=None,
    set_batch_flush_thread_callback=None,
    user_count_cache_ttl_provider=None,
    user_count_near_limit_margin_provider=None,
    batch_flush_interval_provider=None,
    batch_flush_threshold_provider=None,
):
    global _media_api_provider
    global _get_hidden_users_provider
    global _get_registration_batch_used_provider
    global _set_registration_batch_used_provider
    global _set_open_reg_enabled_provider
    global _send_open_reg_closed_notify_provider
    global _logger_provider
    global _time_provider
    global _threading_provider
    global _quota_lock_provider
    global _get_quota_reserved_provider
    global _set_quota_reserved_callback
    global _user_count_cache_provider
    global _batch_used_lock_provider
    global _get_batch_used_mem_provider
    global _set_batch_used_mem_callback
    global _get_batch_used_dirty_provider
    global _set_batch_used_dirty_callback
    global _batch_flush_stop_provider
    global _get_batch_flush_thread_provider
    global _set_batch_flush_thread_callback
    global _user_count_cache_ttl_provider
    global _user_count_near_limit_margin_provider
    global _batch_flush_interval_provider
    global _batch_flush_threshold_provider

    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if get_hidden_users_provider is not None:
        _get_hidden_users_provider = get_hidden_users_provider
    if get_registration_batch_used_provider is not None:
        _get_registration_batch_used_provider = get_registration_batch_used_provider
    if set_registration_batch_used_provider is not None:
        _set_registration_batch_used_provider = set_registration_batch_used_provider
    if set_open_reg_enabled_provider is not None:
        _set_open_reg_enabled_provider = set_open_reg_enabled_provider
    if send_open_reg_closed_notify_provider is not None:
        _send_open_reg_closed_notify_provider = send_open_reg_closed_notify_provider
    if logger_provider is not None:
        _logger_provider = logger_provider
    if time_provider is not None:
        _time_provider = time_provider
    if threading_provider is not None:
        _threading_provider = threading_provider
    if quota_lock_provider is not None:
        _quota_lock_provider = quota_lock_provider
    if get_quota_reserved_provider is not None:
        _get_quota_reserved_provider = get_quota_reserved_provider
    if set_quota_reserved_callback is not None:
        _set_quota_reserved_callback = set_quota_reserved_callback
    if user_count_cache_provider is not None:
        _user_count_cache_provider = user_count_cache_provider
    if batch_used_lock_provider is not None:
        _batch_used_lock_provider = batch_used_lock_provider
    if get_batch_used_mem_provider is not None:
        _get_batch_used_mem_provider = get_batch_used_mem_provider
    if set_batch_used_mem_callback is not None:
        _set_batch_used_mem_callback = set_batch_used_mem_callback
    if get_batch_used_dirty_provider is not None:
        _get_batch_used_dirty_provider = get_batch_used_dirty_provider
    if set_batch_used_dirty_callback is not None:
        _set_batch_used_dirty_callback = set_batch_used_dirty_callback
    if batch_flush_stop_provider is not None:
        _batch_flush_stop_provider = batch_flush_stop_provider
    if get_batch_flush_thread_provider is not None:
        _get_batch_flush_thread_provider = get_batch_flush_thread_provider
    if set_batch_flush_thread_callback is not None:
        _set_batch_flush_thread_callback = set_batch_flush_thread_callback
    if user_count_cache_ttl_provider is not None:
        _user_count_cache_ttl_provider = user_count_cache_ttl_provider
    if user_count_near_limit_margin_provider is not None:
        _user_count_near_limit_margin_provider = user_count_near_limit_margin_provider
    if batch_flush_interval_provider is not None:
        _batch_flush_interval_provider = batch_flush_interval_provider
    if batch_flush_threshold_provider is not None:
        _batch_flush_threshold_provider = batch_flush_threshold_provider


def _set_quota_reserved(value):
    setter = _set_quota_reserved_callback or _set_local_quota_reserved
    setter(value)


def _set_batch_used_mem(value):
    setter = _set_batch_used_mem_callback or _set_local_batch_used_mem
    setter(value)


def _set_batch_used_dirty(value):
    setter = _set_batch_used_dirty_callback or _set_local_batch_used_dirty
    setter(value)


def _set_batch_flush_thread(value):
    setter = _set_batch_flush_thread_callback or _set_local_batch_flush_thread
    setter(value)


def load_batch_used_from_cfg():
    """从 cfg.json 加载 batch_used 到内存，幂等"""
    with _batch_used_lock_provider():
        if _get_batch_used_mem_provider() is None:
            try:
                batch_used = int(_get_registration_batch_used_provider()() or 0)
            except Exception:
                batch_used = 0
            _set_batch_used_mem(batch_used)
            _set_batch_used_dirty(0)


def flush_batch_used(force=False):
    """把内存中的 batch_used 落盘到 cfg.json"""
    with _batch_used_lock_provider():
        batch_used = _get_batch_used_mem_provider()
        if batch_used is None:
            return
        if not force and _get_batch_used_dirty_provider() == 0:
            return
        try:
            _set_registration_batch_used_provider()(batch_used)
            _set_batch_used_dirty(0)
        except Exception:
            _logger_provider().exception("[UserBot] batch_used 落盘失败")


def batch_flush_loop():
    """后台线程：周期性把 _batch_used_mem flush 到 cfg.json"""
    batch_flush_stop = _batch_flush_stop_provider()
    while not batch_flush_stop.is_set():
        try:
            if batch_flush_stop.wait(_batch_flush_interval_provider()):
                break
            flush_batch_used()
        except Exception:
            _logger_provider().exception("[UserBot] batch_used flush 循环异常")
            if batch_flush_stop.wait(5):
                break


def start_batch_flush_thread(loop_target=None):
    """启动后台 flush 线程（幂等）"""
    batch_flush_stop = _batch_flush_stop_provider()
    batch_flush_stop.clear()
    thread = _get_batch_flush_thread_provider()
    if thread is not None and thread.is_alive():
        return
    target = loop_target or batch_flush_loop
    thread = _threading_provider().Thread(target=target, daemon=True, name="batch-flush")
    _set_batch_flush_thread(thread)
    thread.start()


def stop_batch_flush_thread():
    """停止后台 flush 线程并清理已停止的句柄"""
    _batch_flush_stop_provider().set()
    thread = _get_batch_flush_thread_provider()
    if thread and thread.is_alive():
        thread.join(timeout=1)
    if not thread or not thread.is_alive():
        _set_batch_flush_thread(None)


def get_batch_used_snapshot():
    """对外暴露的 batch_used 当前值，供 API 读取（避免 cfg.json 滞后）"""
    with _batch_used_lock_provider():
        batch_used = _get_batch_used_mem_provider()
        if batch_used is not None:
            return batch_used
    return _get_registration_batch_used_provider()()


def refresh_user_count_cache_locked(force=False, quota=0):
    """在 _quota_lock 持有的前提下刷新缓存。返回 count 或 None。"""
    now = _time_provider().time()
    user_count_cache = _user_count_cache_provider()
    cached = user_count_cache.get("count")
    cached_ts = user_count_cache.get("ts", 0.0)
    fresh = (cached is not None) and (now - cached_ts < _user_count_cache_ttl_provider())
    near_limit = (
        quota > 0 and cached is not None
        and cached >= max(0, quota - _user_count_near_limit_margin_provider())
    )
    if fresh and not force and not near_limit:
        return cached
    try:
        users = _media_api_provider().get("/Users", timeout=5).json()
        hidden_users = _get_hidden_users_provider()()
        normal_users = [
            u for u in users
            if u.get("Name") not in hidden_users
            and not u.get("Policy", {}).get("IsAdministrator")
        ]
        user_count_cache["count"] = len(normal_users)
        user_count_cache["users"] = users
        user_count_cache["ts"] = now
        return user_count_cache["count"]
    except Exception as e:
        _logger_provider().warning(f"[UserBot] 刷新 Emby 用户数失败: {e}")
        return cached


def invalidate_user_count_cache():
    with _quota_lock_provider():
        _user_count_cache_provider()["ts"] = 0.0


def get_cached_user_count_for_api(force=False):
    """供 /api/bot/reg_quota_status 读取的入口"""
    with _quota_lock_provider():
        cnt = refresh_user_count_cache_locked(force=force)
    return cnt if cnt is not None else 0


def get_users_list_cached(max_age=None):
    """获取缓存的 Emby 用户列表（用于重名检查）。缓存失效时现拉。"""
    if max_age is None:
        max_age = _user_count_cache_ttl_provider()
    with _quota_lock_provider():
        user_count_cache = _user_count_cache_provider()
        users = user_count_cache.get("users")
        ts = user_count_cache.get("ts", 0.0)
        if users is not None and _time_provider().time() - ts < max_age:
            return users
    with _quota_lock_provider():
        refresh_user_count_cache_locked(force=True)
        return _user_count_cache_provider().get("users")


def reserve_quota_slot(quota_mode, quota):
    """软预占一个 quota 槽。成功返回 (True, None)，失败返回 (False, reason)。"""
    if quota <= 0:
        return True, None
    with _quota_lock_provider():
        quota_reserved = _get_quota_reserved_provider()
        if quota_mode == "batch":
            load_batch_used_from_cfg()
            used = _get_batch_used_mem_provider() or 0
            if used + quota_reserved >= quota:
                return False, "batch_full"
            _set_quota_reserved(quota_reserved + 1)
            return True, None
        cnt = refresh_user_count_cache_locked(quota=quota)
        if cnt is None:
            if quota_reserved > 0:
                return False, "emby_unreachable"
            _set_quota_reserved(quota_reserved + 1)
            return True, None
        if cnt + quota_reserved >= quota:
            cnt2 = refresh_user_count_cache_locked(force=True, quota=quota)
            if cnt2 is not None and cnt2 + quota_reserved >= quota:
                return False, "total_full"
        _set_quota_reserved(quota_reserved + 1)
        return True, None


def release_quota_slot(committed, quota_mode, quota):
    """释放软预占。committed=True 表示注册真的成功了。"""
    with _quota_lock_provider():
        quota_reserved = _get_quota_reserved_provider()
        if quota_reserved > 0:
            _set_quota_reserved(quota_reserved - 1)
    if not committed:
        return
    if quota_mode == "batch":
        inc_batch_used(quota)
    else:
        invalidate_user_count_cache()
        if quota > 0:
            with _quota_lock_provider():
                cnt = refresh_user_count_cache_locked(force=True, quota=quota)
            if cnt is not None and cnt >= quota:
                try:
                    _set_open_reg_enabled_provider()(False)
                    _logger_provider().info(f"[UserBot] 用户总数已达上限({cnt}/{quota})，开放注册已自动关闭")
                    _send_open_reg_closed_notify_provider()("用户总数已达上限")
                except Exception:
                    _logger_provider().exception("[UserBot] 关闭开放注册失败")


def inc_batch_used(quota):
    """batch 模式：注册成功后递增 batch_used。达 quota 立即落盘并关注册。"""
    closed_now = False
    batch_used = None
    with _batch_used_lock_provider():
        batch_used = _get_batch_used_mem_provider()
        if batch_used is None:
            try:
                batch_used = int(_get_registration_batch_used_provider()() or 0)
            except Exception:
                batch_used = 0
            _set_batch_used_mem(batch_used)
            _set_batch_used_dirty(0)
        batch_used += 1
        batch_used_dirty = _get_batch_used_dirty_provider() + 1
        _set_batch_used_mem(batch_used)
        _set_batch_used_dirty(batch_used_dirty)
        should_flush = batch_used_dirty >= _batch_flush_threshold_provider()
        if quota > 0 and batch_used >= quota:
            closed_now = True
            should_flush = True
        if should_flush:
            try:
                _set_registration_batch_used_provider()(batch_used)
                _set_batch_used_dirty(0)
            except Exception:
                _logger_provider().exception("[UserBot] batch_used 落盘失败")
    if closed_now:
        try:
            _set_open_reg_enabled_provider()(False)
            _logger_provider().info(f"[UserBot] 批次注册名额已用完({batch_used}/{quota})，开放注册已自动关闭")
            _send_open_reg_closed_notify_provider()("批次名额已满")
        except Exception:
            _logger_provider().exception("[UserBot] 关闭开放注册失败")
