import ast
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_system_api_tokens_does_not_import_private_users_auth():
    path = _REPO_ROOT / "app/domains/system/api_tokens.py"
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


def test_create_token_rejects_unauthenticated_before_admin_check(monkeypatch):
    from app.domains.system import api_tokens

    request = SimpleNamespace(session={})
    data = api_tokens.CreateTokenRequest(name="Automation")

    def fail_admin_check(*args, **kwargs):
        raise AssertionError("admin check should not run without a logged-in user")

    monkeypatch.setattr(api_tokens.user_service, "is_admin_user", fail_admin_check)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(api_tokens.create_token(request, data))

    assert exc.value.status_code == 401
    assert exc.value.detail == "未登录"


def test_create_token_denies_non_admin_before_side_effects(monkeypatch):
    from app.domains.system import api_tokens

    request = SimpleNamespace(session={"user": {"id": "u1", "name": "User"}})
    data = api_tokens.CreateTokenRequest(name="Automation")
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_create_api_token(*args, **kwargs):
        raise AssertionError("token should not be created without admin permission")

    def fail_create_api_token_record(*args, **kwargs):
        raise AssertionError("token record should not be created without admin permission")

    monkeypatch.setattr(api_tokens.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(api_tokens, "create_api_token", fail_create_api_token)
    monkeypatch.setattr(api_tokens, "create_api_token_record", fail_create_api_token_record)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(api_tokens.create_token(request, data))

    assert exc.value.status_code == 403
    assert exc.value.detail == "需要管理员权限"
    assert calls == [request]


def test_create_token_allows_admin_through_public_facade(monkeypatch):
    from app.domains.system import api_tokens

    request = SimpleNamespace(
        session={"user": {"id": "admin-id", "name": "Admin", "is_admin": True}}
    )
    data = api_tokens.CreateTokenRequest(name="Automation", expires_hours=2)
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_create_api_token(user_id, username, is_admin):
        calls.append(("create_api_token", user_id, username, is_admin))
        return "token-a"

    def fake_create_api_token_record(user_id, token_hash, name, expires_at, created_at):
        calls.append(("create_api_token_record", user_id, token_hash, name))
        assert expires_at
        assert created_at

    monkeypatch.setattr(api_tokens.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(api_tokens, "create_api_token", fake_create_api_token)
    monkeypatch.setattr(api_tokens, "_hash_token", lambda token: f"hash:{token}")
    monkeypatch.setattr(api_tokens, "create_api_token_record", fake_create_api_token_record)

    response = asyncio.run(api_tokens.create_token(request, data))

    assert response["status"] == "success"
    assert response["token"] == "token-a"
    assert response["name"] == "Automation"
    assert response["expires_at"]
    assert response["created_at"]
    assert calls == [
        ("is_admin_user", request),
        ("create_api_token", "admin-id", "Admin", True),
        ("create_api_token_record", "admin-id", "hash:token-a", "Automation"),
    ]


def test_list_tokens_denies_non_admin_before_dao_read(monkeypatch):
    from app.domains.system import api_tokens

    request = SimpleNamespace(session={"user": {"id": "u1", "name": "User"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_list_api_tokens(*args, **kwargs):
        raise AssertionError("tokens should not be listed without admin permission")

    monkeypatch.setattr(api_tokens.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(api_tokens, "list_api_tokens", fail_list_api_tokens)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(api_tokens.list_tokens(request))

    assert exc.value.status_code == 403
    assert exc.value.detail == "需要管理员权限"
    assert calls == [request]


def test_delete_token_denies_non_admin_before_dao_write(monkeypatch):
    from app.domains.system import api_tokens

    request = SimpleNamespace(session={"user": {"id": "u1", "name": "User"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_delete_api_token(*args, **kwargs):
        raise AssertionError("token should not be deleted without admin permission")

    monkeypatch.setattr(api_tokens.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(api_tokens, "delete_api_token", fail_delete_api_token)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(api_tokens.delete_token(request, token_id=1))

    assert exc.value.status_code == 403
    assert exc.value.detail == "需要管理员权限"
    assert calls == [request]
