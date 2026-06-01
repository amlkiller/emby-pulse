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
