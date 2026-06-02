import ast
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_system_tools_does_not_import_private_users_auth():
    path = _REPO_ROOT / "app/domains/system/system_tools.py"
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


def test_perf_status_denies_non_admin_before_collecting_data(monkeypatch):
    from app.domains.system import system_tools

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_query_perf_stats():
        raise AssertionError("performance stats should not be read without admin permission")

    monkeypatch.setattr(system_tools.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(system_tools, "get_query_perf_stats", fail_query_perf_stats)

    response = system_tools.api_perf_status(request)

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]


def test_network_check_rejects_unauthenticated_before_admin_check(monkeypatch):
    from app.domains.system import system_tools

    request = SimpleNamespace(session={})

    def fail_admin_check(*args, **kwargs):
        raise AssertionError("admin check should not run without login")

    monkeypatch.setattr(system_tools.user_service, "is_admin_user", fail_admin_check)

    response = asyncio.run(system_tools.network_check(request))

    assert response == {"error": "未授权"}


def test_get_logs_allows_admin_through_public_facade(monkeypatch):
    from app.domains.system import system_tools

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    original_queue = getattr(system_tools.sys, "_emby_pulse_log_queue", None)
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return True

    monkeypatch.setattr(system_tools.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(system_tools.sys, "_emby_pulse_log_queue", ["line-1", "line-2"], raising=False)

    response = asyncio.run(system_tools.get_logs(request, lines=1))

    assert response == {"success": True, "data": "line-2"}
    assert calls == [request]
    if original_queue is not None:
        monkeypatch.setattr(system_tools.sys, "_emby_pulse_log_queue", original_queue, raising=False)


def test_weather_refresh_denies_non_admin_before_refresh(monkeypatch):
    from app.domains.system import system_tools

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_refresh_weather_cache(*args, **kwargs):
        raise AssertionError("weather cache should not refresh without admin permission")

    monkeypatch.setattr(system_tools.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(system_tools, "refresh_weather_cache", fail_refresh_weather_cache)

    response = system_tools.api_weather_refresh(request, city="Shanghai")

    assert response == {"success": False, "message": "需要管理员权限"}
    assert calls == [request]


def test_weather_status_allows_admin_through_public_facade(monkeypatch):
    from app.domains.system import system_tools

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    cache = {"data": {"temp": "20"}, "city": "Shanghai", "ts": 10, "expires": 30}
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return True

    monkeypatch.setattr(system_tools.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(system_tools, "_weather_cache", cache)
    monkeypatch.setattr(system_tools.time, "time", lambda: 20)

    response = system_tools.api_weather_status(request)

    assert response == {
        "success": True,
        "data": {
            "city": "Shanghai",
            "cached": True,
            "ts": 10,
            "expires": 30,
            "ttl_seconds": 10,
            "is_expired": False,
        },
    }
    assert calls == [request]
