"""Public playback facade for cross-domain callers."""

from app.domains.playback import stats_queries


def get_user_play_summary(user_id: str, start_str: str, end_str: str):
    return stats_queries.get_user_play_summary(user_id, start_str, end_str)


def _get_stats():
    from app.domains.playback import stats

    return stats


def api_latest_media(request=None, limit: int = 60):
    return _get_stats().api_latest_media(request=request, limit=limit)


def api_top_movies(
    request=None,
    user_id=None,
    category: str = "all",
    sort_by: str = "count",
    exclude_types=None,
    period: str = "all",
):
    return _get_stats().api_top_movies(
        request=request,
        user_id=user_id,
        category=category,
        sort_by=sort_by,
        exclude_types=exclude_types,
        period=period,
    )
