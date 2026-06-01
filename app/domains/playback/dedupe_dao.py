import json
import sqlite3

from app.infra.db.schema_registry import TABLE_ALTERS, TABLE_SCHEMAS
from app.infra.db.system_store import system_store


DEDUPE_TABLES = ("dedupe_whitelist", "dedupe_results", "dedupe_config")


def _apply_table_alters(cursor, table_name: str) -> None:
    for alter_sql in TABLE_ALTERS.get(table_name, []):
        try:
            cursor.execute(alter_sql)
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise


def init_dedupe_tables(logger=None) -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(dedupe_whitelist)")
        whitelist_columns = [column[1] for column in cursor.fetchall()]
        needs_migration = "id" in whitelist_columns and "group_key" not in whitelist_columns

        if needs_migration:
            if logger:
                logger.info("[去重引擎] 检测到旧版 dedupe_whitelist 表结构，正在迁移...")
            cursor.execute("SELECT item_id, item_name, created_at FROM dedupe_whitelist")
            old_data = cursor.fetchall()
            cursor.execute("DROP TABLE IF EXISTS dedupe_whitelist")
            cursor.execute(TABLE_SCHEMAS["dedupe_whitelist"])
            for row in old_data:
                if row[0]:
                    cursor.execute(
                        "INSERT OR IGNORE INTO dedupe_whitelist (group_key, title, created_at) VALUES (?, ?, ?)",
                        (row[0], row[1] or "", row[2] or ""),
                    )
            if logger:
                logger.info(f"[去重引擎] 已迁移 {len(old_data)} 条白名单记录")
        else:
            cursor.execute(TABLE_SCHEMAS["dedupe_whitelist"])

        for table_name in DEDUPE_TABLES:
            if table_name != "dedupe_whitelist":
                cursor.execute(TABLE_SCHEMAS[table_name])
            _apply_table_alters(cursor, table_name)

        conn.commit()


def list_dedupe_whitelist_group_keys():
    rows = system_store.fetch_all("SELECT group_key FROM dedupe_whitelist")
    return [row["group_key"] for row in rows]


class DedupeResultWriter:
    def __enter__(self):
        self._context = system_store.connect()
        self.conn = self._context.__enter__()
        self.cursor = self.conn.cursor()
        self.cursor.execute("DELETE FROM dedupe_results")
        self.conn.commit()
        return self

    def insert_result(self, item) -> None:
        self.cursor.execute(
            """INSERT INTO dedupe_results
            (group_key, tmdb_id, media_type, title, season_num, episode_num, item_id, file_name, file_path,
             resolution, bitrate, size_bytes, video_codec, audio_codec, has_hdr, has_dovi,
             has_chi_sub, has_ass_sub, score, is_recommended_del, is_exempt)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                item["g_key"],
                item["tmdb"],
                item["mtype"],
                item["title"],
                item["season"],
                item["episode"],
                item["item_id"],
                item["file_name"],
                item["file_path"],
                item["res"],
                item["bitrate"],
                item["size"],
                item["v_codec"],
                item["a_codec"],
                item["hdr"],
                item["dovi"],
                item["chi"],
                item["ass"],
                item["score"],
                item["del_mark"],
                item["exempt"],
            ),
        )

    def commit(self) -> None:
        self.conn.commit()

    def __exit__(self, exc_type, exc, traceback):
        if exc_type:
            self.conn.rollback()
        self._context.__exit__(exc_type, exc, traceback)


def list_dedupe_results():
    return system_store.fetch_all("SELECT * FROM dedupe_results ORDER BY group_key, score DESC")


def add_dedupe_whitelist_items(items) -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        for item in items:
            cursor.execute(
                "INSERT OR REPLACE INTO dedupe_whitelist (group_key, title) VALUES (?, ?)",
                (item.group_key, item.title),
            )
            cursor.execute("DELETE FROM dedupe_results WHERE group_key = ?", (item.group_key,))
        conn.commit()


def list_dedupe_whitelist():
    return system_store.fetch_all("SELECT * FROM dedupe_whitelist ORDER BY created_at DESC")


def remove_dedupe_whitelist_items(group_keys) -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        for group_key in group_keys:
            cursor.execute("DELETE FROM dedupe_whitelist WHERE group_key = ?", (group_key,))
        conn.commit()


def delete_dedupe_result_by_item_id(item_id: str) -> None:
    system_store.execute("DELETE FROM dedupe_results WHERE item_id = ?", (item_id,))


def get_dedupe_config_values():
    rows = system_store.fetch_all("SELECT key, value FROM dedupe_config")
    config = {}
    for row in rows:
        try:
            config[row["key"]] = json.loads(row["value"])
        except Exception:
            config[row["key"]] = row["value"]
    return config


def save_dedupe_config_values(config: dict) -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        for key, value in config.items():
            value_str = json.dumps(value) if not isinstance(value, str) else value
            cursor.execute(
                "INSERT OR REPLACE INTO dedupe_config (key, value, updated_at) VALUES (?, ?, datetime('now', 'localtime'))",
                (key, value_str),
            )
        conn.commit()
