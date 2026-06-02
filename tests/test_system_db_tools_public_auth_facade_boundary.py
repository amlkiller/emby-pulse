import ast
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_system_db_tools_does_not_import_private_users_auth():
    path = _REPO_ROOT / "app/domains/system/db_tools.py"
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


def test_db_health_denies_non_admin_before_health_check(monkeypatch):
    from app.domains.system import db_tools

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_full_health_check():
        raise AssertionError("health check should not run without admin permission")

    monkeypatch.setattr(db_tools.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(db_tools, "full_health_check", fail_full_health_check)

    response = asyncio.run(db_tools.api_db_health(request))

    assert response.status_code == 403
    assert json.loads(response.body) == {"error": "需要管理员权限"}
    assert calls == [request]


def test_db_health_allows_admin_through_public_facade(monkeypatch):
    from app.domains.system import db_tools

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    health = {"system_db_exists": True}
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_full_health_check():
        calls.append(("full_health_check",))
        return health

    monkeypatch.setattr(db_tools.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(db_tools, "full_health_check", fake_full_health_check)

    response = asyncio.run(db_tools.api_db_health(request))

    assert response is health
    assert calls == [
        ("is_admin_user", request),
        ("full_health_check",),
    ]


def test_db_repair_denies_non_admin_before_side_effects(monkeypatch):
    from app.domains.system import db_tools

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_backup_system_database():
        raise AssertionError("database backup should not run without admin permission")

    def fail_ensure_tables():
        raise AssertionError("table repair should not run without admin permission")

    monkeypatch.setattr(db_tools.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(db_tools, "backup_system_database", fail_backup_system_database)
    monkeypatch.setattr(db_tools, "ensure_tables", fail_ensure_tables)

    response = asyncio.run(db_tools.api_db_repair(request))

    assert response.status_code == 403
    assert json.loads(response.body) == {"error": "需要管理员权限"}
    assert calls == [request]


def test_db_backup_allows_admin_through_public_facade(monkeypatch):
    from app.core import audit_logger
    from app.domains.system import db_tools

    request = SimpleNamespace(
        session={"user": {"id": "admin-id", "name": "Admin"}}
    )
    backup_results = {
        "system": {"success": True, "backup_name": "system.db.bak"},
        "playback": {"success": False},
    }
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_log_audit(**kwargs):
        calls.append(("log_audit", kwargs["action"], kwargs["user_id"], kwargs["ip_address"]))

    def fake_backup_existing_databases():
        calls.append(("backup_existing_databases",))
        return backup_results

    monkeypatch.setattr(db_tools.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(audit_logger, "log_audit", fake_log_audit)
    monkeypatch.setattr(db_tools, "get_client_ip", lambda request: "127.0.0.1")
    monkeypatch.setattr(db_tools, "backup_existing_databases", fake_backup_existing_databases)
    monkeypatch.setattr(db_tools, "BACKUP_DIR", "/backups")

    response = asyncio.run(db_tools.api_db_backup(request))

    assert response == {
        "success": True,
        "backups": backup_results,
        "backup_dir": "/backups",
    }
    assert calls == [
        ("is_admin_user", request),
        ("log_audit", "backup_create", "admin-id", "127.0.0.1"),
        ("backup_existing_databases",),
    ]
