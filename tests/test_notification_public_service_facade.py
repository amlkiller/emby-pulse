import ast
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]


class FakeBot:
    def __init__(self):
        self.calls = []

    def send_message(self, chat_id, text, parse_mode="HTML", reply_markup=None, platform="all"):
        self.calls.append(("send_message", chat_id, text, parse_mode, reply_markup, platform))
        return "message-result"

    def send_photo(
        self,
        chat_id,
        photo_io,
        caption,
        parse_mode="HTML",
        reply_markup=None,
        platform="all",
        wecom_photo_io=None,
    ):
        self.calls.append(
            (
                "send_photo",
                chat_id,
                photo_io,
                caption,
                parse_mode,
                reply_markup,
                platform,
                wecom_photo_io,
            )
        )
        return "photo-result"

    def edit_message(self, chat_id, message_id, text, parse_mode="HTML", reply_markup=None, platform="tg"):
        self.calls.append(("edit_message", chat_id, message_id, text, parse_mode, reply_markup, platform))
        return "edit-result"

    def send_to_channels(self, photo_io, caption, keyboard=None):
        self.calls.append(("send_to_channels", photo_io, caption, keyboard))
        return "channels-result"

    def push_now(self, user_id, period, theme):
        self.calls.append(("push_now", user_id, period, theme))
        return "push-result"


class FakeUserBotService:
    def __init__(self):
        self.calls = []
        self.user_bot = SimpleNamespace(running=True)

    def _send(self, chat_id, text, reply_markup=None):
        self.calls.append(("_send", chat_id, text, reply_markup))
        return {"ok": True}


def test_notification_public_service_delegates_and_returns(monkeypatch):
    from app.domains.notifications import public_service

    bot = FakeBot()
    user_bot_service = FakeUserBotService()
    monkeypatch.setattr(public_service, "_get_bot", lambda: bot)
    monkeypatch.setattr(public_service, "_get_user_bot_service", lambda: user_bot_service)

    assert public_service.send_message("chat", "text", reply_markup={"k": "v"}, platform="tg") == "message-result"
    assert public_service.send_photo(
        "chat",
        "photo",
        "caption",
        reply_markup={"button": 1},
        platform="wecom",
        wecom_photo_io="wecom-photo",
    ) == "photo-result"
    assert public_service.edit_message("chat", 42, "edited", reply_markup={"inline": True}) == "edit-result"
    assert public_service.send_to_channels("poster", "caption", keyboard={"keyboard": True}) == "channels-result"
    assert public_service.push_report_now("user", "weekly", "dark") == "push-result"
    assert public_service.is_user_bot_running() is True
    assert public_service.send_user_bot_message("user-chat", "user text", {"inline": []}) == {"ok": True}

    assert bot.calls == [
        ("send_message", "chat", "text", "HTML", {"k": "v"}, "tg"),
        ("send_photo", "chat", "photo", "caption", "HTML", {"button": 1}, "wecom", "wecom-photo"),
        ("edit_message", "chat", 42, "edited", "HTML", {"inline": True}, "tg"),
        ("send_to_channels", "poster", "caption", {"keyboard": True}),
        ("push_now", "user", "weekly", "dark"),
    ]
    assert user_bot_service.calls == [("_send", "user-chat", "user text", {"inline": []})]


def test_notification_public_service_get_notify_rule_delegates(monkeypatch):
    from app.domains.notifications import notify_admin, public_service

    calls = []

    def fake_get_notify_rule(notify_type):
        calls.append(("get_notify_rule", notify_type))
        return {"notify_type": notify_type, "enabled": 1, "channels": ["tg_bot"]}

    monkeypatch.setattr(notify_admin, "get_notify_rule", fake_get_notify_rule)

    assert public_service.get_notify_rule("user_delete") == {
        "notify_type": "user_delete",
        "enabled": 1,
        "channels": ["tg_bot"],
    }
    assert calls == [("get_notify_rule", "user_delete")]


def test_auto_expire_plugin_does_not_import_private_notification_user_bot_service():
    path = _REPO_ROOT / "app/plugins/auto_expire/plugin.py"
    rel_path = path.relative_to(_REPO_ROOT).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(rel_path))
    violations = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names = {alias.name for alias in node.names}
            if node.module == "app.domains.notifications.user_bot_service":
                violations.append(f"{rel_path}:{node.lineno}")
            if node.module == "app.domains.notifications" and (
                "user_bot_service" in imported_names or "*" in imported_names
            ):
                violations.append(f"{rel_path}:{node.lineno}")
        elif isinstance(node, ast.Import):
            imported_modules = {alias.name for alias in node.names}
            if "app.domains.notifications.user_bot_service" in imported_modules:
                violations.append(f"{rel_path}:{node.lineno}")

    assert violations == []


def test_external_callers_do_not_import_notification_bot_singleton():
    checked_roots = [
        _REPO_ROOT / "app/domains",
        _REPO_ROOT / "app/plugins",
    ]
    violations = []

    for root in checked_roots:
        for path in root.rglob("*.py"):
            rel_path = path.relative_to(_REPO_ROOT).as_posix()
            if rel_path.startswith("app/domains/notifications/"):
                continue

            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(rel_path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom):
                    continue
                if node.module != "app.domains.notifications.bot_service":
                    continue
                imported_names = {alias.name for alias in node.names}
                if "bot" in imported_names or "*" in imported_names:
                    violations.append(f"{rel_path}:{node.lineno}")

    assert violations == []
