import ast
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_risk_service_does_not_import_private_notification_user_bot_service():
    path = _REPO_ROOT / "app/domains/risk/risk_service.py"
    rel_path = path.relative_to(_REPO_ROOT).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(rel_path))
    violations = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names = {alias.name for alias in node.names}
            if node.module == "app.bot.user_bot.user_bot_service":
                violations.append(f"{rel_path}:{node.lineno}")
            if node.module == "app.bot.user_bot" and (
                "user_bot_service" in imported_names or "*" in imported_names
            ):
                violations.append(f"{rel_path}:{node.lineno}")
        elif isinstance(node, ast.Import):
            imported_modules = {alias.name for alias in node.names}
            if "app.bot.user_bot.user_bot_service" in imported_modules:
                violations.append(f"{rel_path}:{node.lineno}")

    assert violations == []


def test_send_user_warning_uses_notification_public_facade(monkeypatch):
    from app.domains.risk import risk_service

    calls = []

    monkeypatch.setattr(
        risk_service,
        "get_tg_user_id_for_emby_user",
        lambda user_id: calls.append(("get_tg_user_id", user_id)) or "tg-1",
    )
    monkeypatch.setattr(
        risk_service.notification_service,
        "send_user_bot_message",
        lambda chat_id, text: calls.append(("send_user_bot_message", chat_id, text)),
    )

    risk_service._send_user_warning("emby-1", "User One", 3, 1, ["TV", "Phone"])

    assert calls[0] == ("get_tg_user_id", "emby-1")
    assert calls[1][0:2] == ("send_user_bot_message", "tg-1")
    assert "User One" in calls[1][2]
    assert "3" in calls[1][2]
    assert "TV" in calls[1][2]
    assert "Phone" in calls[1][2]


def test_send_user_ban_notify_uses_notification_public_facade(monkeypatch):
    from app.domains.risk import risk_service

    calls = []

    monkeypatch.setattr(
        risk_service,
        "get_tg_user_id_for_emby_user",
        lambda user_id: calls.append(("get_tg_user_id", user_id)) or "tg-2",
    )
    monkeypatch.setattr(
        risk_service.notification_service,
        "send_user_bot_message",
        lambda chat_id, text: calls.append(("send_user_bot_message", chat_id, text)),
    )

    risk_service._send_user_ban_notify("emby-2", "User Two", 4, 2, ["Tablet"])

    assert calls[0] == ("get_tg_user_id", "emby-2")
    assert calls[1][0:2] == ("send_user_bot_message", "tg-2")
    assert "User Two" in calls[1][2]
    assert "4" in calls[1][2]
    assert "2" in calls[1][2]
    assert "Tablet" in calls[1][2]


def test_user_risk_notification_skips_public_send_without_tg_binding(monkeypatch):
    from app.domains.risk import risk_service

    calls = []

    monkeypatch.setattr(
        risk_service,
        "get_tg_user_id_for_emby_user",
        lambda user_id: calls.append(("get_tg_user_id", user_id)) or None,
    )
    monkeypatch.setattr(
        risk_service.notification_service,
        "send_user_bot_message",
        lambda *args: calls.append(("send_user_bot_message", args)),
    )

    risk_service._send_user_warning("emby-1", "User One", 3, 1, ["TV"])
    risk_service._send_user_ban_notify("emby-2", "User Two", 4, 2, ["Tablet"])

    assert calls == [
        ("get_tg_user_id", "emby-1"),
        ("get_tg_user_id", "emby-2"),
    ]
