import logging

from app.core.event_bus import bus


logger = logging.getLogger("uvicorn")

_IMPORTANT_EVENTS = ["item.added", "library.new", "playback.start", "playback.stop", "auth", "login", "delete", "remove"]


def _default_calendar_service():
    from app.domains.playback.calendar_service import calendar_service

    return calendar_service


_bus_provider = lambda: bus
_logger_provider = lambda: logger
_calendar_service_provider = lambda: _default_calendar_service()


def set_dependency_providers(
    *,
    bus_provider=None,
    logger_provider=None,
    calendar_service_provider=None,
):
    global _bus_provider
    global _logger_provider
    global _calendar_service_provider

    if bus_provider is not None:
        _bus_provider = bus_provider
    if logger_provider is not None:
        _logger_provider = logger_provider
    if calendar_service_provider is not None:
        _calendar_service_provider = calendar_service_provider


def handle_webhook_event(daemon, event: str, data: dict):
    if any(e in event for e in _IMPORTANT_EVENTS):
        _logger_provider().info(f"🔔 [Webhook] 收到事件: {event}")

    if "item.added" in event or "library.new" in event:
        item = data.get("Item", {})
        if item.get("Id"):
            daemon.add_library_task(item)
            if item.get("Type") == "Episode":
                _calendar_service_provider().mark_episode_ready(
                    item.get("SeriesId"),
                    item.get("ParentIndexNumber"),
                    item.get("IndexNumber"),
                )
                daemon._clear_gap_record_async(item)
    elif "playback.start" in event:
        _logger_provider().info("🔔 [Webhook] 发布 playback.start 事件")
        _bus_provider().publish("notify.playback.start", data)
    elif "playback.stop" in event:
        _logger_provider().info("🔔 [Webhook] 发布 playback.stop 事件")
        _bus_provider().publish("notify.playback.stop", data)
    elif "auth" in event or "login" in event:
        _bus_provider().publish("notify.user.login", data)
    elif "delete" in event or "remove" in event:
        _bus_provider().publish("notify.item.deleted", data)
