import ast
import sys
from pathlib import Path
from types import SimpleNamespace


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_playback_search_does_not_import_private_users_auth():
    path = _REPO_ROOT / "app/domains/playback/search.py"
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


def test_global_library_search_keeps_unauthenticated_response_before_media_calls(monkeypatch):
    from app.domains.playback import search

    request = SimpleNamespace(session={})

    def fail_get_emby_admin(*args, **kwargs):
        raise AssertionError("media-server helper should not run before login check")

    monkeypatch.setattr(search, "get_emby_admin", fail_get_emby_admin)

    response = search.global_library_search("movie", request)

    assert response == {"status": "error", "message": "未登录"}
