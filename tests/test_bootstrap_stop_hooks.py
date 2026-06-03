import asyncio
import os
import sys

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)


def test_calendar_notify_service_stop_stops_global_service(monkeypatch):
    from app.domains.notifications import calendar_notify

    calls = []
    monkeypatch.setattr(calendar_notify.calendar_notify_service, "stop", lambda: calls.append("stop"))

    calendar_notify.calendar_notify_service.stop()

    assert calls == ["stop"]


def test_calendar_notify_service_thread_lifecycle(monkeypatch):
    import inspect

    from app.domains.notifications import calendar_notify

    class FakeThread:
        instances = []

        def __init__(self, target=None, daemon=False, name=None):
            self.target = target
            self.daemon = daemon
            self.name = name
            self.started = False
            self.alive = False
            self.join_timeout = None
            FakeThread.instances.append(self)

        def start(self):
            self.started = True
            self.alive = True

        def is_alive(self):
            return self.alive

        def join(self, timeout=None):
            self.join_timeout = timeout
            self.alive = False

    monkeypatch.setattr(calendar_notify.threading, "Thread", FakeThread)

    service = calendar_notify.CalendarNotifyService()
    service.start()
    service.start()

    assert len(FakeThread.instances) == 1
    assert service.thread.name == "calendar-notify-scheduler"
    assert service.thread.daemon is True
    assert service._stop_event.is_set() is False

    service.stop()

    assert service._stop_event.is_set() is True
    assert FakeThread.instances[0].join_timeout == 1
    assert service.thread is None

    service.restart()

    assert len(FakeThread.instances) == 2
    assert service.thread is FakeThread.instances[1]
    assert service._stop_event.is_set() is False

    sticky_service = calendar_notify.CalendarNotifyService()
    sticky_service.start()
    sticky_service.thread.join = lambda timeout=None: setattr(sticky_service.thread, "join_timeout", timeout)
    sticky_service.stop()

    assert sticky_service.thread is FakeThread.instances[2]
    assert sticky_service.thread.join_timeout == 1

    sticky_service.start()
    sticky_service.restart()

    assert len(FakeThread.instances) == 3
    assert sticky_service.thread is FakeThread.instances[2]

    loop_source = inspect.getsource(calendar_notify.CalendarNotifyService._loop)
    restart_source = inspect.getsource(calendar_notify.CalendarNotifyService.restart)
    assert "_stop_event.wait(60)" in loop_source
    assert "time.sleep" not in restart_source


def test_system_task_stop_cancels_poller_and_allows_restart():
    import inspect

    from app.domains.system import tasks

    async def run_check():
        tasks.stop_task_poller()
        tasks.start_task_poller()

        poller_task = tasks._poller_task
        assert poller_task is not None
        assert tasks._task_poller_started is True

        tasks.stop_task_poller()
        await asyncio.sleep(0)

        assert poller_task.cancelled()
        assert tasks._poller_task is None
        assert tasks._task_poller_started is False
        assert tasks._poller_initialized is False

    asyncio.run(run_check())

    poller_source = inspect.getsource(tasks.poll_emby_tasks)
    assert "while _task_poller_started" in poller_source
    assert "while True" not in poller_source
    assert "await asyncio.sleep(5)" in poller_source


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

    session.stop_session_cleanup_loop()
    calls = []
    monkeypatch.setattr(session, "dao_cleanup_expired_sessions", lambda now: calls.append(now) or 0)

    session.start_session_cleanup_loop(interval_seconds=600)
    assert len(calls) == 1
    assert session._session_cleanup_started is True

    session.stop_session_cleanup_loop()
    assert session._session_cleanup_started is False
    assert session._session_cleanup_thread is None

    session.start_session_cleanup_loop(interval_seconds=600)
    session.stop_session_cleanup_loop()

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


