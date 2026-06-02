"""Public media requests facade for cross-domain callers."""

from app.domains.media_requests import gap_dao, media_request_dao


def submit_single_media_request(
    user_id,
    username,
    tmdb_id,
    media_type,
    title,
    year,
    poster,
    season=0,
):
    return media_request_dao.submit_single_media_request(
        user_id,
        username,
        tmdb_id,
        media_type,
        title,
        year,
        poster,
        season,
    )


def list_user_recent_requests(user_id: str, limit: int = 10):
    return media_request_dao.list_user_recent_requests(user_id, limit)


def finish_media_requests_for_item(tmdb_id, season=None):
    return media_request_dao.finish_media_requests_for_item(tmdb_id, season)


def list_tg_bindings(user_ids):
    return media_request_dao.list_tg_bindings(user_ids)


def list_pending_sync_requests():
    return media_request_dao.list_pending_sync_requests()


def mark_sync_request_finished(tmdb_id, season=None) -> None:
    media_request_dao.mark_sync_request_finished(tmdb_id, season)


def update_feedback_status(feedback_id: int, status: int) -> None:
    media_request_dao.update_feedback_status(feedback_id, status)


def get_request_summary_by_tmdb(tmdb_id):
    return media_request_dao.get_request_summary_by_tmdb(tmdb_id)


def list_pending_requests_by_tmdb(tmdb_id):
    return media_request_dao.list_pending_requests_by_tmdb(tmdb_id)


def update_media_request_status(tmdb_id, season, status, reject_reason=None) -> None:
    media_request_dao.update_media_request_status(tmdb_id, season, status, reject_reason)


def delete_gap_record_by_series_episode(series_id, season, episode) -> None:
    gap_dao.delete_gap_record_by_series_episode(series_id, season, episode)


def delete_cleared_gap_record(series_id, season, episode) -> bool:
    return gap_dao.delete_cleared_gap_record(series_id, season, episode)


def remove_gap_from_scan_state(series_id, season, episode) -> None:
    from app.domains.media_requests.gaps import scan_state, state_lock

    with state_lock:
        if not scan_state.get("results"):
            return
        for series in scan_state["results"]:
            if str(series.get("series_id")) != str(series_id):
                continue
            series["gaps"] = [
                gap
                for gap in series.get("gaps", [])
                if not (
                    int(gap.get("season")) == int(season)
                    and int(gap.get("episode")) == int(episode)
                )
            ]
            if len(series["gaps"]) == 0 and series.get("tmdb_status") in ["Ended", "Canceled"]:
                try:
                    gap_dao.add_gap_perfect_series(
                        series_id,
                        series.get("tmdb_id"),
                        series.get("series_name"),
                    )
                except Exception:
                    pass
        scan_state["results"] = [
            series
            for series in scan_state["results"]
            if len(series.get("gaps", [])) > 0
        ]
        gap_dao.save_gap_scan_cache(scan_state["results"])
