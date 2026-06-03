import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeLogger:
    def __init__(self):
        self.infos = []

    def info(self, message):
        self.infos.append(message)


class FakeBus:
    def __init__(self):
        self.published = []

    def publish(self, event_name, data):
        self.published.append((event_name, data))


class FakeCalendarService:
    def __init__(self):
        self.ready_calls = []

    def mark_episode_ready(self, series_id, season, episode):
        self.ready_calls.append((series_id, season, episode))


def _make_daemon():
    from app.bot.notification_bot import bot_service

    daemon = bot_service.SystemDaemon()
    daemon.library_tasks = []
    daemon.cleared_gaps = []
    daemon.add_library_task = lambda item: daemon.library_tasks.append(item)
    daemon._clear_gap_record_async = lambda item: daemon.cleared_gaps.append(item)
    return daemon


def _patch_dependencies(monkeypatch):
    from app.bot.notification_bot import notification_bot_webhook_event_service
    from app.bot.notification_bot import bot_service

    logger = FakeLogger()
    bus = FakeBus()
    calendar_service = FakeCalendarService()

    monkeypatch.setattr(bot_service, "logger", logger)
    monkeypatch.setattr(bot_service, "bus", bus)
    monkeypatch.setattr(
        notification_bot_webhook_event_service,
        "_calendar_service_provider",
        lambda: calendar_service,
    )

    return logger, bus, calendar_service


def test_webhook_unimportant_event_has_no_side_effects(monkeypatch):
    logger, bus, calendar_service = _patch_dependencies(monkeypatch)
    daemon = _make_daemon()

    daemon.on_webhook_event("session.keepalive", {"Item": {"Id": "item-1"}})

    assert logger.infos == []
    assert bus.published == []
    assert calendar_service.ready_calls == []
    assert daemon.library_tasks == []
    assert daemon.cleared_gaps == []


def test_webhook_library_item_event_enqueues_item_when_id_exists(monkeypatch):
    logger, bus, calendar_service = _patch_dependencies(monkeypatch)
    daemon = _make_daemon()
    item = {"Id": "movie-1", "Type": "Movie"}

    daemon.on_webhook_event("library.new", {"Item": item})

    assert logger.infos == ["🔔 [Webhook] 收到事件: library.new"]
    assert daemon.library_tasks == [item]
    assert calendar_service.ready_calls == []
    assert daemon.cleared_gaps == []
    assert bus.published == []


def test_webhook_library_item_event_skips_missing_item_id(monkeypatch):
    logger, bus, calendar_service = _patch_dependencies(monkeypatch)
    daemon = _make_daemon()

    daemon.on_webhook_event("item.added", {"Item": {"Type": "Movie"}})

    assert logger.infos == ["🔔 [Webhook] 收到事件: item.added"]
    assert daemon.library_tasks == []
    assert calendar_service.ready_calls == []
    assert daemon.cleared_gaps == []
    assert bus.published == []


def test_webhook_episode_event_marks_calendar_ready_and_clears_gap(monkeypatch):
    logger, bus, calendar_service = _patch_dependencies(monkeypatch)
    daemon = _make_daemon()
    item = {"Id": "ep-1", "Type": "Episode", "SeriesId": "series-1", "ParentIndexNumber": 2, "IndexNumber": 7}

    daemon.on_webhook_event("item.added", {"Item": item})

    assert logger.infos == ["🔔 [Webhook] 收到事件: item.added"]
    assert daemon.library_tasks == [item]
    assert calendar_service.ready_calls == [("series-1", 2, 7)]
    assert daemon.cleared_gaps == [item]
    assert bus.published == []


def test_webhook_playback_start_stop_publish_existing_event_names(monkeypatch):
    logger, bus, _calendar_service = _patch_dependencies(monkeypatch)
    daemon = _make_daemon()
    start_data = {"Session": "one"}
    stop_data = {"Session": "two"}

    daemon.on_webhook_event("playback.start", start_data)
    daemon.on_webhook_event("playback.stop", stop_data)

    assert logger.infos == [
        "🔔 [Webhook] 收到事件: playback.start",
        "🔔 [Webhook] 发布 playback.start 事件",
        "🔔 [Webhook] 收到事件: playback.stop",
        "🔔 [Webhook] 发布 playback.stop 事件",
    ]
    assert bus.published == [
        ("notify.playback.start", start_data),
        ("notify.playback.stop", stop_data),
    ]
    assert daemon.library_tasks == []
    assert daemon.cleared_gaps == []


def test_webhook_auth_login_and_delete_remove_publish_existing_event_names(monkeypatch):
    logger, bus, _calendar_service = _patch_dependencies(monkeypatch)
    daemon = _make_daemon()
    auth_data = {"User": "login"}
    delete_data = {"Item": "deleted"}

    daemon.on_webhook_event("authentication.login", auth_data)
    daemon.on_webhook_event("item.remove", delete_data)

    assert logger.infos == [
        "🔔 [Webhook] 收到事件: authentication.login",
        "🔔 [Webhook] 收到事件: item.remove",
    ]
    assert bus.published == [
        ("notify.user.login", auth_data),
        ("notify.item.deleted", delete_data),
    ]
    assert daemon.library_tasks == []
    assert daemon.cleared_gaps == []
