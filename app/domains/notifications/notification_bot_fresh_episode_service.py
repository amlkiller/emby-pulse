import datetime

from app.infra.clients.media_server_client import media_api


_admin_id_provider = lambda: (lambda: None)
_datetime_provider = lambda: datetime
_media_api_provider = lambda: media_api


def set_dependency_providers(
    *,
    admin_id_provider=None,
    datetime_provider=None,
    media_api_provider=None,
):
    global _admin_id_provider
    global _datetime_provider
    global _media_api_provider

    if admin_id_provider is not None:
        _admin_id_provider = admin_id_provider
    if datetime_provider is not None:
        _datetime_provider = datetime_provider
    if media_api_provider is not None:
        _media_api_provider = media_api_provider


def check_fresh_episodes(series_id, parse_time_func=None):
    admin_id = _admin_id_provider()()
    if not admin_id:
        return []
    try:
        params = {
            "ParentId": series_id,
            "Recursive": "true",
            "IncludeItemTypes": "Episode",
            "Limit": 1000,
            "SortBy": "DateCreated",
            "SortOrder": "Descending",
            "Fields": "DateCreated,Name,ParentIndexNumber,IndexNumber",
        }
        res = _media_api_provider().get(f"/Users/{admin_id}/Items", params=params, timeout=10)
        if res.status_code != 200:
            return []
        items = res.json().get("Items", [])
        if not items:
            return []
        fresh_list = []
        last_time = None
        for i, item in enumerate(items):
            curr_time = (parse_time_func or parse_emby_time)(item.get("DateCreated"))
            if not curr_time:
                if i == 0:
                    fresh_list.append(item)
                break
            if i == 0:
                fresh_list.append(item)
                last_time = curr_time
            else:
                delta = abs((last_time - curr_time).total_seconds())
                if delta <= 120:
                    fresh_list.append(item)
                    last_time = curr_time
                else:
                    break
        return fresh_list
    except Exception:
        return []


def parse_emby_time(date_str):
    if not date_str:
        return None
    try:
        clean_str = date_str.replace("Z", "")[:26]
        if "." in clean_str:
            return _datetime_provider().datetime.strptime(clean_str, "%Y-%m-%dT%H:%M:%S.%f")
        return _datetime_provider().datetime.strptime(clean_str, "%Y-%m-%dT%H:%M:%S")
    except Exception:
        return None
