# -*- coding: utf-8 -*-
"""Compatibility exports for schema metadata.

Schema metadata now belongs to app.infra.db.schema_registry. Keep this module so
older imports continue to resolve during the migration.
"""

from app.infra.db.schema_registry import (  # noqa: F401
    CORE_TABLES,
    PLAYBACK_SCHEMA,
    PLAYBACK_TABLES,
    SYSTEM_TABLES,
    TABLE_ALTERS,
    TABLE_INDEXES,
    TABLE_SCHEMAS,
)
