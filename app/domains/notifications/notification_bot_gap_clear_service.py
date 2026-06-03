from app.domains.media_requests import gap_dao
from app.domains.media_requests.public_service import remove_gap_from_scan_state


_gap_dao_provider = lambda: gap_dao
_remove_gap_from_scan_state_provider = lambda: remove_gap_from_scan_state


def set_dependency_providers(
    *,
    gap_dao_provider=None,
    remove_gap_from_scan_state_provider=None,
):
    global _gap_dao_provider
    global _remove_gap_from_scan_state_provider

    if gap_dao_provider is not None:
        _gap_dao_provider = gap_dao_provider
    if remove_gap_from_scan_state_provider is not None:
        _remove_gap_from_scan_state_provider = remove_gap_from_scan_state_provider


def clear_gap_record(item: dict):
    try:
        if item.get("Type") != "Episode":
            return
        series_id = str(item.get("SeriesId"))
        season = int(item.get("ParentIndexNumber", -1))
        episode = int(item.get("IndexNumber", -1))
        if season == -1 or episode == -1:
            return

        _gap_dao_provider().delete_gap_record_by_series_episode(series_id, season, episode)
        try:
            _remove_gap_from_scan_state_provider()(series_id, season, episode)
        except Exception:
            pass
    except Exception:
        pass
