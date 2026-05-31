"""Single import point for database schema metadata during the migration."""

from app.core.db_schemas import (  # noqa: F401
    CORE_TABLES,
    PLAYBACK_SCHEMA,
    PLAYBACK_TABLES,
    SYSTEM_TABLES,
    TABLE_ALTERS,
    TABLE_SCHEMAS,
)
