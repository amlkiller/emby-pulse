import io
import ipaddress
import logging

from app.infra.clients.media_server_client import media_api
from app.infra.db.local_playback_store import insert_bot_playback_history_record
from app.utils.ip_location import get_isp


logger = logging.getLogger("uvicorn")

_media_api_provider = lambda: media_api
_get_isp_provider = lambda: get_isp
_insert_playback_history_provider = lambda: insert_bot_playback_history_record
_logger_provider = lambda: logger


def set_dependency_providers(
    *,
    media_api_provider=None,
    get_isp_provider=None,
    insert_playback_history_provider=None,
    logger_provider=None,
):
    global _media_api_provider
    global _get_isp_provider
    global _insert_playback_history_provider
    global _logger_provider

    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if get_isp_provider is not None:
        _get_isp_provider = get_isp_provider
    if insert_playback_history_provider is not None:
        _insert_playback_history_provider = insert_playback_history_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def download_user_image(user_id):
    if not user_id:
        return None
    try:
        params = {"maxHeight": 400, "maxWidth": 400, "quality": 90}
        res = _media_api_provider().get(f"/Users/{user_id}/Images/Primary", params=params, timeout=5)
        if res.status_code == 200:
            return io.BytesIO(res.content)
    except Exception:
        pass
    return None


def get_username(bot, user_id):
    if user_id in bot.user_cache:
        return bot.user_cache[user_id]
    try:
        res = _media_api_provider().get("/Users", timeout=2)
        if res.status_code == 200:
            for user in res.json():
                bot.user_cache[user["Id"]] = user["Name"]
    except Exception:
        pass
    return bot.user_cache.get(user_id, "Unknown User")


def get_subnet_key(ip):
    try:
        ip_obj = ipaddress.ip_address(ip)
        if ip_obj.version == 6:
            parts = ip_obj.exploded.split(":")
            return ":".join(parts[:4]) + "::/64"
        return ip
    except Exception:
        return ip


def save_playback_history(data, user_id, user_name, item, ip, location):
    """保存播放历史到本地数据库"""
    try:
        isp = _get_isp_provider()(ip)
        item_id = item.get("Id", "")
        item_name = item.get("Name", "未知内容")
        item_type = item.get("Type", "Unknown")
        session = data.get("Session") or data
        client = session.get("Client") or data.get("Client", "")
        device = session.get("DeviceName") or data.get("DeviceName", "")
        _insert_playback_history_provider()(user_id, user_name, item_id, item_name, item_type, client, device, ip, location, isp)
    except Exception as e:
        _logger_provider().error(f"[Playback] 保存历史记录失败: {e}")


def download_emby_image(item_id, img_type="Primary", image_tag=None):
    if not item_id:
        return None
    try:
        params = {"maxHeight": 800, "maxWidth": 600, "quality": 90}
        if image_tag:
            params["tag"] = image_tag
        res = _media_api_provider().get(f"/Items/{item_id}/Images/{img_type}", params=params, timeout=15)
        if res.status_code == 200:
            return io.BytesIO(res.content)
    except Exception:
        pass
    return None
