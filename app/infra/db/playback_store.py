import json
import logging
import os
import sqlite3

from app.core.config import DB_PATH, cfg
from app.infra.clients.media_server_client import media_api

from .row import DataRow, to_data_row

logger = logging.getLogger("uvicorn")


def _interpolate_sql(query: str, args) -> str:
    """Convert parameterized SQL into the Emby custom-query string format."""
    if not args:
        return query
    parts = query.split("?")
    if len(parts) - 1 != len(args):
        return query

    result = parts[0]
    for index, arg in enumerate(args):
        if isinstance(arg, bool):
            value = "1" if arg else "0"
        elif isinstance(arg, (int, float)):
            value = str(arg)
        elif arg is None:
            value = "NULL"
        else:
            text = str(arg)
            text = text.replace("\\", "\\\\")
            text = text.replace("'", "''")
            text = text.replace("\x00", "")
            text = text.replace("�", "")
            text = text.replace("\n", "\\n")
            text = text.replace("\r", "\\r")
            text = text.replace("\t", "\\t")
            text = text.replace("\x1a", "\\Z")
            text = text.replace("/*", "")
            text = text.replace("*/", "")
            text = text.replace("`", "")
            value = f"'{text}'"
        result += value + parts[index + 1]
    return result


class PlaybackStore:
    """Explicit access boundary for PlaybackActivity data."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def query(self, sql: str, params=(), one: bool = False):
        if self._use_api_mode():
            api_result = self._query_api(sql, params, one=one)
            if api_result is not None:
                return api_result

        return self._query_sqlite(sql, params, one=one)

    def _use_api_mode(self) -> bool:
        return cfg.get("playback_data_mode", "sqlite") == "api"

    def _query_api(self, sql: str, params, one: bool = False):
        host = cfg.get("emby_host")
        token = cfg.get("emby_api_key")
        if not host or not token:
            print("[API 引擎] ⚠️ 警告: Emby Host 或 Token 未配置，自动降级回 SQLite。")
            return None

        try:
            response = media_api.submit_custom_query(
                host,
                token,
                _interpolate_sql(sql, params),
                timeout=20,
            )
            if response.status_code != 200:
                print(f"[API 引擎] ❌ 接口拒绝请求! 响应: {response.text[:200]}")
                return None

            data = self._parse_api_response(response)
            return (data[0] if data else None) if one else data
        except Exception as exc:
            print(f"[API 引擎] ❌ 网络崩溃异常: {exc}")
            return None

    def _parse_api_response(self, response):
        try:
            response_json = response.json()
            if isinstance(response_json, str):
                try:
                    raw_data = json.loads(response_json)
                except Exception:
                    raw_data = response_json
            else:
                raw_data = response_json
        except Exception:
            try:
                raw_data = json.loads(response.text)
            except Exception:
                raw_data = {}

        final_data = []
        if isinstance(raw_data, dict):
            columns = raw_data.get("colums") or raw_data.get("columns")
            results = raw_data.get("results")
            if columns and isinstance(results, list):
                for row in results:
                    if isinstance(row, list):
                        row_dict = {}
                        for index, column_name in enumerate(columns):
                            value = row[index] if index < len(row) else None
                            if isinstance(value, str) and value.isdigit():
                                value = int(value)
                            row_dict[column_name] = value
                        final_data.append(row_dict)
            else:
                extracted = raw_data.get("results", raw_data.get("Items", [raw_data]))
                final_data = extracted if isinstance(extracted, list) else [extracted]
        elif isinstance(raw_data, list):
            final_data = raw_data
        elif raw_data:
            final_data = [raw_data]

        return [DataRow(item) if isinstance(item, dict) else item for item in final_data]

    def _query_sqlite(self, sql: str, params=(), one: bool = False):
        if self.db_path.startswith("/emby-data") and not os.path.exists("/emby-data"):
            print("[📁 挂载检测] ⚠️ 未检测到 Emby 数据挂载: /emby-data")
            print("[📁 挂载检测] 播放统计功能将不可用，请配置 API 模式或挂载数据库")
            return None

        if not os.path.exists(self.db_path):
            print(f"[SQLite 引擎] ⚠️ 数据库文件不存在: {self.db_path}")
            print("[SQLite 引擎] 请确保已正确挂载 Emby 插件的 playback_reporting.db")
            return None

        try:
            conn = sqlite3.connect(self.db_path, timeout=20.0)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()
            conn.close()

            if one:
                return to_data_row(rows[0]) if rows else None
            return [to_data_row(row) for row in rows]
        except sqlite3.OperationalError as exc:
            self._log_sqlite_error(exc)
            return None
        except Exception as exc:
            print(f"[SQLite 引擎] 💥 未知错误: {exc}")
            return None

    def _log_sqlite_error(self, exc: sqlite3.OperationalError) -> None:
        err_msg = str(exc).lower()
        if "no such table" in err_msg:
            print(f"[SQLite 引擎] ❌ 表不存在: {exc}")
            print("[SQLite 引擎] 请确认 Emby 插件是否已正确运行并创建数据库表")
        elif "no such column" in err_msg:
            print(f"[SQLite 引擎] ❌ 列不存在: {exc}")
            print("[SQLite 引擎] 可能是插件版本差异，请检查插件版本")
        elif "read-only" in err_msg:
            print(f"[SQLite 引擎] ❌ 数据库为只读: {exc}")
            print("[SQLite 引擎] 请检查 Docker 卷挂载是否为读写模式")
        elif "duplicate column" not in err_msg:
            print(f"[SQLite 引擎] 💥 数据库操作失败: {exc}")

    def inspect_local_schema(self):
        if not os.path.exists(self.db_path):
            return {"db_exists": False, "tables": [], "columns": {}}

        with sqlite3.connect(self.db_path, timeout=5) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            columns = {}
            for table in tables:
                cursor.execute(f"PRAGMA table_info({table})")
                columns[table] = [row[1] for row in cursor.fetchall()]
            return {"db_exists": True, "tables": tables, "columns": columns}


playback_store = PlaybackStore()


def get_playback_column_name() -> str:
    try:
        rows = playback_store.query("SELECT * FROM PlaybackActivity LIMIT 1", [])
        if rows:
            available_cols = list(rows[0].keys()) if hasattr(rows[0], "keys") else []
            col_map = {column.lower(): column for column in available_cols}
            if "clientname" in col_map:
                return col_map["clientname"]
            if "client" in col_map:
                return col_map["client"]
        return "Client"
    except Exception as exc:
        logger.warning(f"[列检测] 检测 PlaybackActivity 列失败: {exc}，默认使用 Client")
        return "Client"
