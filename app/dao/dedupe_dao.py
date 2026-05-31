import json

from app.infra.db.system_store import system_store


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
            cursor.execute(
                """CREATE TABLE dedupe_whitelist (
                    group_key TEXT PRIMARY KEY,
                    title TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            for row in old_data:
                if row[0]:
                    cursor.execute(
                        "INSERT OR IGNORE INTO dedupe_whitelist (group_key, title, created_at) VALUES (?, ?, ?)",
                        (row[0], row[1] or "", row[2] or ""),
                    )
            if logger:
                logger.info(f"[去重引擎] 已迁移 {len(old_data)} 条白名单记录")
        else:
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS dedupe_whitelist (
                    group_key TEXT PRIMARY KEY,
                    title TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )"""
            )

        cursor.execute(
            """CREATE TABLE IF NOT EXISTS dedupe_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_key TEXT,
                tmdb_id TEXT,
                media_type TEXT,
                title TEXT,
                season_num INTEGER,
                episode_num INTEGER,
                item_id TEXT,
                file_name TEXT,
                file_path TEXT,
                resolution TEXT,
                bitrate INTEGER,
                size_bytes REAL,
                video_codec TEXT,
                audio_codec TEXT,
                has_hdr INTEGER,
                has_dovi INTEGER,
                has_chi_sub INTEGER,
                has_ass_sub INTEGER,
                score INTEGER,
                is_recommended_del INTEGER DEFAULT 0,
                is_exempt INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )"""
        )

        cursor.execute("PRAGMA table_info(dedupe_results)")
        columns = [column[1] for column in cursor.fetchall()]
        migrations = {
            "group_key": "ALTER TABLE dedupe_results ADD COLUMN group_key TEXT",
            "tmdb_id": "ALTER TABLE dedupe_results ADD COLUMN tmdb_id TEXT",
            "season_num": "ALTER TABLE dedupe_results ADD COLUMN season_num INTEGER",
            "episode_num": "ALTER TABLE dedupe_results ADD COLUMN episode_num INTEGER",
            "file_name": "ALTER TABLE dedupe_results ADD COLUMN file_name TEXT",
            "file_path": "ALTER TABLE dedupe_results ADD COLUMN file_path TEXT",
            "resolution": "ALTER TABLE dedupe_results ADD COLUMN resolution TEXT",
            "bitrate": "ALTER TABLE dedupe_results ADD COLUMN bitrate INTEGER",
            "size_bytes": "ALTER TABLE dedupe_results ADD COLUMN size_bytes REAL",
            "video_codec": "ALTER TABLE dedupe_results ADD COLUMN video_codec TEXT",
            "audio_codec": "ALTER TABLE dedupe_results ADD COLUMN audio_codec TEXT",
            "has_hdr": "ALTER TABLE dedupe_results ADD COLUMN has_hdr INTEGER",
            "has_dovi": "ALTER TABLE dedupe_results ADD COLUMN has_dovi INTEGER",
            "has_chi_sub": "ALTER TABLE dedupe_results ADD COLUMN has_chi_sub INTEGER",
            "has_ass_sub": "ALTER TABLE dedupe_results ADD COLUMN has_ass_sub INTEGER",
            "score": "ALTER TABLE dedupe_results ADD COLUMN score INTEGER",
            "is_recommended_del": "ALTER TABLE dedupe_results ADD COLUMN is_recommended_del INTEGER DEFAULT 0",
            "is_exempt": "ALTER TABLE dedupe_results ADD COLUMN is_exempt INTEGER DEFAULT 0",
        }
        for column, sql in migrations.items():
            if column not in columns:
                cursor.execute(sql)

        cursor.execute(
            """CREATE TABLE IF NOT EXISTS dedupe_config (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )"""
        )
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
