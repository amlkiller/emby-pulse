from app.infra.db.playback_store import get_playback_column_name, playback_store


def count_playback_clients_by_app():
    client_col = get_playback_column_name()
    return playback_store.query(
        f"""
        SELECT COALESCE({client_col}, '未知客户端') as c_name, COUNT(*) as cnt
        FROM PlaybackActivity
        WHERE {client_col} IS NOT NULL AND {client_col} != ''
        GROUP BY {client_col}
        """
    ) or []


def count_playback_devices(limit: int = 10):
    return playback_store.query(
        """
        SELECT DeviceName, COUNT(*) as cnt
        FROM PlaybackActivity
        WHERE DeviceName IS NOT NULL AND DeviceName != ''
        GROUP BY DeviceName
        ORDER BY cnt DESC
        LIMIT ?
        """,
        (limit,),
    ) or []
