"""Database migration and health operations.

This module is the new boundary for migration orchestration. It delegates to the
existing implementation until schema ownership is fully moved out of app.core.
"""

from app.core.db_manager import ensure_tables, full_health_check  # noqa: F401
from app.core.database import auto_migrate_system_db, init_db  # noqa: F401
