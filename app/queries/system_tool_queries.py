from app.infra.db.playback_store import playback_store


def get_latest_playback_date():
    row = playback_store.query(
        "SELECT DateCreated FROM PlaybackActivity ORDER BY DateCreated DESC LIMIT 1",
        one=True,
    )
    return row["DateCreated"] if row and row["DateCreated"] else None
