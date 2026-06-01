"""
日历通知服务 - 启动入口
"""
import threading
import time
import logging

logger = logging.getLogger("uvicorn")

# 延迟导入避免循环依赖
calendar_notify_service = None

def start_calendar_notify_service():
    """启动日历通知服务"""
    global calendar_notify_service
    try:
        from app.domains.notifications.calendar_notify import calendar_notify_service as service
        calendar_notify_service = service
        service.start()
    except Exception as e:
        logger.error(f"[日历通知] 服务启动失败: {e}")

def stop_calendar_notify_service():
    """停止日历通知服务"""
    global calendar_notify_service
    if calendar_notify_service:
        calendar_notify_service.stop()
