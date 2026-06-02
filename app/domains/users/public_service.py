"""Public users facade for cross-domain callers."""

import time

from app.domains.users import user_bot_dao, user_dao
from app.infra.clients.media_server_client import media_api


_emby_users_cache = {"data": None, "expires": 0}
EMBY_USERS_CACHE_TTL = 30


def is_admin_user(request) -> bool:
    from app.domains.users.auth import is_admin_user as auth_is_admin_user

    return auth_is_admin_user(request)


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


def delete_user_meta_many(user_ids):
    return user_dao.delete_user_meta_many(user_ids)


def get_user_display_name(user_id: str):
    return user_dao.get_user_display_name(user_id)


def list_user_ids_with_expire_date():
    return user_dao.list_user_ids_with_expire_date()


def list_users_with_expire_date():
    return user_dao.list_users_with_expire_date()


def list_permanent_user_expire_records():
    return user_dao.list_permanent_user_expire_records()


def get_tg_user_id_by_emby_id(emby_user_id):
    return user_bot_dao.get_tg_user_id_by_emby_id(emby_user_id)


def get_binding_by_emby_id(emby_user_id):
    return user_bot_dao.get_binding_by_emby_id(emby_user_id)


def get_user_meta(user_id: str):
    return user_dao.get_user_meta(user_id)


def list_all_user_meta():
    return user_dao.list_all_user_meta()


def upsert_user_meta_fields(user_id: str, fields: dict, created_at: str) -> None:
    user_dao.upsert_user_meta_fields(user_id, fields, created_at)
