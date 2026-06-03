import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import app.plugins as app_plugins
from app.bot.notification_bot import bot_service
from app.bot.notification_bot import notification_bot_emby_restart_command_service


class FakeLogger:
    def __init__(self):
        self.errors = []
        self.infos = []

    def error(self, message):
        self.errors.append(message)

    def info(self, message):
        self.infos.append(message)


class FakePlugin:
    def __init__(self, enabled=True, manual_result=None, single_result=None, single_error=None):
        self.enabled = enabled
        self.manual_result = manual_result or {"success": True, "message": "全部完成"}
        self.single_result = single_result or {"success": True, "message": "单台完成"}
        self.single_error = single_error
        self.manual_restart_calls = 0
        self.restart_calls = []

    def manual_restart(self):
        self.manual_restart_calls += 1
        return self.manual_result

    def _restart_via_emby_api(self, host, api_key):
        self.restart_calls.append((host, api_key))
        if self.single_error:
            raise self.single_error
        return self.single_result


class FakeTelegramClient:
    def __init__(self):
        self.calls = []

    def post_api(self, token, method, json=None, proxies=None, timeout=None):
        self.calls.append((token, method, json, proxies, timeout))


def _capture_bot_messages():
    bot = bot_service.NotificationBot()
    sent = []
    bot.send_message = lambda chat_id, text, parse_mode="HTML", reply_markup=None, platform="all": sent.append(
        (chat_id, text, parse_mode, reply_markup, platform)
    )
    return bot, sent


def _patch_plugins(monkeypatch, plugin, config=None):
    config = config if config is not None else {}
    monkeypatch.setattr(app_plugins, "get_plugin", lambda plugin_id: plugin)
    monkeypatch.setattr(app_plugins, "get_plugin_config", lambda plugin_id: config)


def _patch_callback_ack(monkeypatch):
    telegram = FakeTelegramClient()
    monkeypatch.setattr(bot_service, "telegram_client", telegram)
    monkeypatch.setattr(bot_service, "get_notify_tg_bot_token", lambda: "token-1")
    monkeypatch.setattr(bot_service, "get_safe_proxies", lambda: {"https": "proxy"})
    return telegram


def _callback(data):
    return {
        "id": "cq-1",
        "data": data,
        "message": {"message_id": 101, "chat": {"id": "chat-1"}},
    }


def test_cmd_emby_restart_disabled_or_missing_plugin_uses_legacy_dynamic_plugin_lookup(monkeypatch):
    _patch_plugins(monkeypatch, None)
    bot, sent = _capture_bot_messages()

    bot._cmd_emby_restart("chat-1", "/emby_restart", "tg")

    assert sent == [("chat-1", "❌ Emby 自动重启插件未启用", "HTML", None, "tg")]

    _patch_plugins(monkeypatch, FakePlugin(enabled=False))
    bot, sent = _capture_bot_messages()

    bot._cmd_emby_restart("chat-1", "/emby_restart", "wecom")

    assert sent == [("chat-1", "❌ Emby 自动重启插件未启用", "HTML", None, "wecom")]


def test_cmd_emby_restart_empty_server_config(monkeypatch):
    _patch_plugins(monkeypatch, FakePlugin(), {"servers": []})
    bot, sent = _capture_bot_messages()

    bot._cmd_emby_restart("chat-1", "/emby_restart", "tg")

    assert sent == [("chat-1", "❌ 未配置 Emby 服务器，请先在插件面板中添加服务器", "HTML", None, "tg")]


def test_cmd_emby_restart_renders_server_list_and_keyboard(monkeypatch):
    servers = [
        {"name": "AlphaServerLongName", "host": "http://a", "api_key": "key-a"},
        {"name": "Beta", "host": "http://b", "api_key": "key-b"},
        {"host": "http://c", "api_key": "key-c"},
    ]
    _patch_plugins(monkeypatch, FakePlugin(), {"servers": servers})
    bot, sent = _capture_bot_messages()

    bot._cmd_emby_restart("chat-1", "/emby_restart", "tg")

    assert sent == [
        (
            "chat-1",
            (
                "🖥️ <b>Emby 服务器管理</b>\n\n请选择要重启的服务器：\n"
                "\n<b>1.</b> AlphaServerLongName"
                "\n<b>2.</b> Beta"
                "\n<b>3.</b> 未命名"
                "\n\n💡 点击下方按钮重启对应服务器"
            ),
            "HTML",
            {
                "inline_keyboard": [
                    [
                        {"text": "🔄 AlphaSer", "callback_data": "emby_restart:0"},
                        {"text": "🔄 Beta", "callback_data": "emby_restart:1"},
                    ],
                    [{"text": "🔄 未命名", "callback_data": "emby_restart:2"}],
                    [{"text": "🔄 重启全部服务器", "callback_data": "emby_restart:all"}],
                ]
            },
            "tg",
        )
    ]


