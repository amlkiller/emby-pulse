import importlib
import inspect
import os
import sys

import pytest

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)


class FakeThread:
    instances = []

    def __init__(self, target=None, args=(), daemon=False, name=None):
        self.target = target
        self.args = args
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


PLUGIN_CASES = [
    (
        "app.plugins.auto_expire.plugin",
        "AutoExpirePlugin",
        "_thread",
        "_running",
        "_check_loop",
        "auto-expire-check",
    ),
    (
        "app.plugins.temp_account.plugin",
        "TempAccountPlugin",
        "_thread",
        "_running",
        "_check_loop",
        "temp-account-check",
    ),
    (
        "app.plugins.keep_alive.plugin",
        "KeepAlivePlugin",
        "_thread",
        "_running",
        "_check_loop",
        "keep-alive-check",
    ),
    (
        "app.plugins.smart_collections.plugin",
        "SmartCollectionsPlugin",
        "_sync_thread",
        "_running",
        "_sync_loop",
        "smart-collections-sync",
    ),
    (
        "app.plugins.view_report.plugin",
        "ViewReportPlugin",
        "scheduler_thread",
        "scheduler_running",
        "_scheduler_loop",
        "view-report-scheduler",
    ),
    (
        "app.plugins.emby_restart.plugin",
        "EmbyRestartPlugin",
        "scheduler_thread",
        "scheduler_running",
        "_scheduler_loop",
        "emby-restart-scheduler",
    ),
    (
        "app.plugins.user_backup.plugin",
        "UserBackupPlugin",
        "_thread",
        "_running",
        "_schedule_loop",
        "user-backup-scheduler",
    ),
    (
        "app.plugins.hdhive.plugin",
        "HDHivePlugin",
        "_checkin_thread",
        "_running",
        "_checkin_loop",
        "hdhive-checkin",
    ),
    (
        "app.plugins.hdhivesign.plugin",
        "HDHiveSignPlugin",
        "_checkin_thread",
        "_running",
        "_checkin_loop",
        "hdhivesign-checkin",
    ),
]


def _build_plugin(monkeypatch, module_path, class_name):
    from app.plugins.base import PluginBase

    monkeypatch.setattr(PluginBase, "_init_logs_table", lambda self: None)
    monkeypatch.setattr(PluginBase, "_load_config_to_cache", lambda self: None)

    module = importlib.import_module(module_path)
    plugin_class = getattr(module, class_name)
    if hasattr(plugin_class, "_setup_routes"):
        monkeypatch.setattr(plugin_class, "_setup_routes", lambda self: None)
    if hasattr(plugin_class, "_init_db"):
        monkeypatch.setattr(plugin_class, "_init_db", lambda self: None)
    if hasattr(plugin_class, "_load_history"):
        monkeypatch.setattr(plugin_class, "_load_history", lambda self: None)
    if hasattr(plugin_class, "_ensure_dir"):
        monkeypatch.setattr(plugin_class, "_ensure_dir", lambda self: None)
    if hasattr(plugin_class, "_ensure_db"):
        monkeypatch.setattr(plugin_class, "_ensure_db", lambda self: None)
    if hasattr(plugin_class, "_check_today_backup"):
        monkeypatch.setattr(plugin_class, "_check_today_backup", lambda self: None)

    plugin = plugin_class()
    plugin._enabled = True
    plugin.log = lambda *args, **kwargs: None
    return module, plugin


@pytest.mark.parametrize(
    "module_path,class_name,thread_attr,running_attr,loop_name,thread_name",
    PLUGIN_CASES,
)
def test_plugin_scheduler_start_is_idempotent_and_disable_clears_thread(
    monkeypatch, module_path, class_name, thread_attr, running_attr, loop_name, thread_name
):
    module, plugin = _build_plugin(monkeypatch, module_path, class_name)
    FakeThread.instances = []
    monkeypatch.setattr(module.threading, "Thread", FakeThread)

    assert hasattr(plugin, "_stop_event")
    assert not plugin._stop_event.is_set()

    plugin.on_enable()
    plugin.on_enable()

    assert len(FakeThread.instances) == 1
    thread = FakeThread.instances[0]
    assert thread.started is True
    assert thread.daemon is True
    assert thread.name == thread_name
    assert thread.target == getattr(plugin, loop_name)
    assert getattr(plugin, thread_attr) is thread
    assert getattr(plugin, running_attr) is True
    assert not plugin._stop_event.is_set()

    plugin.on_disable()

    assert getattr(plugin, running_attr) is False
    assert plugin._stop_event.is_set()
    assert thread.join_timeout == 1
    assert getattr(plugin, thread_attr) is None


