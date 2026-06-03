import logging

from app.infra.clients.media_server_client import media_api


logger = logging.getLogger("uvicorn")

_media_api_provider = lambda: media_api
_admin_id_provider = lambda: _default_get_admin_id
_logger_provider = lambda: logger


def _default_get_admin_id():
    return None


def set_dependency_providers(
    *,
    media_api_provider=None,
    admin_id_provider=None,
    logger_provider=None,
):
    global _media_api_provider
    global _admin_id_provider
    global _logger_provider

    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if admin_id_provider is not None:
        _admin_id_provider = admin_id_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def cmd_latest(bot, cid, platform):
    try:
        user_id = _admin_id_provider()()
        if not user_id:
            return bot.send_message(cid, "❌ 错误: 无法获取 Emby 用户身份", platform=platform)

        fields = "DateCreated,Name,SeriesName,Type,ParentIndexNumber,IndexNumber"
        params = {"IncludeItemTypes": "Movie,Episode", "Limit": 8, "Fields": fields}

        res = _media_api_provider().get(f"/Users/{user_id}/Items/Latest", params=params, timeout=10)
        if res.status_code != 200:
            return bot.send_message(cid, f"❌ 查询失败", platform=platform)

        items = res.json()
        if not items:
            return bot.send_message(cid, "📭 最近没有新入库的资源", platform=platform)

        msg = "🆕 <b>最近入库 (Top 8)</b>\n\n"
        for i in items:
            name = i.get("Name", "未知")
            item_type = i.get("Type")

            if item_type == "Episode" and i.get("SeriesName"):
                s_idx = str(i.get("ParentIndexNumber", 0)).zfill(2) if i.get("ParentIndexNumber") is not None else "01"
                e_idx = str(i.get("IndexNumber", 0)).zfill(2) if i.get("IndexNumber") is not None else "XX"
                name = f"《{i.get('SeriesName')}》 S{s_idx}E{e_idx} {name}"
            elif item_type == "Movie":
                name = f"《{name}》"

            date_raw = i.get("DateCreated")
            date_str = date_raw[:10] if date_raw else "未知时间"
            type_icon = "🎬" if item_type == "Movie" else "📺"

            msg += f"{type_icon} <code>{date_str}</code> | <b>{name}</b>\n"

        bot.send_message(cid, msg.strip(), platform=platform)
    except Exception as e:
        _logger_provider().error(f"[Bot] latest query error: {e}")
        bot.send_message(cid, f"❌ 查询异常", platform=platform)
