import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.bot.notification_bot import bot_service


class FakeTelegramClient:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def post_api(self, token, method, json=None, proxies=None, timeout=None):
        self.calls.append((token, method, json, proxies, timeout))
        if self.error:
            raise self.error
        return {"ok": True}


def test_set_commands_skips_telegram_call_when_token_missing(monkeypatch):
    telegram = FakeTelegramClient()
    monkeypatch.setattr(bot_service, "get_notify_tg_bot_token", lambda: "")
    monkeypatch.setattr(bot_service, "telegram_client", telegram)

    bot_service.NotificationBot()._set_commands()

    assert telegram.calls == []


def test_set_commands_registers_existing_command_list_through_legacy_entry(monkeypatch):
    telegram = FakeTelegramClient()
    proxies = {"https": "http://proxy.local:8080"}
    monkeypatch.setattr(bot_service, "get_notify_tg_bot_token", lambda: "tg-token")
    monkeypatch.setattr(bot_service, "get_safe_proxies", lambda: proxies)
    monkeypatch.setattr(bot_service, "telegram_client", telegram)

    bot_service.NotificationBot()._set_commands()

    assert len(telegram.calls) == 1
    token, method, payload, seen_proxies, timeout = telegram.calls[0]
    assert token == "tg-token"
    assert method == "setMyCommands"
    assert seen_proxies == proxies
    assert timeout == 10

    commands = payload["commands"]
    assert [command["command"] for command in commands] == [
        "search",
        "stats",
        "weekly",
        "monthly",
        "yearly",
        "now",
        "latest",
        "recent",
        "check",
        "calendar",
        "emby_restart",
        "whois",
        "help",
    ]
    assert commands[0]["description"] == "🔍 搜索资源"
    assert commands[-1]["description"] == "🤖 帮助菜单"


def test_set_commands_swallows_registration_errors(monkeypatch):
    telegram = FakeTelegramClient(error=RuntimeError("telegram down"))
    monkeypatch.setattr(bot_service, "get_notify_tg_bot_token", lambda: "tg-token")
    monkeypatch.setattr(bot_service, "get_safe_proxies", lambda: None)
    monkeypatch.setattr(bot_service, "telegram_client", telegram)

    bot_service.NotificationBot()._set_commands()

    assert len(telegram.calls) == 1
