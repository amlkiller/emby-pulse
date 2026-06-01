import json
import sqlite3

from app.infra.db.schema_registry import TABLE_ALTERS, TABLE_SCHEMAS
from app.infra.db.system_store import system_store


GAP_TABLES = ("gap_config", "gap_records", "gap_perfect_series", "gap_scan_cache")


def ensure_gap_tables(logger=None) -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        for table_name in GAP_TABLES:
            cursor.execute(TABLE_SCHEMAS[table_name])

        for alter_sql in TABLE_ALTERS.get("gap_perfect_series", []):
            try:
                cursor.execute(alter_sql)
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise

        cursor.execute("SELECT value FROM gap_config WHERE key = 'cache_interval_hours'")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO gap_config (key, value) VALUES ('cache_interval_hours', '6')")

        cursor.execute("PRAGMA table_info(gap_scan_cache)")
        columns = [column[1] for column in cursor.fetchall()]
        if "series_id" in columns and "result_json" not in columns:
            if logger:
                logger.info("[缺集管理] 检测到旧版 gap_scan_cache 表结构，正在迁移...")
            cursor.execute("DROP TABLE gap_scan_cache")
            cursor.execute(TABLE_SCHEMAS["gap_scan_cache"])

        conn.commit()


def add_gap_perfect_series(series_id, tmdb_id, series_name) -> None:
    system_store.execute(
        "INSERT OR IGNORE INTO gap_perfect_series (series_id, tmdb_id, series_name) VALUES (?, ?, ?)",
        (series_id, tmdb_id, series_name),
    )


def get_gap_cache_interval_hours(default: int = 6) -> int:
    row = system_store.fetch_one("SELECT value FROM gap_config WHERE key = 'cache_interval_hours'")
    return int(row["value"]) if row else default


def list_gap_records_for_lock():
    return system_store.fetch_all("SELECT series_id, season_number, episode_number, status FROM gap_records")


def list_gap_perfect_series_ids():
    rows = system_store.fetch_all("SELECT series_id FROM gap_perfect_series")
    return [row["series_id"] for row in rows]


def get_gap_config_value(key: str):
    row = system_store.fetch_one("SELECT value FROM gap_config WHERE key = ?", (key,))
    return row["value"] if row else None


def save_gap_scan_cache(results) -> None:
    system_store.execute(
        "INSERT OR REPLACE INTO gap_scan_cache (id, result_json, updated_at) VALUES (1, ?, datetime('now', 'localtime'))",
        (json.dumps(results),),
    )


def load_gap_scan_cache():
    row = system_store.fetch_one("SELECT result_json FROM gap_scan_cache WHERE id = 1")
    return json.loads(row["result_json"]) if row and row["result_json"] else None


def list_ignored_series_ids():
    rows = system_store.fetch_all("SELECT series_id FROM gap_records WHERE status=1 AND season_number=-1")
    return [row["series_id"] for row in rows]


def delete_gap_record_by_series_episode(series_id, season, episode) -> None:
    system_store.execute(
        "DELETE FROM gap_records WHERE series_id=? AND season_number=? AND episode_number=?",
        (series_id, season, episode),
    )


def delete_cleared_gap_record(series_id, season, episode) -> bool:
    deleted = system_store.execute(
        "DELETE FROM gap_records WHERE series_id=? AND season_number=? AND episode_number=? AND status=2",
        (series_id, season, episode),
    )
    return deleted > 0


def save_gap_record_status(series_id, series_name, season, episode, status: int) -> None:
    system_store.execute(
        "INSERT INTO gap_records (series_id, series_name, season_number, episode_number, status) VALUES (?, ?, ?, ?, ?) ON CONFLICT(series_id, season_number, episode_number) DO UPDATE SET status = ?",
        (series_id, series_name, season, episode, status, status),
    )


def list_gap_ignore_records():
    return system_store.fetch_all(
        "SELECT id, series_id, series_name, season_number, episode_number, created_at FROM gap_records WHERE status = 1 AND series_id != 'SYSTEM'"
    )


def list_gap_perfect_records():
    return system_store.fetch_all("SELECT series_id, tmdb_id, series_name, marked_at FROM gap_perfect_series")


def delete_gap_record_by_id(record_id) -> None:
    system_store.execute("DELETE FROM gap_records WHERE id = ?", (record_id,))


def delete_gap_perfect_series(series_id) -> None:
    system_store.execute("DELETE FROM gap_perfect_series WHERE series_id = ?", (series_id,))


def delete_gap_records_by_series_id(series_id) -> None:
    system_store.execute("DELETE FROM gap_records WHERE series_id = ?", (series_id,))


def get_gap_config_map():
    rows = system_store.fetch_all("SELECT key, value FROM gap_config")
    return {row["key"]: row["value"] for row in rows}


def save_gap_config_value(key, value) -> None:
    system_store.execute("INSERT OR REPLACE INTO gap_config (key, value) VALUES (?, ?)", (key, str(value).strip()))
