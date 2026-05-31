import json

from app.infra.db.system_store import system_store


def mark_calendar_episode_ready(series_id, season, episode) -> None:
    system_store.execute(
        """
        UPDATE tv_calendar_cache
        SET status = 'ready'
        WHERE series_id = ? AND season = ? AND episode = ?
        """,
        (series_id, season, episode),
    )


def list_calendar_cache_rows(start_date: str, end_date: str):
    return system_store.fetch_all(
        "SELECT status, data_json FROM tv_calendar_cache WHERE air_date >= ? AND air_date <= ?",
        (start_date, end_date),
    )


def replace_calendar_cache_items(week_data) -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        for items in week_data.values():
            for data_dict in items:
                series_id = data_dict.get("series_id")
                season = data_dict.get("season")
                episode = data_dict.get("episode")
                air_date = data_dict.get("air_date")
                status = data_dict.get("status")

                if series_id and season is not None and episode is not None:
                    cache_id = f"{series_id}_{season}_{episode}"
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO tv_calendar_cache
                        (id, series_id, season, episode, air_date, status, data_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (cache_id, series_id, season, episode, air_date, status, json.dumps(data_dict)),
                    )
        conn.commit()


def list_cached_calendar_series_ids():
    rows = system_store.fetch_all("SELECT DISTINCT series_id FROM tv_calendar_cache")
    return [row["series_id"] for row in rows]


def delete_calendar_cache_for_series(series_ids) -> int:
    if not series_ids:
        return 0
    placeholders = ",".join(["?"] * len(series_ids))
    return system_store.execute(
        f"DELETE FROM tv_calendar_cache WHERE series_id IN ({placeholders})",
        series_ids,
    )


def list_ended_series_tmdb_ids():
    rows = system_store.fetch_all("SELECT tmdb_id FROM tv_series_status WHERE status = 'ended'")
    return {row["tmdb_id"] for row in rows}


def save_series_status(tmdb_id, series_name, status, checked_at: str) -> None:
    system_store.execute(
        """
        INSERT OR REPLACE INTO tv_series_status
        (tmdb_id, series_name, status, last_checked, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (tmdb_id, series_name, status, checked_at, checked_at),
    )
