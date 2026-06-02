import ast
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class FakeBackgroundTasks:
    def add_task(self, *args, **kwargs):
        raise AssertionError("background task should not be queued without admin permission")


def test_media_request_gaps_does_not_import_private_users_auth():
    path = _REPO_ROOT / "app/domains/media_requests/gaps.py"
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


def test_start_scan_denies_non_admin_before_scan_state_and_task(monkeypatch):
    from app.domains.media_requests import gaps

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    original_scan_state = dict(gaps.scan_state)
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    monkeypatch.setattr(gaps.user_service, "is_admin_user", fake_is_admin_user)

    response = gaps.start_scan(request, FakeBackgroundTasks())

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]
    assert gaps.scan_state == original_scan_state


def test_save_gap_config_denies_non_admin_before_writing(monkeypatch):
    from app.domains.media_requests import gaps

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_save_gap_config_value(*args, **kwargs):
        raise AssertionError("gap config should not be saved without admin permission")

    monkeypatch.setattr(gaps.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(gaps, "save_gap_config_value", fail_save_gap_config_value)

    response = gaps.save_gap_config(request, {"cache_interval_hours": 6})

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]


def test_get_gap_config_allows_admin_through_public_facade(monkeypatch):
    from app.domains.media_requests import gaps

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_get_gap_config_map():
        calls.append(("get_gap_config_map",))
        return {"excluded_libraries": '["tv"]', "cache_interval_hours": "6"}

    monkeypatch.setattr(gaps.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(gaps, "get_gap_config_map", fake_get_gap_config_map)

    response = gaps.get_gap_config(request)

    assert response == {
        "status": "success",
        "data": {"excluded_libraries": ["tv"], "cache_interval_hours": "6"},
    }
    assert calls == [
        ("is_admin_user", request),
        ("get_gap_config_map",),
    ]


def test_search_mp_internal_call_skips_admin_check(monkeypatch):
    from app.domains.media_requests import gaps

    def fail_is_admin_user(*args, **kwargs):
        raise AssertionError("internal request=None call should skip admin check")

    monkeypatch.setattr(gaps.user_service, "is_admin_user", fail_is_admin_user)
    monkeypatch.setattr(gaps, "get_moviepilot_url", lambda: "")
    monkeypatch.setattr(gaps, "get_moviepilot_token", lambda: "")

    response = gaps.search_mp_for_gap(request=None, payload={})

    assert response == {"status": "error", "message": "未配置 MP"}