@pytest.mark.parametrize(
    "module_path,class_name,thread_attr,running_attr,loop_name,thread_name",
    PLUGIN_CASES,
)
def test_plugin_scheduler_loops_use_interruptible_waits(
    monkeypatch, module_path, class_name, thread_attr, running_attr, loop_name, thread_name
):
    _, plugin = _build_plugin(monkeypatch, module_path, class_name)

    source = inspect.getsource(getattr(plugin, loop_name))

    assert "_stop_event.wait" in source
    assert "time.sleep" not in source


def test_hdhivesign_checkin_retry_wait_continues_when_plugin_is_running(monkeypatch):
    _, plugin = _build_plugin(
        monkeypatch,
        "app.plugins.hdhivesign.plugin",
        "HDHiveSignPlugin",
    )
    signin_calls = []
    wait_calls = []
    saved_history = []

    monkeypatch.setattr(
        plugin,
        "_get_config",
        lambda: {
            "cookie": "token=test-token",
            "base_url": "https://hdhive.test",
            "max_retries": 1,
            "retry_interval": 7,
        },
    )
    monkeypatch.setattr(plugin, "_fetch_user_info", lambda cookies, token, base_url: {})
    monkeypatch.setattr(plugin, "_save_sign_history", lambda sign_data: saved_history.append(sign_data))
    monkeypatch.setattr(plugin, "_send_notification", lambda sign_data: None)
    monkeypatch.setattr(plugin._stop_event, "wait", lambda timeout: wait_calls.append(timeout) and False)

    def fake_signin(cookies, token, base_url, is_gambler):
        signin_calls.append((cookies, token, base_url, is_gambler))
        if len(signin_calls) == 1:
            return False, "temporary failure", 0
        return True, "签到成功", 5

    monkeypatch.setattr(plugin, "_signin_base", fake_signin)

    result = plugin.checkin()

    assert result["status"] == "success"
    assert result["message"] == "签到成功"
    assert wait_calls == [7]
    assert len(signin_calls) == 2
    assert saved_history[0]["status"] == "签到成功"


def test_hdhivesign_checkin_retry_wait_stops_when_plugin_is_disabled(monkeypatch):
    _, plugin = _build_plugin(
        monkeypatch,
        "app.plugins.hdhivesign.plugin",
        "HDHiveSignPlugin",
    )
    signin_calls = []
    wait_calls = []
    saved_history = []

    monkeypatch.setattr(
        plugin,
        "_get_config",
        lambda: {
            "cookie": "token=test-token",
            "base_url": "https://hdhive.test",
            "max_retries": 3,
            "retry_interval": 11,
        },
    )
    monkeypatch.setattr(plugin, "_save_sign_history", lambda sign_data: saved_history.append(sign_data))
    monkeypatch.setattr(plugin._stop_event, "wait", lambda timeout: wait_calls.append(timeout) or True)

    def fake_signin(cookies, token, base_url, is_gambler):
        signin_calls.append((cookies, token, base_url, is_gambler))
        return False, "temporary failure", 0

    monkeypatch.setattr(plugin, "_signin_base", fake_signin)

    result = plugin.checkin()

    assert result == {"status": "error", "message": "temporary failure"}
    assert wait_calls == [11]
    assert len(signin_calls) == 1
    assert saved_history == []


def test_hdhivesign_checkin_retry_delay_uses_interruptible_wait(monkeypatch):
    _, plugin = _build_plugin(
        monkeypatch,
        "app.plugins.hdhivesign.plugin",
        "HDHiveSignPlugin",
    )

    source = inspect.getsource(plugin.checkin)

    assert "_stop_event.wait(retry_interval)" in source
    assert "time.sleep" not in source


def test_event_bus_unsubscribe_is_idempotent():
    from app.core.event_bus import EventBus

    event_bus = EventBus()

    def handler(*args, **kwargs):
        pass

    try:
        event_bus.subscribe("webhook.received", handler)
        event_bus.subscribe("webhook.received", handler)

        assert event_bus.subscribers["webhook.received"] == [handler]

        event_bus.unsubscribe("webhook.received", handler)
        event_bus.unsubscribe("webhook.received", handler)

        assert "webhook.received" not in event_bus.subscribers
    finally:
        event_bus.executor.shutdown(wait=True)


