# app/core/event_bus.py
import threading
from collections import defaultdict
import logging

logger = logging.getLogger("uvicorn")

class EventBus:
    def __init__(self):
        self.subscribers = defaultdict(list)
        self.lock = threading.Lock()

    def subscribe(self, event_type: str, handler):
        with self.lock:
            if handler not in self.subscribers[event_type]:
                self.subscribers[event_type].append(handler)

    def publish(self, event_type: str, *args, **kwargs):
        with self.lock:
            handlers = self.subscribers[event_type][:]
        # 多线程并发分发，确保发布者（如 Webhook）瞬间返回，绝不阻塞
        for handler in handlers:
            try:
                threading.Thread(target=handler, args=args, kwargs=kwargs, daemon=True).start()
            except Exception as e:
                logger.error(f"事件总线分发异常 [{event_type}]: {e}")

# 单例模式，全局复用
bus = EventBus()