def test_notification_bot_event_subscriptions_are_reversible(monkeypatch):
    import inspect

    from app.domains.notifications import bot_service

    subscriptions = []

    class FakeBus:
        def subscribe(self, event_type, handler):
            if (event_type, handler) not in subscriptions:
                subscriptions.append((event_type, handler))

        def unsubscribe(self, event_type, handler):
            if (event_type, handler) in subscriptions:
                subscriptions.remove((event_type, handler))

    monkeypatch.setattr(bot_service, "bus", FakeBus())
    monkeypatch.setattr(bot_service, "get_bot_tg_token", lambda: "token")
    monkeypatch.setattr(bot_service, "get_wecom_corpid", lambda: "")
    monkeypatch.setattr(bot_service.NotificationBot, "_set_commands", lambda self: None)
    monkeypatch.setattr(bot_service.NotificationBot, "_set_wecom_menu", lambda self: None)

    class FakeThread:
        instances = []

        def __init__(self, target=None, daemon=False, name=None):
            self.target = target
            self.daemon = daemon
            self.name = name
            self.started = False
            self.alive = False
            self.join_timeout = None
            FakeThread.instances.append(self)

        def start(self):
            self.started = True
            self.alive = True

        def is_alive(self):
            return self.alive

        def join(self, timeout=None):
            self.join_timeout = timeout
            self.alive = False

    monkeypatch.setattr(bot_service.threading, "Thread", FakeThread)

    daemon = bot_service.SystemDaemon()
    notifier = bot_service.NotificationBot()

    assert daemon._subscribed is False
    assert notifier._subscribed is False
    assert subscriptions == []

    daemon.start()
    daemon.start()
    notifier.start()
    notifier.start()

    assert len(FakeThread.instances) == 3
    assert daemon.schedule_thread.name == "notification-daemon-scheduler"
    assert daemon.library_thread.name == "notification-daemon-library"
    assert notifier.poll_thread.name == "notification-bot-polling"

    expected = [
        ("webhook.received", daemon.on_webhook_event),
        ("notify.library.new_episode", notifier.on_library_new_episode),
        ("notify.library.new_item", notifier.on_library_new_item),
        ("notify.gap_cleared", notifier.on_gap_cleared),
        ("notify.playback.start", notifier._on_playback_start_event),
        ("notify.playback.stop", notifier._on_playback_stop_event),
        ("notify.user.login", notifier.on_user_login),
        ("notify.item.deleted", notifier.on_item_deleted),
        ("notify.daily_report", notifier.on_daily_report),
        ("notify.risk.alert", notifier.on_risk_alert),
    ]
    assert subscriptions == expected
    assert daemon._subscribed is True
    assert notifier._subscribed is True

    playback_calls = []
    monkeypatch.setattr(notifier, "on_playback_event", lambda data, action: playback_calls.append((data, action)))
    notifier._on_playback_start_event({"item": "one"})
    notifier._on_playback_stop_event({"item": "two"})
    assert playback_calls == [
        ({"item": "one"}, "start"),
        ({"item": "two"}, "stop"),
    ]

    daemon.stop()
    notifier.stop()

    assert subscriptions == []
    assert daemon._subscribed is False
    assert notifier._subscribed is False
    assert FakeThread.instances[0].join_timeout == 1
    assert FakeThread.instances[1].join_timeout == 1
    assert FakeThread.instances[2].join_timeout == 1
    assert daemon.schedule_thread is None
    assert daemon.library_thread is None
    assert notifier.poll_thread is None

    daemon.start()
    notifier.start()

    assert subscriptions == expected
    assert daemon.schedule_thread is FakeThread.instances[3]
    assert daemon.library_thread is FakeThread.instances[4]
    assert notifier.poll_thread is FakeThread.instances[5]

    library_group_source = inspect.getsource(bot_service.SystemDaemon._process_library_group)
    pending_sync_source = inspect.getsource(bot_service.SystemDaemon._sync_pending_requests)
    assert "_stop_event.wait(2)" in library_group_source
    assert "_stop_event.wait(0.5)" in pending_sync_source
    assert "time.sleep" not in library_group_source
    assert "time.sleep" not in pending_sync_source


