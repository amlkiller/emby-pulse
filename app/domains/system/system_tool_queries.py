from app.core.security_utils import safe_error_message
from app.infra.db.playback_store import playback_store


def get_latest_playback_date():
    row = playback_store.query(
        "SELECT DateCreated FROM PlaybackActivity ORDER BY DateCreated DESC LIMIT 1",
        one=True,
    )
    return row["DateCreated"] if row and row["DateCreated"] else None


def diagnose_playback_database():
    result = {
        "db_path": playback_store.db_path,
        "db_exists": False,
        "tables": [],
        "columns": {},
        "issues": [],
    }

    schema_info = playback_store.inspect_local_schema()
    result["db_exists"] = schema_info["db_exists"]
    result["tables"] = schema_info["tables"]
    result["columns"] = schema_info["columns"]

    if not result["db_exists"]:
        result["issues"].append(f"数据库文件不存在: {playback_store.db_path}")
        result["issues"].append("请确保已正确挂载 Emby 插件的 playback_reporting.db")
        result["issues"].append("Docker 示例: -v /path/to/playback_reporting.db:/emby-data/playback_reporting.db")
        return result

    try:
        required_tables = [
            "users_meta",
            "tg_user_bindings",
            "invitations",
            "PlaybackActivity",
            "point_config",
            "point_logs",
        ]
        for table in required_tables:
            if table not in result["tables"]:
                result["issues"].append(f"缺少表: {table} (可能是插件版本较旧)")

        if "users_meta" in result["tables"]:
            for column in ["expire_date", "points", "is_vip", "max_concurrent"]:
                if column not in result["columns"].get("users_meta", []):
                    result["issues"].append(f"users_meta 缺少列: {column}")

        if "tg_user_bindings" not in result["tables"]:
            result["issues"].append("缺少 tg_user_bindings 表，机器人功能将无法使用")
    except Exception as exc:
        result["issues"].append(safe_error_message(exc, "数据库读取错误"))

    return result
