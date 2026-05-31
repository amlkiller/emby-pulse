import os
import random
import string
import time

from app.core.db_schemas import SYSTEM_TABLES
from app.core.security_utils import safe_error_message
from app.infra.db.system_store import system_store


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
