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

    risk_service.start_risk_monitor()
    time.sleep(0.01)

    assert risk_service._risk_monitor_started is True
    assert risk_service._risk_monitor_thread is not None

    risk_service.stop_risk_monitor()

    assert risk_service._risk_monitor_started is False
    assert risk_service._risk_monitor_thread is None

    risk_service.start_risk_monitor()
    risk_service.stop_risk_monitor()

    assert risk_service._risk_monitor_started is False


def test_media_request_refresh_loop_stop_resets_state_and_allows_restart(monkeypatch):
    from app.domains.media_requests import router

    router.stop_media_request_services()
    calls = []
    monkeypatch.setattr(router, "_refresh_community_cache", lambda: calls.append("refresh"))

    router.start_community_cache_refresh_loop()

    assert router._community_refresh_started is True
    assert router._community_refresh_thread is not None

    router.stop_media_request_services()

    assert router._community_refresh_started is False
    assert router._community_refresh_thread is None
    assert calls == []

    router.start_community_cache_refresh_loop()
    router.stop_media_request_services()

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
