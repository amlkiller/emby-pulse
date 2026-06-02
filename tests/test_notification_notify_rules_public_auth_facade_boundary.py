import ast
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_notification_notify_rules_does_not_import_private_users_auth():
    path = _REPO_ROOT / "app/domains/notifications/notify_rules.py"
    rel_path = path.relative_to(_REPO_ROOT).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(rel_path))
    violations = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names = {alias.name for alias in node.names}
            if node.module == "app.domains.users.auth":
                violations.append(f"{rel_path}:{node.lineno}")
            if node.module == "app.domains.users" and ("auth" in imported_names or "*" in imported_names):
                violations.append(f"{rel_path}:{node.lineno}")
        elif isinstance(node, ast.Import):
            imported_modules = {alias.name for alias in node.names}
            if "app.domains.users.auth" in imported_modules:
                violations.append(f"{rel_path}:{node.lineno}")

    assert violations == []


def test_get_emby_users_denies_non_admin_before_media_call(monkeypatch):
    from app.domains.notifications import notify_rules

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_media_get(*args, **kwargs):
        raise AssertionError("media server users should not be read without admin permission")

    monkeypatch.setattr(notify_rules.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(notify_rules.media_api, "get", fail_media_get)

    response = asyncio.run(notify_rules.get_emby_users(request))

    assert response == {"success": False, "data": [], "error": "需要管理员权限"}
    assert calls == [request]


def test_get_mutes_allows_admin_through_public_facade(monkeypatch):
    from app.domains.notifications import notify_rules

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_list_bot_notify_mutes():
        calls.append(("list_bot_notify_mutes",))
        return [
            {"user_id": "u1", "event_type": "playback"},
            {"user_id": "u2", "event_type": "login"},
        ]

    monkeypatch.setattr(notify_rules.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(notify_rules, "list_bot_notify_mutes", fake_list_bot_notify_mutes)

    response = asyncio.run(notify_rules.get_mutes(request))

    assert response == {
        "success": True,
        "data": {"playback": ["u1"], "login": ["u2"]},
    }
    assert calls == [
        ("is_admin_user", request),
        ("list_bot_notify_mutes",),
    ]


def test_save_mutes_denies_non_admin_before_body_and_write(monkeypatch):
    from app.domains.notifications import notify_rules

    class RequestWithFailingJson:
        session = {"user": {"Id": "u1"}}

        async def json(self):
            raise AssertionError("request body should not be read without admin permission")

    request = RequestWithFailingJson()
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_replace_bot_notify_mutes(*args, **kwargs):
        raise AssertionError("mute rules should not be written without admin permission")

    monkeypatch.setattr(notify_rules.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(notify_rules, "replace_bot_notify_mutes", fail_replace_bot_notify_mutes)

    response = asyncio.run(notify_rules.save_mutes(request))

    assert response == {"success": False, "msg": "需要管理员权限"}
    assert calls == [request]


def test_save_mutes_allows_admin_through_public_facade(monkeypatch):
    from app.domains.notifications import notify_rules

    class RequestWithJson:
        session = {"user": {"Id": "admin"}}

        async def json(self):
            return {"playback": ["u1"], "login": ["u2"]}

    request = RequestWithJson()
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_replace_bot_notify_mutes(playback_users, login_users):
        calls.append(("replace_bot_notify_mutes", playback_users, login_users))

    monkeypatch.setattr(notify_rules.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(notify_rules, "replace_bot_notify_mutes", fake_replace_bot_notify_mutes)

    response = asyncio.run(notify_rules.save_mutes(request))

    assert response == {"success": True, "msg": "降噪规则保存成功！新规即刻生效。"}
    assert calls == [
        ("is_admin_user", request),
        ("replace_bot_notify_mutes", ["u1"], ["u2"]),
    ]
