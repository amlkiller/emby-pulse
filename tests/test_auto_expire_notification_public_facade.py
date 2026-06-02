import importlib
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _build_plugin(monkeypatch):
    from app.plugins.base import PluginBase

    monkeypatch.setattr(PluginBase, "_init_logs_table", lambda self: None)
    monkeypatch.setattr(PluginBase, "_load_config_to_cache", lambda self: None)

    module = importlib.import_module("app.plugins.auto_expire.plugin")
    monkeypatch.setattr(module.AutoExpirePlugin, "_setup_routes", lambda self: None)
    return module, module.AutoExpirePlugin()


def test_auto_expire_user_reminder_uses_notification_public_facade(monkeypatch):
    module, plugin = _build_plugin(monkeypatch)

    calls = []
    monkeypatch.setattr(
        module.user_service,
        "get_tg_user_id_by_emby_id",
        lambda user_id: calls.append(("lookup", user_id)) or "tg-1",
    )
    monkeypatch.setattr(
        module.notification_service,
        "is_user_bot_running",
        lambda: calls.append(("is_user_bot_running",)) or True,
    )
    monkeypatch.setattr(
        module.notification_service,
        "send_user_bot_message",
        lambda chat_id, text: calls.append(("send_user_bot_message", chat_id, text)),
    )

    assert plugin._send_user_remind("u1", 3, "2026-06-05") is None

    assert calls[0] == ("is_user_bot_running",)
    assert calls[1] == ("lookup", "u1")
    assert calls[2][0:2] == ("send_user_bot_message", "tg-1")
    assert "账号到期提醒" in calls[2][2]
    assert "2026-06-05" in calls[2][2]


def test_auto_expire_user_reminder_skips_when_user_bot_stopped(monkeypatch):
    module, plugin = _build_plugin(monkeypatch)

    calls = []
    monkeypatch.setattr(
        module.user_service,
        "get_tg_user_id_by_emby_id",
        lambda user_id: calls.append(("lookup", user_id)) or "tg-1",
    )
    monkeypatch.setattr(module.notification_service, "is_user_bot_running", lambda: False)
    monkeypatch.setattr(
        module.notification_service,
        "send_user_bot_message",
        lambda chat_id, text: calls.append(("send_user_bot_message", chat_id, text)),
    )

    assert plugin._send_user_remind("u1", 3, "2026-06-05") is None
    assert calls == []
