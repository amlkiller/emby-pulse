import datetime

from app.domains.users import user_dao
from app.infra.clients.media_server_client import media_api


_user_dao_provider = lambda: user_dao
_media_api_provider = lambda: media_api
_datetime_provider = lambda: datetime


def set_dependency_providers(
    *,
    user_dao_provider=None,
    media_api_provider=None,
    datetime_provider=None,
):
    global _user_dao_provider
    global _media_api_provider
    global _datetime_provider

    if user_dao_provider is not None:
        _user_dao_provider = user_dao_provider
    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if datetime_provider is not None:
        _datetime_provider = datetime_provider


def check_user_expiration():
    try:
        users = _user_dao_provider().list_users_with_expire_date()
        if not users:
            return
        today = _datetime_provider().datetime.now().strftime("%Y-%m-%d")
        media_api_obj = _media_api_provider()

        for u in users:
            if u["expire_date"] < today:
                try:
                    user_res = media_api_obj.get(f"/Users/{u['user_id']}", timeout=5)
                    if user_res.status_code == 200:
                        policy = user_res.json().get("Policy", {})
                        if not policy.get("IsDisabled", False):
                            policy["IsDisabled"] = True
                            media_api_obj.post(f"/Users/{u['user_id']}/Policy", json=policy, timeout=5)
                except Exception:
                    pass
    except Exception:
        pass
