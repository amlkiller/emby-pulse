import ast
import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[1]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))


def _app_python_files():
    app_root = _repo_root / "app"
    return [path for path in app_root.rglob("*.py") if "__pycache__" not in path.parts]


def test_core_db_schemas_is_only_compatibility_importer():
    allowed = Path("app/core/db_schemas.py")
    offenders = []

    for path in _app_python_files():
        rel_path = path.relative_to(_repo_root)
        if rel_path == allowed:
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


def test_core_db_schemas_reexports_schema_registry_objects():
    from app.core import db_schemas
    from app.infra.db import schema_registry

    assert db_schemas.SYSTEM_TABLES is schema_registry.SYSTEM_TABLES
    assert db_schemas.PLAYBACK_TABLES is schema_registry.PLAYBACK_TABLES
    assert db_schemas.TABLE_SCHEMAS is schema_registry.TABLE_SCHEMAS
    assert db_schemas.TABLE_ALTERS is schema_registry.TABLE_ALTERS
    assert db_schemas.CORE_TABLES is schema_registry.CORE_TABLES
    assert db_schemas.PLAYBACK_SCHEMA is schema_registry.PLAYBACK_SCHEMA


def test_schema_registry_owns_schema_metadata_definitions():
    source = (_repo_root / "app/infra/db/schema_registry.py").read_text(encoding="utf-8")

    assert "SYSTEM_TABLES = [" in source
    assert "PLAYBACK_TABLES = [" in source
    assert "TABLE_SCHEMAS = {" in source
    assert "TABLE_ALTERS = {" in source
    assert "from app.core.db_schemas" not in source


def test_database_uses_schema_registry_table_lists():
    from app.infra.db import database
    from app.infra.db import schema_registry

    source = (_repo_root / "app/infra/db/database.py").read_text(encoding="utf-8")

    assert database.SYSTEM_TABLES is schema_registry.SYSTEM_TABLES
    assert database.PLAYBACK_TABLES is schema_registry.PLAYBACK_TABLES
    assert "SYSTEM_TABLES = [" not in source
    assert "PLAYBACK_TABLES = [" not in source
