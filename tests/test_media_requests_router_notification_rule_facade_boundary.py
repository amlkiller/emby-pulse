import asyncio
import ast
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class AsyncJsonRequest:
    def __init__(self, payload, session=None, base_url="http://127.0.0.1:10308"):
        self._payload = payload
        self.session = session or {}
        self.base_url = base_url

    async def json(self):
        return self._payload


class FakeMediaResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


class FakeMediaApi:
    def __init__(self, calls):
        self.calls = calls

    def get(self, path, timeout=None):
        self.calls.append(("media_get", path, timeout))
        if path == "/Users":
            return FakeMediaResponse(payload=[])
        return FakeMediaResponse(payload={"Policy": {}})

    def post(self, path, json=None, timeout=None):
        self.calls.append(("media_post", path, json, timeout))
        if path == "/Users/New":
            return FakeMediaResponse(status_code=200, payload={"Id": "user-1"})
        return FakeMediaResponse(status_code=204, payload={})


def _assert_imports_notification_notify_admin(path):
    rel_path = path.relative_to(_REPO_ROOT).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(rel_path))
    imports_notify_admin = False

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names = {alias.name for alias in node.names}
            if node.module == "app.domains.notifications" and "notify_admin" in imported_names:
                imports_notify_admin = True
        elif isinstance(node, ast.Import):
            imported_modules = {alias.name for alias in node.names}
            if "app.domains.notifications.notify_admin" in imported_modules:
                imports_notify_admin = True

    assert imports_notify_admin is True


def _assert_no_private_notification_user_bot_import(path):
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


def test_media_requests_router_imports_notification_rule_owner_directly():
    _assert_imports_notification_notify_admin(_REPO_ROOT / "app/domains/media_requests/router.py")


def test_media_requests_router_does_not_import_private_notification_user_bot_service():
    _assert_no_private_notification_user_bot_import(_REPO_ROOT / "app/domains/media_requests/router.py")


def test_submit_media_request_uses_public_rule_before_notifications(monkeypatch):
    from app.domains.media_requests import router as media_requests_router

    calls = []
    request = AsyncJsonRequest(
        {
            "tmdb_id": 100,
            "media_type": "movie",
            "title": "Movie One",
            "year": "2026",
            "poster_path": "/poster.jpg",
        },
        session={"req_user": {"Id": "user-1", "Name": "User One"}},
    )

    def fake_get_notify_rule(notify_type):
        calls.append(("get_notify_rule", notify_type))
        return {"enabled": 1, "channels": ["tg_bot", "web"]}

    def fake_send_photo(*args, **kwargs):
        calls.append(("send_photo", args, kwargs))

    def fake_add_system_notification(*args, **kwargs):
        calls.append(("add_system_notification", args, kwargs))

    monkeypatch.setattr(media_requests_router, "_check_user_exists", lambda user_id: True)
    monkeypatch.setattr(
        media_requests_router,
        "submit_new_media_request",
        lambda *args: calls.append(("submit_new_media_request", args)) or {"ok": True},
    )
    monkeypatch.setattr(media_requests_router, "get_pulse_url", lambda: "http://pulse.local")
    monkeypatch.setattr(media_requests_router.notify_admin, "get_notify_rule", fake_get_notify_rule)
    monkeypatch.setattr(media_requests_router.notification_service, "send_photo", fake_send_photo)
    monkeypatch.setattr(media_requests_router, "add_system_notification", fake_add_system_notification)

    response = asyncio.run(media_requests_router.submit_media_request(request))

    assert response == {"status": "success", "message": "心愿已提交！系统将尽快处理您的请求。"}
    assert calls.index(("get_notify_rule", "request_new")) < next(
        index for index, call in enumerate(calls) if call[0] == "send_photo"
    )
    assert calls.index(("get_notify_rule", "request_new")) < next(
        index for index, call in enumerate(calls) if call[0] == "add_system_notification"
    )
    send_photo_call = next(call for call in calls if call[0] == "send_photo")
    assert send_photo_call[2]["platform"] == "tg"


