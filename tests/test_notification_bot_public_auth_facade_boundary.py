import ast
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_notification_bot_does_not_import_private_users_auth():
    path = _REPO_ROOT / "app/domains/notifications/bot.py"
    rel_path = path.relative_to(_REPO_ROOT).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(rel_path))
    violations = []
    imports_points_dao = False

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names = {alias.name for alias in node.names}
            if node.module == "app.domains.users.auth":
                violations.append(f"{rel_path}:{node.lineno}")
            if node.module == "app.domains.users" and ("auth" in imported_names or "*" in imported_names):
                violations.append(f"{rel_path}:{node.lineno}")
            if node.module == "app.domains.points.router" and (
                "get_point_config" in imported_names or "*" in imported_names
            ):
                violations.append(f"{rel_path}:{node.lineno}")
            if node.module == "app.domains.points" and "point_dao" in imported_names:
                imports_points_dao = True
        elif isinstance(node, ast.Import):
            imported_modules = {alias.name for alias in node.names}
            if "app.domains.users.auth" in imported_modules:
                violations.append(f"{rel_path}:{node.lineno}")
            if "app.domains.points.router" in imported_modules:
                violations.append(f"{rel_path}:{node.lineno}")

    assert violations == []
    assert imports_points_dao is True


def test_get_bot_settings_denies_non_admin_before_config_read(monkeypatch):
    from app.domains.notifications import bot as notification_bot

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_get_all_bot_settings():
        raise AssertionError("bot settings should not be read without admin permission")

    monkeypatch.setattr(notification_bot.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(notification_bot, "get_all_bot_settings", fail_get_all_bot_settings)

    response = notification_bot.api_get_bot_settings(request)

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]


def test_get_user_blacklist_allows_admin_through_public_facade(monkeypatch):
    from app.domains.notifications import bot as notification_bot

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    rows = [{"tg_user_id": "1001", "reason": "spam"}]
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_list_user_blacklist():
        calls.append(("list_user_blacklist",))
        return rows

    monkeypatch.setattr(notification_bot.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(notification_bot, "list_user_blacklist", fake_list_user_blacklist)

    response = notification_bot.api_get_user_blacklist(request)

    assert response == {"status": "success", "data": rows}
    assert calls == [
        ("is_admin_user", request),
        ("list_user_blacklist",),
    ]


def test_add_user_blacklist_denies_non_admin_before_request_body(monkeypatch):
    from app.domains.notifications import bot as notification_bot

    calls = []

    class Request:
        session = {"user": {"Id": "u1"}}

        async def json(self):
            raise AssertionError("request body should not be read without admin permission")

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    request = Request()
    monkeypatch.setattr(notification_bot.user_service, "is_admin_user", fake_is_admin_user)

    response = asyncio.run(notification_bot.api_add_user_blacklist(request))

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]


def test_test_bot_allows_admin_through_public_facade(monkeypatch):
    from app.domains.notifications import bot as notification_bot

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    calls = []

    class Response:
        status_code = 200
        text = "ok"

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_get_tg_bot_token():
        calls.append(("get_tg_bot_token",))
        return "token"

    def fake_get_tg_chat_id():
        calls.append(("get_tg_chat_id",))
        return "chat"

    def fake_send_message(token, payload, proxies=None, timeout=None):
        calls.append(("send_message", token, payload, proxies, timeout))
        return Response()

    monkeypatch.setattr(notification_bot.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(notification_bot, "get_tg_bot_token", fake_get_tg_bot_token)
    monkeypatch.setattr(notification_bot, "get_tg_chat_id", fake_get_tg_chat_id)
    monkeypatch.setattr(notification_bot.telegram_client, "send_message", fake_send_message)

    response = notification_bot.api_test_bot(request)

    assert response == {"status": "success"}
    assert calls == [
        ("is_admin_user", request),
        ("get_tg_bot_token",),
        ("get_tg_chat_id",),
        ("send_message", "token", {"chat_id": "chat", "text": "🎉 测试消息"}, None, 10),
    ]


def test_lottery_pool_uses_point_dao_config_owner(monkeypatch):
    from app.domains.notifications import bot as notification_bot

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_get_point_config():
        calls.append(("get_point_config",))
        return {"lottery_draw_hour": "21", "lottery_max_per_day": "7"}

    def fake_get_lottery_pool_info(today, tomorrow):
        calls.append(("get_lottery_pool_info", today, tomorrow))
        return {
            "target_pool": 1200,
            "target_tickets": 12,
            "total_accumulated": 2400,
            "target_date": today,
            "is_drawn": False,
        }

    monkeypatch.setattr(notification_bot.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(notification_bot.point_dao, "get_point_config", fake_get_point_config)
    monkeypatch.setattr(notification_bot, "get_lottery_pool_info", fake_get_lottery_pool_info)

    response = notification_bot.api_lottery_pool(request)

    assert response["status"] == "success"
    assert response["data"]["draw_hour"] == 21
    assert response["data"]["max_per_day"] == 7
    assert response["data"]["today_pool"] == 1200
    assert calls[0:2] == [
        ("is_admin_user", request),
        ("get_point_config",),
    ]
    assert calls[2][0] == "get_lottery_pool_info"
