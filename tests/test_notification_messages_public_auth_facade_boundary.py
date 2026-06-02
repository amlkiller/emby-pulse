import ast
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_notification_messages_does_not_import_private_users_auth():
    path = _REPO_ROOT / "app/domains/notifications/messages.py"
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


def test_get_conversations_denies_non_admin_before_dao_or_media_side_effects(monkeypatch):
    from app.domains.notifications import messages as notification_messages

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_ensure_msg_tables():
        raise AssertionError("message tables should not be ensured without admin permission")

    def fail_list_conversations(*args, **kwargs):
        raise AssertionError("conversations should not be listed without admin permission")

    def fail_count_conversations():
        raise AssertionError("conversations should not be counted without admin permission")

    media_api = SimpleNamespace(
        host="http://emby",
        api_key="token",
        get=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("media users should not be read without admin permission")
        ),
    )

    monkeypatch.setattr(notification_messages.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(notification_messages, "_ensure_msg_tables", fail_ensure_msg_tables)
    monkeypatch.setattr(notification_messages, "list_conversations", fail_list_conversations)
    monkeypatch.setattr(notification_messages, "count_conversations", fail_count_conversations)
    monkeypatch.setattr(notification_messages, "media_api", media_api)

    response = notification_messages.get_conversations(request)

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]


def test_get_conversations_allows_admin_through_public_facade(monkeypatch):
    from app.domains.notifications import messages as notification_messages

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    calls = []

    class MediaResponse:
        status_code = 200

        def json(self):
            calls.append(("media_json",))
            return [{"Id": "u1"}]

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_ensure_msg_tables():
        calls.append(("_ensure_msg_tables",))

    def fake_list_conversations(limit, offset):
        calls.append(("list_conversations", limit, offset))
        return [{"id": 7, "user_id": "u1", "username": "Alice", "user_avatar": "", "user_remark": ""}]

    def fake_count_conversations():
        calls.append(("count_conversations",))
        return 1

    def fake_media_get(path):
        calls.append(("media_get", path))
        return MediaResponse()

    def fake_get_local_user_profile_by_emby_id(user_id):
        calls.append(("get_local_user_profile_by_emby_id", user_id))
        return {"avatar": "/avatar/u1.jpg", "remark": "Alice Remark"}

    def fail_get_user_meta_remark(*args, **kwargs):
        raise AssertionError("users_meta remark should not be read when local remark exists")

    media_api = SimpleNamespace(host="http://emby", api_key="token", get=fake_media_get)

    monkeypatch.setattr(notification_messages.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(notification_messages, "_ensure_msg_tables", fake_ensure_msg_tables)
    monkeypatch.setattr(notification_messages, "list_conversations", fake_list_conversations)
    monkeypatch.setattr(notification_messages, "count_conversations", fake_count_conversations)
    monkeypatch.setattr(notification_messages, "get_local_user_profile_by_emby_id", fake_get_local_user_profile_by_emby_id)
    monkeypatch.setattr(notification_messages, "get_user_meta_remark", fail_get_user_meta_remark)
    monkeypatch.setattr(notification_messages, "media_api", media_api)

    response = notification_messages.get_conversations(request, page=2, limit=5)

    assert response == {
        "status": "success",
        "data": [
            {
                "id": 7,
                "user_id": "u1",
                "username": "Alice",
                "user_avatar": "/avatar/u1.jpg",
                "user_remark": "Alice Remark",
                "user_deleted": False,
                "pinned": False,
            }
        ],
        "total": 1,
        "page": 2,
        "limit": 5,
    }
    assert calls == [
        ("is_admin_user", request),
        ("_ensure_msg_tables",),
        ("list_conversations", 5, 5),
        ("count_conversations",),
        ("media_get", "/Users"),
        ("media_json",),
        ("get_local_user_profile_by_emby_id", "u1"),
    ]


def test_get_msg_bot_config_denies_non_admin_before_config_reads(monkeypatch):
    from app.domains.notifications import messages as notification_messages

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_is_message_bot_notify_enabled():
        raise AssertionError("bot notify config should not be read without admin permission")

    def fail_is_message_bot_reply_enabled():
        raise AssertionError("bot reply config should not be read without admin permission")

    def fail_is_user_bot_configured():
        raise AssertionError("user bot config should not be read without admin permission")

    monkeypatch.setattr(notification_messages.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(notification_messages, "is_message_bot_notify_enabled", fail_is_message_bot_notify_enabled)
    monkeypatch.setattr(notification_messages, "is_message_bot_reply_enabled", fail_is_message_bot_reply_enabled)
    monkeypatch.setattr(notification_messages, "is_user_bot_configured", fail_is_user_bot_configured)

    response = notification_messages.get_msg_bot_config(request)

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]
