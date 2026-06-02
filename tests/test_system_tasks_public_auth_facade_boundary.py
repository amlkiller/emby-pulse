import ast
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_system_tasks_does_not_import_private_users_auth():
    path = _REPO_ROOT / "app/domains/system/tasks.py"
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


def test_get_task_config_denies_non_admin_through_public_facade(monkeypatch):
    from app.domains.system import tasks

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_is_task_notify_enabled():
        raise AssertionError("task config should not be read without admin permission")

    monkeypatch.setattr(tasks.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(tasks, "is_task_notify_enabled", fail_is_task_notify_enabled)

    response = asyncio.run(tasks.get_task_config(request))

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]


def test_get_task_config_allows_admin_through_public_facade(monkeypatch):
    from app.domains.system import tasks

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_is_task_notify_enabled():
        calls.append(("is_task_notify_enabled",))
        return True

    monkeypatch.setattr(tasks.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(tasks, "is_task_notify_enabled", fake_is_task_notify_enabled)

    response = asyncio.run(tasks.get_task_config(request))

    assert response == {"status": "success", "enable_notify": True}
    assert calls == [
        ("is_admin_user", request),
        ("is_task_notify_enabled",),
    ]


def test_translate_task_denies_non_admin_before_writing(monkeypatch):
    from app.domains.system import tasks

    request = SimpleNamespace(session={"user": {"Id": "u1"}})
    data = tasks.TranslationModel(original_name="Scan media library", translated_name="扫描")
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(seen_request)
        return False

    def fail_save_task_translation(*args, **kwargs):
        raise AssertionError("translation should not be saved without admin permission")

    def fail_delete_task_translation(*args, **kwargs):
        raise AssertionError("translation should not be deleted without admin permission")

    monkeypatch.setattr(tasks.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(tasks, "save_task_translation", fail_save_task_translation)
    monkeypatch.setattr(tasks, "delete_task_translation", fail_delete_task_translation)

    response = asyncio.run(tasks.translate_task(data, request))

    assert response == {"status": "error", "message": "需要管理员权限"}
    assert calls == [request]


def test_start_task_allows_admin_through_public_facade(monkeypatch):
    from app.domains.system import tasks

    request = SimpleNamespace(session={"user": {"Id": "admin"}})
    calls = []

    def fake_is_admin_user(seen_request):
        calls.append(("is_admin_user", seen_request))
        return True

    def fake_post(path, timeout):
        calls.append(("media_post", path, timeout))

    monkeypatch.setattr(tasks.user_service, "is_admin_user", fake_is_admin_user)
    monkeypatch.setattr(tasks.media_api, "post", fake_post)

    response = asyncio.run(tasks.start_task("task-1", request))

    assert response == {"status": "success"}
    assert calls == [
        ("is_admin_user", request),
        ("media_post", "/ScheduledTasks/Running/task-1", 5),
    ]