def test_batch_manage_action_uses_public_rule_before_status_notify_queries(monkeypatch):
    from app.domains.media_requests import router as media_requests_router

    calls = []
    request = SimpleNamespace(session={"user": {"Id": "admin"}})

    def fake_get_notify_rule(notify_type):
        calls.append(("get_notify_rule", notify_type))
        return {"enabled": 1, "channels": ["tg_bot"]}

    def fake_list_request_status_notify_items(items):
        calls.append(("list_request_status_notify_items", items))
        return [], []

    monkeypatch.setattr(media_requests_router.user_service, "is_admin_user", lambda request: True)
    monkeypatch.setattr(media_requests_router, "get_media_request", lambda *args: None)
    monkeypatch.setattr(media_requests_router, "get_moviepilot_url", lambda: None)
    monkeypatch.setattr(
        media_requests_router,
        "update_media_request_status",
        lambda *args: calls.append(("update_media_request_status", args)),
    )
    monkeypatch.setattr(media_requests_router.notify_admin, "get_notify_rule", fake_get_notify_rule)
    monkeypatch.setattr(
        media_requests_router,
        "list_request_status_notify_items",
        fake_list_request_status_notify_items,
    )
    monkeypatch.setattr(
        media_requests_router,
        "list_tg_bindings",
        lambda user_ids: calls.append(("list_tg_bindings", user_ids)) or {},
    )

    data = media_requests_router.BulkAdminActionModel(
        items=[{"tmdb_id": 100, "season": 0}],
        action="approve",
    )
    response = media_requests_router.batch_manage_action(data, request)

    assert response == {"status": "success", "message": "操作已执行"}
    assert calls.index(("get_notify_rule", "request_status")) < next(
        index for index, call in enumerate(calls) if call[0] == "list_request_status_notify_items"
    )


def test_batch_manage_action_uses_public_user_bot_facade_for_status_notifications(monkeypatch):
    from app.domains.media_requests import router as media_requests_router

    calls = []
    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    notify_items = [
        {
            "tmdb_id": 100,
            "season": 0,
            "request": {
                "title": "Poster Movie",
                "year": "2026",
                "media_type": "movie",
                "season": 0,
                "episodes": "",
                "poster_path": "/poster.jpg",
            },
            "users": [{"user_id": "user-photo", "username": "Photo User"}],
        },
        {
            "tmdb_id": 200,
            "season": 1,
            "request": {
                "title": "Text Show",
                "year": "2025",
                "media_type": "tv",
                "season": 1,
                "episodes": "1,2",
                "poster_path": "",
            },
            "users": [
                {"user_id": "user-text", "username": "Text User"},
                {"user_id": "user-unbound", "username": "Unbound User"},
            ],
        },
    ]

    def fake_get_notify_rule(notify_type):
        calls.append(("get_notify_rule", notify_type))
        return {"enabled": 1, "channels": ["tg_bot"]}

    monkeypatch.setattr(media_requests_router.user_service, "is_admin_user", lambda request: True)
    monkeypatch.setattr(media_requests_router, "get_media_request", lambda *args: None)
    monkeypatch.setattr(media_requests_router, "get_moviepilot_url", lambda: None)
    monkeypatch.setattr(
        media_requests_router,
        "update_media_request_status",
        lambda *args: calls.append(("update_media_request_status", args)),
    )
    monkeypatch.setattr(media_requests_router.notify_admin, "get_notify_rule", fake_get_notify_rule)
    monkeypatch.setattr(
        media_requests_router,
        "list_request_status_notify_items",
        lambda items: calls.append(("list_request_status_notify_items", items))
        or (notify_items, ["user-photo", "user-text", "user-unbound"]),
    )
    monkeypatch.setattr(
        media_requests_router,
        "list_tg_bindings",
        lambda user_ids: calls.append(("list_tg_bindings", user_ids))
        or {"user-photo": "123", "user-text": "456"},
    )
    monkeypatch.setattr(
        media_requests_router.notification_service,
        "send_user_bot_photo",
        lambda *args, **kwargs: calls.append(("send_user_bot_photo", args, kwargs)),
    )
    monkeypatch.setattr(
        media_requests_router.notification_service,
        "send_user_bot_message",
        lambda *args, **kwargs: calls.append(("send_user_bot_message", args, kwargs)),
    )

    data = media_requests_router.BulkAdminActionModel(
        items=[{"tmdb_id": 100, "season": 0}, {"tmdb_id": 200, "season": 1}],
        action="approve",
    )
    response = media_requests_router.batch_manage_action(data, request)

    assert response == {"status": "success", "message": "操作已执行"}
    send_calls = [call for call in calls if call[0].startswith("send_user_bot_")]
    assert len(send_calls) == 2
    assert send_calls[0] == (
        "send_user_bot_photo",
        (
            123,
            "https://image.tmdb.org/t/p/w300/poster.jpg",
            "🚀 <b>求片状态更新</b>\n\n📺 <b>内容：</b>Poster Movie (2026)\n📢 <b>状态：</b>审批通过，正在下载中",
        ),
        {},
    )
    assert send_calls[1] == (
        "send_user_bot_message",
        (
            456,
            "🚀 <b>求片状态更新</b>\n\n📺 <b>内容：</b>Text Show S1E1-2 (2025)\n📢 <b>状态：</b>审批通过，正在下载中",
        ),
        {},
    )


