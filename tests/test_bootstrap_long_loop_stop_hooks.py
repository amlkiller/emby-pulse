import os
import sys
import time

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)


def test_risk_monitor_stop_resets_state_and_allows_restart(monkeypatch):
    from app.domains.risk import risk_service

    risk_service.stop_risk_monitor()
    calls = []
    monkeypatch.setattr(risk_service, "scan_playbacks_and_alert", lambda: calls.append("scan"))
    subscriptions = []

    class FakeBus:
        def subscribe(self, event_type, handler):
            if (event_type, handler) not in subscriptions:
                subscriptions.append((event_type, handler))

        def unsubscribe(self, event_type, handler):
            if (event_type, handler) in subscriptions:
                subscriptions.remove((event_type, handler))

    monkeypatch.setattr(risk_service, "bus", FakeBus())

    risk_service.start_risk_monitor()
    risk_service.start_risk_monitor()
    time.sleep(0.01)

    assert risk_service._risk_monitor_started is True
    assert risk_service._risk_monitor_thread is not None
    assert risk_service._risk_monitor_subscribed is True
    assert subscriptions == [
        ("notify.playback.start", risk_service._on_playback_start),
        ("notify.risk.alert", risk_service._on_risk_alert_for_web),
    ]

    risk_service.stop_risk_monitor()

    assert risk_service._risk_monitor_started is False
    assert risk_service._risk_monitor_thread is None
    assert risk_service._risk_monitor_subscribed is False
    assert subscriptions == []

    risk_service.start_risk_monitor()
    assert subscriptions == [
        ("notify.playback.start", risk_service._on_playback_start),
        ("notify.risk.alert", risk_service._on_risk_alert_for_web),
    ]
    risk_service.stop_risk_monitor()

    assert risk_service._risk_monitor_started is False
    assert subscriptions == []


def test_media_request_refresh_loop_stop_resets_state_and_allows_restart(monkeypatch):
    from app.domains.media_requests import router

    router.stop_community_cache_refresh_loop()
    calls = []
    monkeypatch.setattr(router, "_refresh_community_cache", lambda: calls.append("refresh"))

    router.start_community_cache_refresh_loop()

    assert router._community_refresh_started is True
    assert router._community_refresh_thread is not None

    router.stop_community_cache_refresh_loop()

    assert router._community_refresh_started is False
    assert router._community_refresh_thread is None
    assert calls == []

    router.start_community_cache_refresh_loop()
    router.stop_community_cache_refresh_loop()

    assert router._community_refresh_started is False


def test_calendar_service_stop_resets_state_and_allows_restart(monkeypatch):
    from app.domains.playback.calendar_service import CalendarService

    service = CalendarService()
    calls = []
    monkeypatch.setattr(service, "get_weekly_calendar", lambda **kwargs: calls.append(kwargs))

    service.start()

    assert service._background_sync_started is True
    assert service._background_sync_thread is not None

    service.stop()

    assert service._background_sync_started is False
    assert service._background_sync_thread is None
    assert calls == []

    service.start()
    service.stop()

    assert service._background_sync_started is False


def test_gap_service_stop_resets_delayed_start_and_allows_restart(monkeypatch):
    from app.domains.media_requests import gaps

    gaps.stop_gap_services()
    calls = []
    monkeypatch.setattr(gaps, "_ensure_gap_tables", lambda: calls.append("ensure"))

    gaps.start_gap_services()

    assert gaps._gap_services_started is True
    assert gaps._gap_delayed_start_thread is not None

    gaps.stop_gap_services()

    assert gaps._gap_services_started is False
    assert gaps._gap_delayed_start_thread is None
    assert gaps._gap_background_sync_thread is None

    gaps.start_gap_services()
    gaps.stop_gap_services()

    assert gaps._gap_services_started is False
    assert calls == ["ensure", "ensure"]


def test_gap_service_stop_resets_active_background_sync(monkeypatch):
    from app.domains.media_requests import gaps

    gaps.stop_gap_services()
    monkeypatch.setattr(gaps, "_ensure_gap_tables", lambda: None)
    monkeypatch.setattr(gaps, "_delayed_start_background_sync", lambda: None)

    gaps.start_gap_services()
    gaps._start_background_gap_sync()

    assert gaps._gap_services_started is True
    assert gaps._gap_background_sync_thread is not None

    gaps.stop_gap_services()

    assert gaps._gap_services_started is False
    assert gaps._gap_delayed_start_thread is None
    assert gaps._gap_background_sync_thread is None


def test_weather_cache_refresh_stop_resets_state_and_allows_restart(monkeypatch):
    from app.domains.system import system_tools

    system_tools.stop_weather_cache_refresh()
    calls = []
    monkeypatch.setattr(system_tools, "refresh_weather_cache", lambda *args, **kwargs: calls.append(args))
    monkeypatch.setattr(system_tools, "WEATHER_CACHE_TTL", 60)

    system_tools.start_weather_cache_refresh()
    system_tools.start_weather_cache_refresh()

    assert system_tools._weather_refresh_running is True
    assert system_tools._weather_refresh_thread is not None

    system_tools.stop_weather_cache_refresh()

    assert system_tools._weather_refresh_running is False
    assert system_tools._weather_refresh_thread is None
    assert calls == []

    system_tools.start_weather_cache_refresh()
    system_tools.stop_weather_cache_refresh()

    assert system_tools._weather_refresh_running is False
