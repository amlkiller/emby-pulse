from app.core.config import cfg
from app.infra.db.playback_store import get_playback_column_name, playback_store


def build_stats_base_filter(user_id_filter):
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


def query_stats(sql: str, params=(), one: bool = False):
    return playback_store.query(sql, params, one=one)
