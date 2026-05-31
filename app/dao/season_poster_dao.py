from app.infra.db.system_store import system_store


def ensure_season_poster_tables() -> None:
    with system_store.connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS season_poster_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                time TEXT NOT NULL,
                series_id TEXT,
                series_name TEXT,
                season_number INTEGER,
                old_poster TEXT,
                new_poster TEXT,
                success INTEGER,
                message TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS season_poster_cache (
                series_id TEXT PRIMARY KEY,
                series_name TEXT,
                season_count INTEGER,
                last_season_number INTEGER,
                last_updated TEXT
            )
            """
        )
        conn.commit()


def list_season_poster_logs(limit: int = 100):
    ensure_season_poster_tables()
    return system_store.fetch_all(
        """
        SELECT time, series_name, season_number, old_poster, new_poster, success, message
        FROM season_poster_logs
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )


def clear_season_poster_logs() -> None:
    ensure_season_poster_tables()
    with system_store.connect() as conn:
        conn.execute("DELETE FROM season_poster_logs")
        conn.commit()


def clear_plugin_logs(plugin_id: str) -> None:
    system_store.execute("DELETE FROM plugin_logs WHERE plugin_id = ?", (plugin_id,))


def count_updated_series() -> int:
    ensure_season_poster_tables()
    row = system_store.fetch_one("SELECT COUNT(DISTINCT series_id) as count FROM season_poster_logs WHERE success = 1")
    return row["count"] if row else 0


def get_cached_season_poster(series_id: str):
    ensure_season_poster_tables()
    return system_store.fetch_one(
        """
        SELECT series_name, season_count, last_season_number, last_updated
        FROM season_poster_cache
        WHERE series_id = ?
        """,
        (series_id,),
    )


def save_cached_season_poster(series_id: str, series_name: str, season_count: int, last_season_number: int, last_updated: str) -> None:
    ensure_season_poster_tables()
    system_store.execute(
        """
        INSERT OR REPLACE INTO season_poster_cache
        (series_id, series_name, season_count, last_season_number, last_updated)
        VALUES (?, ?, ?, ?, ?)
        """,
        (series_id, series_name, season_count, last_season_number, last_updated),
    )


def clear_season_poster_cache() -> None:
    ensure_season_poster_tables()
    system_store.execute("DELETE FROM season_poster_cache")


def save_season_poster_log(
    time_str: str,
    series_id: str,
    series_name: str,
    season_number: int,
    old_poster: str,
    new_poster: str,
    success: bool,
    message: str,
) -> None:
    ensure_season_poster_tables()
    system_store.execute(
        """
        INSERT INTO season_poster_logs
        (time, series_id, series_name, season_number, old_poster, new_poster, success, message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            time_str,
            series_id,
            series_name,
            season_number,
            old_poster,
            new_poster,
            1 if success else 0,
            message,
        ),
    )