def test_handle_callback_restart_all_uses_dispatcher_and_reports_success(monkeypatch):
    plugin = FakePlugin(manual_result={"success": True, "message": "已提交全部重启"})
    _patch_plugins(monkeypatch, plugin, {"servers": [{"name": "Alpha"}, {"name": "Beta"}]})
    telegram = _patch_callback_ack(monkeypatch)
    bot, sent = _capture_bot_messages()

    bot._handle_callback(_callback("emby_restart:all"))

    assert telegram.calls == [
        ("token-1", "answerCallbackQuery", {"callback_query_id": "cq-1"}, {"https": "proxy"}, 5)
    ]
    assert plugin.manual_restart_calls == 1
    assert sent == [
        ("chat-1", "🔄 正在重启全部 2 台 Emby 服务器...", "HTML", None, "tg"),
        ("chat-1", "✅ 已提交全部重启", "HTML", None, "tg"),
    ]


def test_handle_callback_restart_all_reports_failure(monkeypatch):
    plugin = FakePlugin(manual_result={"success": False, "message": "全部失败"})
    _patch_plugins(monkeypatch, plugin, {"servers": [{"name": "Alpha"}]})
    _patch_callback_ack(monkeypatch)
    bot, sent = _capture_bot_messages()

    bot._handle_callback(_callback("emby_restart:all"))

    assert sent == [
        ("chat-1", "🔄 正在重启全部 1 台 Emby 服务器...", "HTML", None, "tg"),
        ("chat-1", "❌ 全部失败", "HTML", None, "tg"),
    ]


def test_handle_callback_single_server_success_and_failure(monkeypatch):
    servers = [{"name": "Alpha", "host": "http://a", "api_key": "key-a"}]
    plugin = FakePlugin(single_result={"success": True})
    _patch_plugins(monkeypatch, plugin, {"servers": servers})
    _patch_callback_ack(monkeypatch)
    bot, sent = _capture_bot_messages()

    bot._handle_callback(_callback("emby_restart:0"))

    assert plugin.restart_calls == [("http://a", "key-a")]
    assert sent == [
        ("chat-1", "🔄 正在重启服务器 [Alpha]...", "HTML", None, "tg"),
        ("chat-1", "✅ 服务器 [Alpha] 重启成功", "HTML", None, "tg"),
    ]

    plugin = FakePlugin(single_result={"success": False, "message": "api error"})
    _patch_plugins(monkeypatch, plugin, {"servers": servers})
    _patch_callback_ack(monkeypatch)
    bot, sent = _capture_bot_messages()

    bot._handle_callback(_callback("emby_restart:0"))

    assert plugin.restart_calls == [("http://a", "key-a")]
    assert sent == [
        ("chat-1", "🔄 正在重启服务器 [Alpha]...", "HTML", None, "tg"),
        ("chat-1", "❌ 服务器 [Alpha] 重启失败: api error", "HTML", None, "tg"),
    ]


def test_handle_callback_invalid_index(monkeypatch):
    plugin = FakePlugin()
    _patch_plugins(monkeypatch, plugin, {"servers": [{"name": "Alpha"}]})
    _patch_callback_ack(monkeypatch)
    bot, sent = _capture_bot_messages()

    bot._handle_callback(_callback("emby_restart:4"))

    assert plugin.restart_calls == []
    assert sent == [("chat-1", "❌ 服务器不存在", "HTML", None, "tg")]


def test_handle_callback_exception_logs_with_current_bot_service_logger(monkeypatch):
    logger = FakeLogger()
    monkeypatch.setattr(bot_service, "logger", logger)
    plugin = FakePlugin(single_error=RuntimeError("restart exploded"))
    _patch_plugins(monkeypatch, plugin, {"servers": [{"name": "Alpha", "host": "http://a", "api_key": "key-a"}]})
    _patch_callback_ack(monkeypatch)
    bot, sent = _capture_bot_messages()

    bot._handle_callback(_callback("emby_restart:0"))

    assert logger.errors == ["[Bot] emby_restart callback error: restart exploded"]
    assert sent == [
        ("chat-1", "🔄 正在重启服务器 [Alpha]...", "HTML", None, "tg"),
        ("chat-1", "❌ 执行失败: restart exploded", "HTML", None, "tg"),
    ]


def test_service_private_provider_can_be_reset_to_legacy_dynamic_import(monkeypatch):
    notification_bot_emby_restart_command_service.set_dependency_providers(
        get_plugin_provider=lambda: notification_bot_emby_restart_command_service._default_get_plugin,
        get_plugin_config_provider=lambda: notification_bot_emby_restart_command_service._default_get_plugin_config,
    )
    _patch_plugins(monkeypatch, FakePlugin(), {"servers": []})
    bot, sent = _capture_bot_messages()

    bot._cmd_emby_restart("chat-1", "/emby_restart", "tg")

    assert sent == [("chat-1", "❌ 未配置 Emby 服务器，请先在插件面板中添加服务器", "HTML", None, "tg")]