def test_disable_enabled_plugins_invokes_enabled_plugin_disable_hooks(monkeypatch):
    import app.plugins as plugins

    class FakePlugin:
        def __init__(self, plugin_id, enabled):
            self.id = plugin_id
            self.enabled = enabled
            self.disable_calls = 0

        def disable(self):
            self.disable_calls += 1
            self.enabled = False

    enabled_plugin = FakePlugin("enabled", True)
    disabled_plugin = FakePlugin("disabled", False)
    monkeypatch.setattr(
        plugins,
        "_registry",
        {
            enabled_plugin.id: enabled_plugin,
            disabled_plugin.id: disabled_plugin,
        },
    )

    plugins.disable_enabled_plugins()
    plugins.disable_enabled_plugins()

    assert enabled_plugin.disable_calls == 1
    assert disabled_plugin.disable_calls == 0


def test_season_poster_webhook_subscription_is_idempotent_and_reversible(monkeypatch):
    class FakeBus:
        def __init__(self):
            self.handlers = []

        def subscribe(self, event_type, handler):
            assert event_type == "webhook.received"
            if handler not in self.handlers:
                self.handlers.append(handler)

        def unsubscribe(self, event_type, handler):
            assert event_type == "webhook.received"
            if handler in self.handlers:
                self.handlers.remove(handler)

    module, plugin = _build_plugin(
        monkeypatch,
        "app.plugins.season_poster_updater.plugin",
        "SeasonPosterUpdaterPlugin",
    )
    fake_bus = FakeBus()
    monkeypatch.setattr(module, "bus", fake_bus)

    plugin.on_enable()
    plugin.on_enable()

    assert plugin._subscribed is True
    assert fake_bus.handlers == [plugin._on_webhook_event]

    plugin.on_disable()

    assert plugin._subscribed is False
    assert fake_bus.handlers == []

    plugin.on_enable()

    assert plugin._subscribed is True
    assert fake_bus.handlers == [plugin._on_webhook_event]


@pytest.mark.parametrize(
    "module_path,class_name",
    [
        ("app.plugins.cloud115.plugin", "Cloud115Plugin"),
        ("app.plugins.hdhive.plugin", "HDHivePlugin"),
    ],
)
def test_bot_admin_message_plugin_subscription_is_idempotent_and_reversible(
    monkeypatch, module_path, class_name
):
    class FakeBus:
        def __init__(self):
            self.handlers = []

        def subscribe(self, event_type, handler):
            assert event_type == "bot.admin_message"
            if handler not in self.handlers:
                self.handlers.append(handler)

        def unsubscribe(self, event_type, handler):
            assert event_type == "bot.admin_message"
            if handler in self.handlers:
                self.handlers.remove(handler)

    module, plugin = _build_plugin(monkeypatch, module_path, class_name)
    fake_bus = FakeBus()
    monkeypatch.setattr(module, "bus", fake_bus)

    if hasattr(module, "threading"):
        FakeThread.instances = []
        monkeypatch.setattr(module.threading, "Thread", FakeThread)

    plugin.on_enable()
    plugin.on_enable()

    assert plugin._subscribed is True
    assert fake_bus.handlers == [plugin._on_admin_message]

    plugin.on_disable()

    assert plugin._subscribed is False
    assert fake_bus.handlers == []

    plugin.on_enable()

    assert plugin._subscribed is True
    assert fake_bus.handlers == [plugin._on_admin_message]

    plugin.on_disable()

    assert plugin._subscribed is False
    assert fake_bus.handlers == []

    plugin.on_enable()

    assert plugin._subscribed is True
    assert fake_bus.handlers == [plugin._on_admin_message]


def test_hdhive_request_search_helper_uses_existing_tmdb_select_flow(monkeypatch):
    module, plugin = _build_plugin(monkeypatch, "app.plugins.hdhive.plugin", "HDHivePlugin")
    calls = []

    def fake_search_tmdb_select(search_key, res_type, tmdb_id, chat_id, platform):
        calls.append((search_key, res_type, tmdb_id, chat_id, platform))

    monkeypatch.setattr(plugin, "_search_tmdb_select", fake_search_tmdb_select)

    module._search_hdhive_for_request(plugin, 12345, "tv", "Series One", "chat-1", "tg")

    assert len(calls) == 1
    search_key, res_type, tmdb_id, chat_id, platform = calls[0]
    assert (res_type, tmdb_id, chat_id, platform) == ("tv", 12345, "chat-1", "tg")
    assert module._tmdb_cache[search_key]["results"] == [{
        "type": "tv",
        "tmdb_id": 12345,
        "title": "Series One",
        "year": "",
    }]
