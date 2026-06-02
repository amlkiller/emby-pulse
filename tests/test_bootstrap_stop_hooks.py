import asyncio
import os
import sys

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)


def test_calendar_notify_stop_services_stops_global_service(monkeypatch):
    from app.domains.notifications import calendar_notify

    calls = []
    monkeypatch.setattr(calendar_notify.calendar_notify_service, "stop", lambda: calls.append("stop"))

    calendar_notify.stop_calendar_notify_services()

    assert calls == ["stop"]


def test_system_task_stop_cancels_poller_and_allows_restart():
    from app.domains.system import tasks

    async def run_check():
        tasks.stop_system_task_services()
        tasks.start_task_poller()

        poller_task = tasks._poller_task
        assert poller_task is not None
        assert tasks._task_poller_started is True

        tasks.stop_system_task_services()
        await asyncio.sleep(0)

        assert poller_task.cancelled()
        assert tasks._poller_task is None
        assert tasks._task_poller_started is False
        assert tasks._poller_initialized is False

    asyncio.run(run_check())


def test_auth_lock_cleanup_stop_resets_state_and_allows_restart(monkeypatch):
    from app.domains.users import auth

    auth.stop_auth_domain_services()
    calls = []
    monkeypatch.setattr(auth, "cleanup_expired_login_locks", lambda: calls.append("cleanup") or 0)

    auth._start_lock_cleanup()
    assert calls == ["cleanup"]
    assert auth._lock_cleanup_started is True

    auth.stop_auth_domain_services()
    assert auth._lock_cleanup_started is False
    assert auth._lock_cleanup_thread is None

    auth._start_lock_cleanup()
    auth.stop_auth_domain_services()

    assert calls == ["cleanup", "cleanup"]


def test_session_cleanup_stop_resets_state_and_allows_restart(monkeypatch):
    from app.core import session

    session.stop_session_services()
    calls = []
    monkeypatch.setattr(session, "dao_cleanup_expired_sessions", lambda now: calls.append(now) or 0)

    session.start_session_cleanup_loop(interval_seconds=600)
    assert len(calls) == 1
    assert session._session_cleanup_started is True

    session.stop_session_services()
    assert session._session_cleanup_started is False
    assert session._session_cleanup_thread is None

    session.start_session_cleanup_loop(interval_seconds=600)
    session.stop_session_services()

    assert len(calls) == 2


def test_dashboard_cache_stop_cancels_tasks_and_allows_restart(monkeypatch):
    async def run_check():
        from app.domains.playback import stats

        stats.stop_dashboard_cache_tasks()

        async def fake_preload_dashboard_cache(*args, **kwargs):
            await asyncio.sleep(60)

        monkeypatch.setattr(stats, "preload_dashboard_cache", fake_preload_dashboard_cache)

        stats.start_dashboard_cache_tasks()

        preload_task = stats._dashboard_preload_task
        refresh_task = stats._dashboard_refresh_task
        assert preload_task is not None
        assert refresh_task is not None
        assert stats._dashboard_cache_tasks_started is True

        stats.stop_dashboard_cache_tasks()
        await asyncio.sleep(0)

        assert preload_task.cancelled()
        assert refresh_task.cancelled()
        assert stats._dashboard_preload_task is None
        assert stats._dashboard_refresh_task is None
        assert stats._dashboard_cache_tasks_started is False

        stats.start_dashboard_cache_tasks()
        stats.stop_dashboard_cache_tasks()

        assert stats._dashboard_cache_tasks_started is False

    asyncio.run(run_check())
