import os
import sqlite3

from app.core.security_utils import safe_error_message
from app.infra.db.playback_store import playback_store


def get_latest_playback_date():
    row = playback_store.query(
        "SELECT DateCreated FROM PlaybackActivity ORDER BY DateCreated DESC LIMIT 1",
        one=True,
    )
    return row["DateCreated"] if row and row["DateCreated"] else None


def diagnose_playback_database():
    db_path = playback_store.db_path
    result = {
        "db_path": db_path,
        "db_exists": os.path.exists(db_path),
        "tables": [],
        "issues": [],
    }

    if not result["db_exists"]:
        result["issues"].append(f"数据库文件不存在: {db_path}")
        result["issues"].append("请确保已正确挂载 Emby 插件的 playback_reporting.db")
        result["issues"].append("Docker 示例: -v /path/to/playback_reporting.db:/emby-data/playback_reporting.db")
        return result

    try:
        with sqlite3.connect(db_path, timeout=5) as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            result["tables"] = tables

            required_tables = [
                "users_meta",
                "tg_user_bindings",
                "invitations",
                "PlaybackActivity",
                "point_config",
                "point_logs",
            ]
            for table in required_tables:
                if table not in tables:
                    result["issues"].append(f"缺少表: {table} (可能是插件版本较旧)")

            if "users_meta" in tables:
                cursor.execute("PRAGMA table_info(users_meta)")
                columns = [row[1] for row in cursor.fetchall()]
                for column in ["expire_date", "points", "is_vip", "max_concurrent"]:
                    if column not in columns:
                        result["issues"].append(f"users_meta 缺少列: {column}")

            if "tg_user_bindings" not in tables:
                result["issues"].append("缺少 tg_user_bindings 表，机器人功能将无法使用")
    except Exception as exc:
        result["issues"].append(safe_error_message(exc, "数据库读取错误"))

    return result
