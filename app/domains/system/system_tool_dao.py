import os
import random
import string
import time
import json
import sqlite3

from app.core.security_utils import safe_error_message
from app.infra.db.schema_bootstrap import apply_registered_indexes
from app.infra.db.schema_registry import PLAYBACK_SCHEMA, SYSTEM_TABLES, TABLE_ALTERS, TABLE_SCHEMAS
from app.infra.db.system_store import system_store


REPAIR_TABLE_MESSAGES = {
    "PlaybackActivity": "已修复: 播放活动主表",
    "users_meta": "已修复: 用户元数据表",
    "invitations": "已修复: 邀请码表",
    "tv_calendar_cache": "已修复: 追剧日历缓存表",
    "media_requests": "已修复: 求片主表",
    "request_users": "已修复: 求片关联表",
    "insight_ignores": "已修复: 盘点忽略表",
    "gap_records": "已修复: 缺集记录表",
}

UPGRADE_TABLE_LABELS = {
    "PlaybackActivity": "播放活动主表",
    "users_meta": "用户元数据表",
    "invitations": "邀请码表",
    "tv_calendar_cache": "追剧日历缓存表",
    "media_requests": "求片主表",
    "request_users": "求片关联表",
    "insight_ignores": "盘点忽略表",
    "gap_records": "缺集记录表",
}

UPGRADE_COLUMN_MESSAGES = {
    ("invitations", "template_user_id"): "已升级: 邀请码模板字段",
}


def check_system_table_integrity():
    if not os.path.exists(system_store.db_path):
        return {"ok": False, "msg": "系统数据库不存在"}

    try:
        with system_store.connect(timeout=3) as conn:
            cursor = conn.cursor()
            existing_tables = []
            missing_tables = []

            for table in SYSTEM_TABLES.copy():
                try:
                    cursor.execute(f"SELECT 1 FROM {table} LIMIT 1")
                    existing_tables.append(table)
                except Exception:
                    missing_tables.append(table)

        if len(missing_tables) == 0:
            return {"ok": True, "msg": f"完整 ({len(existing_tables)} 表)"}
        return {
            "ok": False,
            "msg": f"缺 {len(missing_tables)} 表: {', '.join(missing_tables[:3])}{'...' if len(missing_tables) > 3 else ''}",
        }
    except Exception as exc:
        return {"ok": False, "msg": safe_error_message(exc)[:50]}


def check_system_db_readwrite():
    try:
        test_key = f"_health_check_{''.join(random.choices(string.ascii_lowercase, k=8))}"
        test_value = f"test_{int(time.time())}"

        with system_store.connect(timeout=3) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO point_config (key, value) VALUES (?, ?)", (test_key, test_value))
            conn.commit()
            cursor.execute("SELECT value FROM point_config WHERE key = ?", (test_key,))
            result = cursor.fetchone()
            cursor.execute("DELETE FROM point_config WHERE key = ?", (test_key,))
            conn.commit()

        if result and result[0] == test_value:
            return {"ok": True, "msg": "读写正常"}
        return {"ok": False, "msg": "数据验证失败"}
    except Exception as exc:
        return {"ok": False, "msg": safe_error_message(exc)[:50]}


def system_database_exists() -> bool:
    return os.path.exists(system_store.db_path)


def _schema_sql_for_repair_table(table_name: str) -> str:
    if table_name == "PlaybackActivity":
        return PLAYBACK_SCHEMA
    return TABLE_SCHEMAS[table_name]


def _column_name_from_add_column(alter_sql: str) -> str:
    parts = alter_sql.split("ADD COLUMN ", 1)
    if len(parts) == 1:
        return ""
    return parts[1].split()[0].strip('"`[]')


def _upgrade_message(table_name: str, column_name: str) -> str:
    mapped = UPGRADE_COLUMN_MESSAGES.get((table_name, column_name))
    if mapped:
        return mapped
    table_label = UPGRADE_TABLE_LABELS.get(table_name, table_name)
    return f"已升级: {table_label}字段 {column_name}"


def repair_core_system_tables():
    results = []
    with system_store.connect() as conn:
        cursor = conn.cursor()

        for table_name, repair_message in REPAIR_TABLE_MESSAGES.items():
            try:
                cursor.execute(f"SELECT 1 FROM {table_name} LIMIT 1")
            except sqlite3.OperationalError:
                cursor.execute(_schema_sql_for_repair_table(table_name))
                results.append(repair_message)

            for alter_sql in TABLE_ALTERS.get(table_name, []):
                try:
                    cursor.execute(alter_sql)
                except sqlite3.OperationalError as exc:
                    if "duplicate column" not in str(exc).lower():
                        raise
                    continue

                column_name = _column_name_from_add_column(alter_sql)
                results.append(_upgrade_message(table_name, column_name))

            apply_registered_indexes(cursor, table_name)

        conn.commit()
    return results


def get_dashboard_layout():
    with system_store.connect() as conn:
        conn.execute(TABLE_SCHEMAS["sys_dashboard"])
        row = conn.execute("SELECT layout_json FROM sys_dashboard WHERE id = 1").fetchone()
        if row and row[0]:
            return json.loads(row[0])
    return None


def save_dashboard_layout(data) -> None:
    with system_store.connect() as conn:
        conn.execute(TABLE_SCHEMAS["sys_dashboard"])
        conn.execute(
            "INSERT OR REPLACE INTO sys_dashboard (id, layout_json) VALUES (1, ?)",
            (json.dumps(data, ensure_ascii=False),),
        )
        conn.commit()