def test_user_bot_worker_threads_stop_and_restart(monkeypatch):
    import inspect

    from app.domains.notifications import user_bot_service

    monkeypatch.setattr(user_bot_service, "_is_pro", lambda: True)
    monkeypatch.setattr(user_bot_service, "get_user_bot_token", lambda: "token")
    monkeypatch.setattr(user_bot_service.UserBot, "_set_commands", lambda self: None)
    monkeypatch.setattr(user_bot_service, "_load_batch_used_from_cfg", lambda: None)
    user_bot_service._batch_flush_thread = None
    user_bot_service._batch_flush_stop.clear()

    flush_calls = []
    monkeypatch.setattr(user_bot_service, "_flush_batch_used", lambda force=False: flush_calls.append(force))

    class FakeThread:
        instances = []

        def __init__(self, target=None, daemon=False, name=None):
            self.target = target
            self.daemon = daemon
            self.name = name
            self.started = False
            self.alive = False
            self.join_timeout = None
            FakeThread.instances.append(self)

        def start(self):
            self.started = True
            self.alive = True

        def is_alive(self):
            return self.alive

        def join(self, timeout=None):
            self.join_timeout = timeout
            self.alive = False

    monkeypatch.setattr(user_bot_service.threading, "Thread", FakeThread)

    user_bot = user_bot_service.UserBot()

    user_bot.start()
    user_bot.start()

    assert len(FakeThread.instances) == 3
    assert user_bot.poll_thread.name == "user-bot-polling"
    assert user_bot.scheduler_thread.name == "user-bot-scheduler"
    assert user_bot_service._batch_flush_thread.name == "batch-flush"
    assert user_bot._stop_event.is_set() is False

    user_bot.stop()

    assert flush_calls == [True]
    assert user_bot._stop_event.is_set() is True
    assert user_bot_service._batch_flush_stop.is_set() is True
    assert FakeThread.instances[0].join_timeout == 1
    assert FakeThread.instances[1].join_timeout == 1
    assert FakeThread.instances[2].join_timeout == 1
    assert user_bot.poll_thread is None
    assert user_bot.scheduler_thread is None
    assert user_bot_service._batch_flush_thread is None

    user_bot.start()

    assert len(FakeThread.instances) == 6
    assert user_bot._stop_event.is_set() is False
    assert user_bot_service._batch_flush_stop.is_set() is False
    assert user_bot.poll_thread is FakeThread.instances[3]
    assert user_bot.scheduler_thread is FakeThread.instances[4]
    assert user_bot_service._batch_flush_thread is FakeThread.instances[5]

    polling_source = inspect.getsource(user_bot_service.UserBot._polling_loop)
    from app.domains.notifications import user_bot_scheduler_service

    scheduler_source = inspect.getsource(user_bot_scheduler_service.run_scheduler_loop)
    scheduler_wrapper_source = inspect.getsource(user_bot_service.UserBot._scheduler_loop)
    batch_flush_source = inspect.getsource(user_bot_service._batch_flush_loop)
    assert "_stop_event.wait(3)" in polling_source
    assert "_stop_event.wait(5)" in polling_source
    assert "stop_event.wait(30)" in scheduler_source
    assert "stop_event.wait(60)" in scheduler_source
    assert "user_bot_scheduler_service.run_scheduler_loop" in scheduler_wrapper_source
    assert "_batch_flush_stop.wait(BATCH_FLUSH_INTERVAL)" in batch_flush_source
    assert "_batch_flush_stop.wait(5)" in batch_flush_source
    assert "time.sleep" not in polling_source
    assert "time.sleep" not in scheduler_source
    assert "time.sleep" not in batch_flush_source

    sticky_bot = user_bot_service.UserBot()
    sticky_bot.start()
    sticky_bot.poll_thread.join = lambda timeout=None: setattr(sticky_bot.poll_thread, "join_timeout", timeout)
    user_bot_service._batch_flush_thread.join = (
        lambda timeout=None: setattr(user_bot_service._batch_flush_thread, "join_timeout", timeout)
    )
    sticky_bot.stop()
    assert sticky_bot.poll_thread is FakeThread.instances[6]
    assert sticky_bot.scheduler_thread is None
    assert user_bot_service._batch_flush_thread is FakeThread.instances[5]
    assert user_bot_service._batch_flush_thread.join_timeout == 1

    sticky_bot.start()
    assert len(FakeThread.instances) == 8
    assert sticky_bot.poll_thread is FakeThread.instances[6]
    assert sticky_bot.scheduler_thread is None
    assert user_bot_service._batch_flush_thread is FakeThread.instances[5]

    user_bot_service._batch_flush_thread.alive = False
    user_bot_service._stop_batch_flush_thread()
    assert user_bot_service._batch_flush_thread is None


def test_notification_media_quality_uses_color_transfer_hdr_fallback(monkeypatch):
    from app.domains.notifications import bot_service

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "MediaStreams": [{
                    "Type": "Video",
                    "Width": 1920,
                    "Height": 1080,
                    "BitRate": 8000000,
                    "Codec": "hevc",
                    "ColorTransfer": "arib-std-b67",
                }]
            }

    class FakeMediaApi:
        api_key = "api-key"

        def get(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(bot_service, "media_api", FakeMediaApi())
    monkeypatch.setattr(bot_service, "get_admin_id", lambda: "admin")

    result = bot_service.get_media_quality_info("item-1")

    assert result["hdr"] == "HLG"
    assert result["quality"] == "1080p HLG"
