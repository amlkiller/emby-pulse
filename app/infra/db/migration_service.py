"""Database migration, health, backup, and repair operations.

This module is the new boundary for migration orchestration. It delegates to the
existing implementation until schema ownership is fully moved out of app.core.
"""

import os

from app.core.config import DB_PATH
from app.core.security_utils import safe_error_message
from app.infra.db import db_manager
from app.infra.db.schema_registry import SYSTEM_TABLES, TABLE_ALTERS
from app.infra.db.system_store import system_store


def backup_system_database():
    if os.path.exists(system_store.db_path):
        return db_manager.backup_database(system_store.db_path)
    return None


def backup_old_database():
    if os.path.exists(DB_PATH):
        return db_manager.backup_database(DB_PATH)
    return None


def backup_existing_databases():
    results = {}
    system_backup = backup_system_database()
    if system_backup:
        results["system_db"] = system_backup
    old_backup = backup_old_database()
    if old_backup:
        results["old_db"] = old_backup
    return results


def deep_check_system_database():
    results = {
        "system_db": {
            "exists": os.path.exists(system_store.db_path),
            "path": system_store.db_path,
            "size_mb": 0,
            "tables": {},
            "scan_log": [],
        }
    }

    results["system_db"]["scan_log"].append(
        {
            "step": "check_file",
            "status": "running",
            "message": "正在检查数据库文件...",
        }
    )

    if not os.path.exists(system_store.db_path):
        results["system_db"]["scan_log"][0]["status"] = "error"
        results["system_db"]["scan_log"][0]["message"] = "数据库文件不存在"
        results["missing_tables"] = list(SYSTEM_TABLES)
        results["is_healthy"] = False
        return results

    results["system_db"]["scan_log"][0]["status"] = "success"
    results["system_db"]["scan_log"][0]["message"] = f"数据库文件存在: {system_store.db_path}"
    results["system_db"]["size_mb"] = round(os.path.getsize(system_store.db_path) / (1024 * 1024), 2)

    results["system_db"]["scan_log"].append(
        {
            "step": "connect",
            "status": "running",
            "message": "正在连接数据库...",
        }
    )

    try:
        with system_store.connect() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = {row[0] for row in cursor.fetchall()}

            results["system_db"]["scan_log"][1]["status"] = "success"
            results["system_db"]["scan_log"][1]["message"] = f"已连接，发现 {len(existing_tables)} 张表"

            results["system_db"]["scan_log"].append(
                {
                    "step": "scan_tables",
                    "status": "running",
                    "message": f"正在扫描 {len(SYSTEM_TABLES)} 张系统表...",
                }
            )

            missing_tables = []
            missing_alters = {}
            table_details = {}

            for table_name in SYSTEM_TABLES:
                if table_name in existing_tables:
                    try:
                        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                        count = cursor.fetchone()[0]
                        cursor.execute(f"PRAGMA table_info({table_name})")
                        columns = [row[1] for row in cursor.fetchall()]

                        table_details[table_name] = {
                            "exists": True,
                            "rows": count,
                            "columns": columns,
                            "status": "ok",
                        }
                    except Exception as exc:
                        table_details[table_name] = {
                            "exists": True,
                            "rows": 0,
                            "columns": [],
                            "status": "error",
                            "error": safe_error_message(exc, "查询失败"),
                        }
                else:
                    missing_tables.append(table_name)
                    table_details[table_name] = {
                        "exists": False,
                        "rows": 0,
                        "columns": [],
                        "status": "missing",
                    }

            results["system_db"]["tables"] = table_details
            results["system_db"]["scan_log"][2]["status"] = "success"
            results["system_db"]["scan_log"][2][
                "message"
            ] = f"扫描完成: {len(SYSTEM_TABLES) - len(missing_tables)} 正常, {len(missing_tables)} 缺失"

            results["system_db"]["scan_log"].append(
                {
                    "step": "check_alters",
                    "status": "running",
                    "message": "正在检测表字段...",
                }
            )

            for table_name, alters in TABLE_ALTERS.items():
                if table_name in existing_tables:
                    cursor.execute(f"PRAGMA table_info({table_name})")
                    existing_columns = {row[1] for row in cursor.fetchall()}

                    for alter_sql in alters:
                        parts = alter_sql.split("ADD COLUMN ")
                        if len(parts) > 1:
                            field_name = parts[1].split()[0]
                            if field_name not in existing_columns:
                                if table_name not in missing_alters:
                                    missing_alters[table_name] = []
                                missing_alters[table_name].append(field_name)

            results["system_db"]["scan_log"][3]["status"] = "success"
            results["system_db"]["scan_log"][3][
                "message"
            ] = f"字段检测完成: {sum(len(value) for value in missing_alters.values())} 个缺失字段"
    except Exception as exc:
        results["system_db"]["scan_log"][1]["status"] = "error"
        results["system_db"]["scan_log"][1]["message"] = safe_error_message(exc, "连接失败")
        results["is_healthy"] = False
        return results

    results["missing_tables"] = missing_tables
    results["missing_alters"] = missing_alters
    results["is_healthy"] = len(missing_tables) == 0 and len(missing_alters) == 0
    results["summary"] = {
        "total_tables": len(SYSTEM_TABLES),
        "existing_tables": len(SYSTEM_TABLES) - len(missing_tables),
        "missing_tables": len(missing_tables),
        "missing_columns": sum(len(value) for value in missing_alters.values()),
    }

    return results
