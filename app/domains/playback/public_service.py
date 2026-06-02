"""Public playback facade for cross-domain callers."""

from app.domains.playback import stats_queries


def get_user_play_summary(user_id: str, start_str: str, end_str: str):
    return stats_queries.get_user_play_summary(user_id, start_str, end_str)
