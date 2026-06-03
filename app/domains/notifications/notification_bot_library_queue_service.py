import logging

from app.infra.config.bot_settings import get_library_notify_queue_max


logger = logging.getLogger("uvicorn")

_library_notify_queue_max_provider = lambda: get_library_notify_queue_max
_logger_provider = lambda: logger


def set_dependency_providers(
    *,
    library_notify_queue_max_provider=None,
    logger_provider=None,
):
    global _library_notify_queue_max_provider
    global _logger_provider

    if library_notify_queue_max_provider is not None:
        _library_notify_queue_max_provider = library_notify_queue_max_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def add_library_task(daemon, item):
    with daemon.library_lock:
        max_queue = 300
        max_queue = _library_notify_queue_max_provider()()
        if len(daemon.library_queue) >= max_queue:
            dropped = daemon.library_queue.pop(0)
            _logger_provider().warning(f"[入库通知] 队列已满，丢弃最旧项目: {dropped.get('Name') or dropped.get('Id')}")
        if not any(x.get("Id") == item.get("Id") for x in daemon.library_queue):
            daemon.library_queue.append(item)