def test_submit_feedback_uses_public_rule_before_notifications(monkeypatch):
    from app.domains.media_requests import router as media_requests_router

    calls = []
    request = SimpleNamespace(
        session={"req_user": {"Id": "user-1", "Name": "User One"}},
        base_url="http://127.0.0.1:10308",
    )

    def fake_get_notify_rule(notify_type):
        calls.append(("get_notify_rule", notify_type))
        return {"enabled": 1, "channels": ["wecom", "web"]}

    monkeypatch.setattr(media_requests_router, "_check_user_exists", lambda user_id: True)
    monkeypatch.setattr(
        media_requests_router,
        "create_media_feedback",
        lambda *args: calls.append(("create_media_feedback", args)) or 42,
    )
    monkeypatch.setattr(media_requests_router, "get_pulse_url", lambda: "http://pulse.local")
    monkeypatch.setattr(media_requests_router.notify_admin, "get_notify_rule", fake_get_notify_rule)
    monkeypatch.setattr(
        media_requests_router.notification_service,
        "send_photo",
        lambda *args, **kwargs: calls.append(("send_photo", args, kwargs)),
    )
    monkeypatch.setattr(
        media_requests_router,
        "add_system_notification",
        lambda *args, **kwargs: calls.append(("add_system_notification", args, kwargs)),
    )

    data = media_requests_router.FeedbackSubmitModel(
        item_name="Movie One",
        issue_type="bad_audio",
        description="Audio missing",
        poster_path="http://poster.local/poster.jpg",
    )
    response = media_requests_router.submit_feedback(data, request)

    assert response == {"status": "success", "message": "反馈已提交，感谢您的协助！"}
    assert calls.index(("get_notify_rule", "feedback_new")) < next(
        index for index, call in enumerate(calls) if call[0] == "send_photo"
    )
    assert calls.index(("get_notify_rule", "feedback_new")) < next(
        index for index, call in enumerate(calls) if call[0] == "add_system_notification"
    )
    send_photo_call = next(call for call in calls if call[0] == "send_photo")
    assert send_photo_call[2]["platform"] == "wecom"


def test_user_registration_uses_public_rule_and_preserves_disabled_rule_fallback(monkeypatch):
    from app.domains.media_requests import router as media_requests_router
    from app.domains.users import public_service as users_public_service
    from app.infra.db import notification_dao

    calls = []
    request = SimpleNamespace(session={})

    def fake_get_notify_rule(notify_type):
        calls.append(("get_notify_rule", notify_type))
        return {"enabled": 0, "channels": []}

    monkeypatch.setattr(media_requests_router, "media_api", FakeMediaApi(calls))
    monkeypatch.setattr(
        media_requests_router,
        "claim_registration_invitation",
        lambda code, safe_name: (
            {
                "days": 30,
                "template_user_id": None,
                "routes": "",
                "route_mode": "block",
                "req_free": 0,
                "req_free_count": -1,
            },
            None,
        ),
    )
    monkeypatch.setattr(
        media_requests_router,
        "save_registered_user_meta",
        lambda *args: calls.append(("save_registered_user_meta", args)),
    )
    monkeypatch.setattr(
        users_public_service,
        "invalidate_emby_users_cache",
        lambda: calls.append(("invalidate_emby_users_cache",)),
    )
    monkeypatch.setattr(media_requests_router.notify_admin, "get_notify_rule", fake_get_notify_rule)
    monkeypatch.setattr(
        media_requests_router.notification_service,
        "send_message",
        lambda *args, **kwargs: calls.append(("send_message", args, kwargs)),
    )
    monkeypatch.setattr(
        notification_dao,
        "add_system_notification",
        lambda *args, **kwargs: calls.append(("add_system_notification", args, kwargs)),
    )
    monkeypatch.setattr(media_requests_router, "get_media_server_user_routes", lambda uid: [])
    monkeypatch.setattr(media_requests_router, "get_media_server_main_public_or_host", lambda: "http://emby.local")
    monkeypatch.setattr(media_requests_router, "get_media_server_welcome_message", lambda: "welcome")

    data = media_requests_router.UserRegisterModel(
        code="INVITE1",
        username="userone",
        password="StrongPass123!",
    )
    response = asyncio.run(media_requests_router.user_community_register(data, request))

    assert response["status"] == "success"
    assert request.session["req_user"] == {"Id": "user-1", "Name": "userone"}
    assert calls.index(("get_notify_rule", "user_register")) < next(
        index for index, call in enumerate(calls) if call[0] == "send_message"
    )
    assert calls.index(("get_notify_rule", "user_register")) < next(
        index for index, call in enumerate(calls) if call[0] == "add_system_notification"
    )
    send_message_call = next(call for call in calls if call[0] == "send_message")
    assert send_message_call[1][0] == "sys_notify"
    assert "userone" in send_message_call[1][1]
    assert send_message_call[2]["platform"] == "all"
