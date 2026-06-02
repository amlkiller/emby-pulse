import ast
import json
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_media_requests_router_does_not_import_private_users_auth():
    path = _REPO_ROOT / "app/domains/media_requests/router.py"
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


def test_get_all_requests_denies_non_admin_before_dao_reads(monkeypatch):
    from app.domains.media_requests import router as media_requests_router

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_list_all_requests():
        raise AssertionError("media requests should not be read without admin permission")

    monkeypatch.setattr(media_requests_router.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(media_requests_router, "list_all_requests", fail_list_all_requests)

    response = media_requests_router.get_all_requests(request)

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]


def test_get_all_feedback_allows_admin_through_public_facade(monkeypatch):
    from app.domains.media_requests import router as media_requests_router

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    rows = [
        (1, "Movie", "User One", "bad_audio", "Audio is missing", 0, "2026-06-02 10:00:00"),
    ]
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_list_all_feedback():
        calls.append(("list_all_feedback",))
        return rows

    monkeypatch.setattr(media_requests_router.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(media_requests_router, "list_all_feedback", fake_list_all_feedback)

    response = media_requests_router.get_all_feedback(request)

    assert response == {
        "status": "success",
        "data": [
            {
                "id": 1,
                "item_name": "Movie",
                "username": "User One",
                "issue_type": "bad_audio",
                "description": "Audio is missing",
                "status": 0,
                "created_at": "2026-06-02 10:00:00",
            }
        ],
    }
    assert calls == [
        ("is_admin_user", request),
        ("list_all_feedback",),
    ]


def test_refresh_cache_denies_non_admin_before_refresh(monkeypatch):
    from app.domains.media_requests import router as media_requests_router

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_refresh_community_cache():
        raise AssertionError("community cache should not refresh without admin permission")

    monkeypatch.setattr(media_requests_router.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(media_requests_router, "_refresh_community_cache", fail_refresh_community_cache)

    response = media_requests_router.refresh_community_cache_api(request)

    assert response.status_code == 403
    assert json.loads(response.body.decode("utf-8")) == {
        "status": "error",
        "message": "需要管理员权限",
    }
    assert calls == [request]


def test_search_episodes_denies_non_admin_before_search_dependencies(monkeypatch):
    from app.domains.media_requests import router as media_requests_router

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_get_update_request_search_info(*args, **kwargs):
        raise AssertionError("update request search info should not be read without admin permission")

    monkeypatch.setattr(media_requests_router.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(
        media_requests_router,
        "get_update_request_search_info",
        fail_get_update_request_search_info,
    )

    response = media_requests_router.search_episodes_for_update(
        {"tmdb_id": 100, "season": 1, "episodes": [1, 2]},
        request,
    )

    assert response == {"status": "error", "message": "无权访问"}
    assert calls == [request]
