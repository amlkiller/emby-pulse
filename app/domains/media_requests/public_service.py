"""Public media requests facade for cross-domain callers."""

from app.domains.media_requests import gap_dao


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
