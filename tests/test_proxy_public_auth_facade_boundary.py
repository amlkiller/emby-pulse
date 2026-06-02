import ast
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_proxy_router_does_not_import_private_users_auth():
    path = _REPO_ROOT / "app/domains/proxy/router.py"
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


def test_clear_image_cache_denies_unauthorized_without_deleting_cache(monkeypatch, tmp_path):
    from app.domains.proxy import router

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    image_path = tmp_path / "cached.jpg"
    meta_path = tmp_path / "cached.jpg.meta"
    image_path.write_bytes(b"image")
    meta_path.write_text("image/jpeg", encoding="utf-8")
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    monkeypatch.setattr(router, "IMAGE_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(router.user_service, "is_admin_user", fake_is_admin_user)

    response = router.clear_image_cache(request)

    assert response == {"status": "error", "message": "未授权"}
    assert calls == [request]
    assert image_path.exists()
    assert meta_path.exists()


def test_clear_image_cache_allows_authorized_public_facade_to_delete_cache(monkeypatch, tmp_path):
    from app.domains.proxy import router

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    image_path = tmp_path / "cached.jpg"
    meta_path = tmp_path / "cached.jpg.meta"
    other_path = tmp_path / "keep.txt"
    image_path.write_bytes(b"image")
    meta_path.write_text("image/jpeg", encoding="utf-8")
    other_path.write_text("not-cache", encoding="utf-8")
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return True

    monkeypatch.setattr(router, "IMAGE_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(router.user_service, "is_admin_user", fake_is_admin_user)

    response = router.clear_image_cache(request)

    assert response == {"status": "success", "deleted_count": 2}
    assert calls == [request]
    assert not image_path.exists()
    assert not meta_path.exists()
    assert other_path.exists()
