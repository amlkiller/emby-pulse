import ast
import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[1]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))


def _app_python_files():
    app_root = _repo_root / "app"
    return [path for path in app_root.rglob("*.py") if "__pycache__" not in path.parts]


def test_schema_registry_is_only_direct_core_schema_importer():
    allowed = Path("app/infra/db/schema_registry.py")
    offenders = []

    for path in _app_python_files():
        rel_path = path.relative_to(_repo_root)
        if rel_path == Path("app/core/db_schemas.py") or rel_path == allowed:
            continue

        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(rel_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "app.core.db_schemas":
                offenders.append(str(rel_path))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "app.core.db_schemas":
                        offenders.append(str(rel_path))

    assert offenders == []


def test_database_uses_schema_registry_table_lists():
    from app.infra.db import database
    from app.infra.db import schema_registry

    source = (_repo_root / "app/infra/db/database.py").read_text(encoding="utf-8")

    assert database.SYSTEM_TABLES is schema_registry.SYSTEM_TABLES
    assert database.PLAYBACK_TABLES is schema_registry.PLAYBACK_TABLES
    assert "SYSTEM_TABLES = [" not in source
    assert "PLAYBACK_TABLES = [" not in source
