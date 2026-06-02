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


class FakeJsonRequest:
    def __init__(self, payload, user=None):
        self._payload = payload
        self.session = {}
        if user is not None:
            self.session["user"] = user

    async def json(self):
        return self._payload


def test_pwa_router_does_not_import_private_users_auth():
    path = _REPO_ROOT / "app/domains/pwa/router.py"
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


def test_set_default_icon_denies_non_admin_through_public_facade(monkeypatch):
    from app.domains.pwa import router

    request = FakeJsonRequest({"icon_id": "custom_icon_a"}, user={"Id": "u1"})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_save_pwa_config(*args, **kwargs):
        raise AssertionError("config should not be saved without admin permission")

    monkeypatch.setattr(router.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(router, "save_pwa_config", fail_save_pwa_config)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(router.set_default_icon(request))

    assert exc.value.status_code == 403
    assert exc.value.detail == "需要管理员权限"
    assert calls == [request]


def test_set_default_icon_allows_admin_through_public_facade(monkeypatch):
    from app.domains.pwa import router

    request = FakeJsonRequest({"icon_id": "custom_icon_a"}, user={"Id": "admin"})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_save_pwa_config(key, value):
        calls.append(("save_pwa_config", key, value))
        return True

    monkeypatch.setattr(router.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(router, "save_pwa_config", fake_save_pwa_config)

    response = asyncio.run(router.set_default_icon(request))

    assert response == {"status": "success", "message": "已设置默认图标"}
    assert calls == [
        ("is_admin_user", request),
        ("save_pwa_config", "default_icon", "custom_icon_a"),
    ]


def test_delete_custom_icon_denies_non_admin_before_deleting(monkeypatch, tmp_path):
    from app.domains.pwa import router

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    icon_dir = tmp_path / "data" / "pwa_icons"
    icon_dir.mkdir(parents=True)
    icon_path = icon_dir / "custom_icon_a.png"
    icon_path.write_bytes(b"png")
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(router.user_service, "is_admin_user", fake_is_admin_user)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(router.delete_custom_icon("custom_icon_a", request))

    assert exc.value.status_code == 403
    assert exc.value.detail == "需要管理员权限"
    assert calls == [request]
    assert icon_path.exists()


def test_delete_custom_icon_allows_admin_through_public_facade(monkeypatch, tmp_path):
    from app.domains.pwa import router

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    icon_dir = tmp_path / "data" / "pwa_icons"
    icon_dir.mkdir(parents=True)
    icon_path = icon_dir / "custom_icon_a.png"
    icon_path.write_bytes(b"png")
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return True

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(router.user_service, "is_admin_user", fake_is_admin_user)

    response = asyncio.run(router.delete_custom_icon("custom_icon_a", request))

    assert response == {"status": "success", "message": "图标已删除"}
    assert calls == [request]
    assert not icon_path.exists()
