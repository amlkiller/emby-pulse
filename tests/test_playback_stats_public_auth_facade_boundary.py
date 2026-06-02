import ast
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_playback_stats_does_not_import_private_users_auth():
    path = _REPO_ROOT / "app/domains/playback/stats.py"
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


def test_get_libraries_denies_non_admin_before_query_or_media_side_effects(monkeypatch):
    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_media_get(*args, **kwargs):
        raise AssertionError("media libraries should not be read without admin permission")

    def fail_get_admin_user_id():
        raise AssertionError("admin media user should not be queried without admin permission")

    def fail_playback_query(*args, **kwargs):
        raise AssertionError("stats queries should not run without admin permission")

    monkeypatch.setattr(stats.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(stats.media_api, "get", fail_media_get)
    monkeypatch.setattr(stats, "get_admin_user_id", fail_get_admin_user_id)
    monkeypatch.setattr(stats.playback_store, "query", fail_playback_query)

    response = stats.api_get_libraries(request)

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]


def test_get_libraries_allows_admin_through_public_facade(monkeypatch):
    from app.domains.playback import stats

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    calls = []

    class LibrariesResponse:
        status_code = 200

        def json(self):
            calls.append(("libraries_json",))
            return [
                {
                    "ItemId": "lib-1",
                    "Name": "Movies",
                    "CollectionType": "movies",
                }
            ]

    class ItemResponse:
        status_code = 200

        def json(self):
            calls.append(("item_json",))
            return {"ImageTags": {"Primary": "abcdef123456"}}

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_media_get(path, timeout=None):
        calls.append(("media_get", path, timeout))
        if path == "/Library/VirtualFolders":
            return LibrariesResponse()
        if path == "/Users/admin-id/Items/lib-1":
            return ItemResponse()
        raise AssertionError(f"unexpected media path: {path}")

    def fake_get_admin_user_id():
        calls.append(("get_admin_user_id",))
        return "admin-id"

    def fail_playback_query(*args, **kwargs):
        raise AssertionError("library listing should not query playback stats")

    monkeypatch.setattr(stats.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(stats.media_api, "get", fake_media_get)
    monkeypatch.setattr(stats, "get_admin_user_id", fake_get_admin_user_id)
    monkeypatch.setattr(stats.playback_store, "query", fail_playback_query)

    response = stats.api_get_libraries(request)

    assert response == {
        "status": "success",
        "data": [
            {
                "Id": "lib-1",
                "Name": "Movies",
                "CollectionType": "movies",
                "ImageTag": "abcdef12",
            }
        ],
    }
    assert calls == [
        ("is_admin_user", request),
        ("media_get", "/Library/VirtualFolders", 10),
        ("libraries_json",),
        ("get_admin_user_id",),
        ("media_get", "/Users/admin-id/Items/lib-1", 3),
        ("item_json",),
    ]
