import ast
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_playback_insight_does_not_import_private_users_auth():
    path = _REPO_ROOT / "app/domains/playback/insight.py"
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


def test_ignore_item_denies_non_admin_through_public_facade(monkeypatch):
    from app.domains.playback import insight

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    data = insight.IgnoreModel(item_id="item-1", item_name="Movie")
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_save_insight_ignore(*args, **kwargs):
        raise AssertionError("ignore item should not be saved without admin permission")

    monkeypatch.setattr(insight.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(insight, "save_insight_ignore", fail_save_insight_ignore)

    response = insight.ignore_item(data, request)

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]


def test_ignore_item_allows_admin_through_public_facade(monkeypatch):
    from app.domains.playback import insight

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    data = insight.IgnoreModel(item_id="item-1", item_name="Movie")
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_save_insight_ignore(item_id, item_name):
        calls.append(("save_insight_ignore", item_id, item_name))

    monkeypatch.setattr(insight.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(insight, "save_insight_ignore", fake_save_insight_ignore)

    response = insight.ignore_item(data, request)

    assert response == {"status": "success"}
    assert calls == [
        ("is_admin_user", request),
        ("save_insight_ignore", "item-1", "Movie"),
    ]


def test_get_ignored_items_allows_admin_through_public_facade(monkeypatch):
    from app.domains.playback import insight

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    calls = []

    class FakeRow(dict):
        pass

    rows = [
        FakeRow(item_id="item-1", item_name="Movie"),
        FakeRow(item_id="item-2", item_name="Show"),
    ]

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_list_insight_ignores():
        calls.append(("list_insight_ignores",))
        return rows

    monkeypatch.setattr(insight.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(insight, "list_insight_ignores", fake_list_insight_ignores)

    response = insight.get_ignored_items(request)

    assert response == {"status": "success", "data": [dict(row) for row in rows]}
    assert calls == [
        ("is_admin_user", request),
        ("list_insight_ignores",),
    ]


def test_scan_library_quality_denies_non_admin_before_scan_dependencies(monkeypatch):
    from app.domains.playback import insight

    request = SimpleNamespace(session={"user": {"Id": "u1"}}, query_params={})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_time(*args, **kwargs):
        raise AssertionError("scan dependencies should not be touched without admin permission")

    monkeypatch.setattr(insight.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(insight.time, "time", fail_time)

    response = insight.scan_library_quality(request)

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]
