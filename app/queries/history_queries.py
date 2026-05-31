from app.infra.db.local_playback_store import fetch_playback_ip_rows
from app.infra.db.playback_store import get_playback_column_name, playback_store


CORE_PLAYBACK_COLUMNS = ["DateCreated", "UserId", "ItemId", "ItemName", "PlayDuration"]


def get_available_playback_columns():
    rows = playback_store.query("SELECT * FROM PlaybackActivity LIMIT 1", [])
    if rows:
        first_row = rows[0]
        if hasattr(first_row, "keys"):
            return list(first_row.keys())
        if isinstance(first_row, dict):
            return list(first_row.keys())
    return CORE_PLAYBACK_COLUMNS.copy()


def build_history_select_fields():
    available_columns = get_available_playback_columns()
    extra_columns = [column for column in available_columns if column not in CORE_PLAYBACK_COLUMNS]
    return CORE_PLAYBACK_COLUMNS + extra_columns


def count_history(where_sql: str, params):
    rows = playback_store.query(f"SELECT COUNT(*) as c FROM PlaybackActivity{where_sql}", params)
    return rows[0]["c"] if rows else 0


def fetch_history_rowids(where_sql: str, params, limit: int, offset: int):
    sql = f"SELECT rowid FROM PlaybackActivity{where_sql} ORDER BY DateCreated DESC LIMIT ? OFFSET ?"
    return playback_store.query(sql, params + [limit, offset]) or []


def fetch_history_rows_by_rowids(select_fields, rowids):
    if not rowids:
        return []
    placeholders = ",".join(["?" for _ in rowids])
    sql = (
        f"SELECT {', '.join(select_fields)} FROM PlaybackActivity "
        f"WHERE rowid IN ({placeholders}) ORDER BY DateCreated DESC"
    )
    return playback_store.query(sql, rowids) or []


def fetch_history_rows(select_fields, where_sql: str, params, limit: int, offset: int):
    sql = (
        f"SELECT {', '.join(select_fields)} FROM PlaybackActivity{where_sql} "
        "ORDER BY DateCreated DESC LIMIT ? OFFSET ?"
    )
    return playback_store.query(sql, params + [limit, offset]) or []


def count_today_plays(today_start: str, today_end: str, filter_sql: str, params):
    sql = f"SELECT COUNT(*) as c FROM PlaybackActivity WHERE DateCreated >= ? AND DateCreated < ?{filter_sql}"
    rows = playback_store.query(sql, [today_start, today_end] + params)
    return rows[0]["c"] if rows and rows[0]["c"] else 0


def sum_today_duration(today_start: str, today_end: str, filter_sql: str, params):
    sql = f"SELECT SUM(PlayDuration) as total FROM PlaybackActivity WHERE DateCreated >= ? AND DateCreated < ?{filter_sql}"
    rows = playback_store.query(sql, [today_start, today_end] + params)
    return rows[0]["total"] if rows and rows[0]["total"] else 0


def count_today_active_users(today_start: str, today_end: str, filter_sql: str, params):
    sql = f"SELECT COUNT(DISTINCT UserId) as c FROM PlaybackActivity WHERE DateCreated >= ? AND DateCreated < ?{filter_sql}"
    rows = playback_store.query(sql, [today_start, today_end] + params)
    return rows[0]["c"] if rows and rows[0]["c"] else 0


def count_total_plays(filter_sql: str, params):
    rows = playback_store.query(f"SELECT COUNT(*) as c FROM PlaybackActivity WHERE 1=1{filter_sql}", params)
    return rows[0]["c"] if rows and rows[0]["c"] else 0


def fetch_local_ip_data(rows):
    local_ip_data = {}
    if not rows:
        return local_ip_data

    try:
        item_ids = [row["ItemId"] for row in rows if row.get("ItemId")]
        user_ids = [row["UserId"] for row in rows if row.get("UserId")]
        if not item_ids or not user_ids:
            return local_ip_data

        for row in fetch_playback_ip_rows(item_ids, user_ids):
            key = str(row["UserId"]) + "_" + str(row["ItemId"])
            if key not in local_ip_data:
                local_ip_data[key] = {
                    "ip": row["RemoteEndPoint"] or "",
                    "location": row["Location"] or "",
                    "isp": row["ISP"] or "",
                }
    except Exception as exc:
        print(f"[IP补充] 加载本地IP数据失败: {exc}")
    return local_ip_data
