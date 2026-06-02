"""Shared template context helpers."""

import json

from app.infra.clients.media_server_client import media_api
from app.infra.config.media_server_settings import get_media_server_main_public_or_host
from app.shared.version import APP_VERSION


def get_common_vars(request, active_page: str, extra_vars: dict = None):
    emby_url = get_media_server_main_public_or_host()
    emby_url = emby_url.strip().rstrip("/")

    server_id = ""
    try:
        sys_res = media_api.get("/System/Info", timeout=2)
        if sys_res.status_code == 200:
            raw_id = sys_res.json().get("Id", "")
            if raw_id:
                server_id = str(raw_id).replace("\r", "").replace("\n", "").strip()
    except Exception:
        pass

    user = request.session.get("user", {})
    user_permissions = user.get("permissions", [])
    if isinstance(user_permissions, str):
        try:
            user_permissions = json.loads(user_permissions)
        except Exception:
            user_permissions = []

    vars_dict = {
        "request": request,
        "version": APP_VERSION,
        "active_page": active_page,
        "emby_url": emby_url,
        "server_id": server_id,
        "is_pro": True,
        "user_permissions": user_permissions,
        "is_admin": user.get("auth_type") == "emby" or user.get("role") == "admin",
        "user_name": user.get("name", "用户"),
        "user_avatar": user.get("avatar", ""),
    }
    if extra_vars:
        vars_dict.update(extra_vars)
    return vars_dict
