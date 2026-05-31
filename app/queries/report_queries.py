from app.core.config import cfg
from app.infra.db.playback_store import playback_store


def build_report_base_filter(user_id_filter):
    where = "WHERE 1=1"
    params = []

    if user_id_filter and user_id_filter != "all":
        where += " AND UserId = ?"
        params.append(user_id_filter)

    hidden = cfg.get("hidden_users")
    if (not user_id_filter or user_id_filter == "all") and hidden and len(hidden) > 0:
        placeholders = ",".join(["?"] * len(hidden))
        where += f" AND UserId NOT IN ({placeholders})"
        params.extend(hidden)

    return where, params


def count_report_plays(where_sql: str, params):
    rows = playback_store.query(f"SELECT COUNT(*) as c FROM PlaybackActivity {where_sql}", params)
    return rows[0]["c"] if rows else 0


def sum_report_duration(where_sql: str, params):
    rows = playback_store.query(f"SELECT SUM(PlayDuration) as c FROM PlaybackActivity {where_sql}", params)
    return rows[0]["c"] if rows and rows[0]["c"] else 0


def list_report_top_items(where_sql: str, params, limit: int = 8):
    return playback_store.query(
        f"""
        SELECT ItemName, ItemId, COUNT(*) as C, SUM(PlayDuration) as D
        FROM PlaybackActivity {where_sql}
        GROUP BY ItemName
        ORDER BY C DESC
        LIMIT ?
        """,
        list(params) + [limit],
    ) or []


def list_report_ranked_items(where_sql: str, exclude_sql: str, exclude_types, limit: int):
    params = list(exclude_types) + [limit] if exclude_types else [limit]
    return playback_store.query(
        f"""
        SELECT ItemName, ItemId, ItemType, COUNT(*) as C, COALESCE(SUM(PlayDuration), 0) as Duration
        FROM PlaybackActivity {where_sql}{exclude_sql}
        GROUP BY ItemName
        ORDER BY Duration DESC
        LIMIT ?
        """,
        params,
    ) or []
