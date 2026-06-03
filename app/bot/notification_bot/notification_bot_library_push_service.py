from app.core.event_bus import bus
from app.domains.media_requests import gap_dao
from app.infra.clients.media_server_client import media_api


_bus_provider = lambda: bus
_gap_dao_provider = lambda: gap_dao
_media_api_provider = lambda: media_api
_admin_id_provider = lambda: (lambda: None)


def set_dependency_providers(
    *,
    admin_id_provider=None,
    bus_provider=None,
    gap_dao_provider=None,
    media_api_provider=None,
):
    global _admin_id_provider
    global _bus_provider
    global _gap_dao_provider
    global _media_api_provider

    if admin_id_provider is not None:
        _admin_id_provider = admin_id_provider
    if bus_provider is not None:
        _bus_provider = bus_provider
    if gap_dao_provider is not None:
        _gap_dao_provider = gap_dao_provider
    if media_api_provider is not None:
        _media_api_provider = media_api_provider


def push_episode_group(daemon, series_id, episodes):
    admin_id = _admin_id_provider()()
    series_info = {}

    try:
        res = _media_api_provider().get(f"/Users/{admin_id}/Items/{series_id}", timeout=10)
        if res.status_code == 200:
            series_info = res.json()
    except Exception:
        pass
    if not series_info:
        series_info = episodes[0]

    series_name = series_info.get("Name", "未知剧集")

    try:
        for ep in episodes:
            s_idx = ep.get("ParentIndexNumber")
            e_idx = ep.get("IndexNumber")
            if s_idx is None or e_idx is None:
                continue
            if _gap_dao_provider().delete_cleared_gap_record(series_id, s_idx, e_idx):
                _bus_provider().publish(
                    "notify.gap_cleared",
                    {"s_idx": s_idx, "e_idx": e_idx, "series_name": series_name},
                )
    except Exception:
        pass

    st_tmdb = series_info.get("ProviderIds", {}).get("Tmdb")
    if st_tmdb:
        added_seasons = set()
        for ep in episodes:
            s_idx = ep.get("ParentIndexNumber")
            if s_idx is not None:
                added_seasons.add(s_idx)
        for season in added_seasons:
            daemon._auto_finish_request(st_tmdb, season=season)

    _bus_provider().publish(
        "notify.library.new_episode",
        {"series_id": series_id, "episodes": episodes, "series_info": series_info},
    )


def push_single_item(daemon, item):
    try:
        res = _media_api_provider().get(f"/Items/{item['Id']}", timeout=10)
        if res.status_code == 200:
            item = res.json()
    except Exception:
        pass
    tmdb_id = item.get("ProviderIds", {}).get("Tmdb")
    if tmdb_id:
        daemon._auto_finish_request(tmdb_id)
    _bus_provider().publish("notify.library.new_item", item)
