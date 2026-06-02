# app/core/event_bus.py
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import logging

logger = logging.getLogger("uvicorn")

class EventBus:
    def __init__(self):
        self.subscribers = defaultdict(list)
        self.lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="event_bus")

    def subscribe(self, event_type: str, handler):
        with self.lock:
            if handler not in self.subscribers[event_type]:
                self.subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler):
        with self.lock:
            handlers = self.subscribers.get(event_type)
            if not handlers or handler not in handlers:
                return
            handlers.remove(handler)
            if not handlers:
                self.subscribers.pop(event_type, None)

    def publish(self, event_type: str, *args, **kwargs):
        with self.lock:
            handlers = self.subscribers[event_type][:]
        for handler in handlers:
            try:
                self.executor.submit(handler, *args, **kwargs)
            except Exception as e:
                logger.error(f"事件总线分发异常 [{event_type}]: {e}")

# 单例模式，全局复用
bus = EventBus()
