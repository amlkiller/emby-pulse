"""Public users facade for cross-domain callers."""

import time

from app.infra.clients.media_server_client import media_api


_emby_users_cache = {"data": None, "expires": 0}
EMBY_USERS_CACHE_TTL = 30


def is_admin_user(request) -> bool:
    from app.domains.users.auth import is_admin_user as auth_is_admin_user

    return auth_is_admin_user(request)


def check_permission(request, page: str) -> bool:
    from app.domains.users.auth import check_permission as auth_check_permission

    return auth_check_permission(request, page)


def get_page_permission_map() -> dict:
    from app.domains.users.auth import PAGE_PERMISSION_MAP

    return PAGE_PERMISSION_MAP


def get_emby_users_cached():
    """Get Emby users with the same short-lived cache used by the users router."""
    if _emby_users_cache["data"] and time.time() < _emby_users_cache["expires"]:
        return _emby_users_cache["data"]

    try:
        res = media_api.get("/Users", timeout=5)
        if res.status_code == 200:
            users = res.json()
            _emby_users_cache["data"] = users
            _emby_users_cache["expires"] = time.time() + EMBY_USERS_CACHE_TTL
            return users
    except:
        pass
    return None


def invalidate_emby_users_cache():
    """Clear the shared Emby users cache after user changes."""
    _emby_users_cache["data"] = None
    _emby_users_cache["expires"] = 0
