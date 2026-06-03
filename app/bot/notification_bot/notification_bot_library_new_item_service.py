import datetime
import logging
import re

from app.core.config import REPORT_COVER_URL
from app.infra.config.media_server_settings import (
    get_media_server_host,
    get_media_server_main_public_or_host,
)
from app.infra.config.notification_settings import get_enable_library_notify


logger = logging.getLogger("uvicorn")


def _default_get_plugin(plugin_name):
    from app.plugins import get_plugin

    return get_plugin(plugin_name)


_enable_library_notify_provider = lambda: get_enable_library_notify
_media_quality_info_provider = lambda: (lambda _item_id: {})
_media_server_main_public_or_host_provider = lambda: get_media_server_main_public_or_host
_media_server_host_provider = lambda: get_media_server_host
_notify_channels_provider = lambda: (lambda _notify_type: [])
_get_plugin_provider = lambda: _default_get_plugin
_report_cover_url_provider = lambda: REPORT_COVER_URL
_datetime_provider = lambda: datetime
_re_provider = lambda: re
_logger_provider = lambda: logger


def set_dependency_providers(
    *,
    enable_library_notify_provider=None,
    media_quality_info_provider=None,
    media_server_main_public_or_host_provider=None,
    media_server_host_provider=None,
    notify_channels_provider=None,
    get_plugin_provider=None,
    report_cover_url_provider=None,
    datetime_provider=None,
    re_provider=None,
    logger_provider=None,
):
    global _enable_library_notify_provider
    global _media_quality_info_provider
    global _media_server_main_public_or_host_provider
    global _media_server_host_provider
    global _notify_channels_provider
    global _get_plugin_provider
    global _report_cover_url_provider
    global _datetime_provider
    global _re_provider
    global _logger_provider

    if enable_library_notify_provider is not None:
        _enable_library_notify_provider = enable_library_notify_provider
    if media_quality_info_provider is not None:
        _media_quality_info_provider = media_quality_info_provider
    if media_server_main_public_or_host_provider is not None:
        _media_server_main_public_or_host_provider = media_server_main_public_or_host_provider
    if media_server_host_provider is not None:
        _media_server_host_provider = media_server_host_provider
    if notify_channels_provider is not None:
        _notify_channels_provider = notify_channels_provider
    if get_plugin_provider is not None:
        _get_plugin_provider = get_plugin_provider
    if report_cover_url_provider is not None:
        _report_cover_url_provider = report_cover_url_provider
    if datetime_provider is not None:
        _datetime_provider = datetime_provider
    if re_provider is not None:
        _re_provider = re_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def _format_overview(item):
    overview = str(item.get("Overview") or "")
    overview = _re_provider().sub(r"<[^>]+>", "", overview).strip()
    if not overview:
        overview = "暂无简介..."
    if len(overview) > 150:
        overview = overview[:140] + "..."
    return overview


def _format_type(type_raw):
    type_cn = "电影"
    type_icon = "🎬"
    if type_raw in ["Series", "Episode"]:
        type_cn = "剧集"
        type_icon = "📺"
    return type_cn, type_icon


def _get_base_url():
    base_url = _media_server_main_public_or_host_provider()() or _media_server_host_provider()()
    if base_url and not base_url.startswith(("http://", "https://")):
        base_url = "https://" + base_url
    return base_url


def _render_caption(tpl_vars, type_icon, type_cn, name, year, rating, overview):
    try:
        tpl_plugin = _get_plugin_provider()("notify_template")
        if tpl_plugin and tpl_plugin.enabled:
            return tpl_plugin.render("library_new_item", tpl_vars)
        raise Exception("fallback")
    except Exception as e:
        _logger_provider().warning(f"[入库通知] 模板渲染失败，使用默认模板: {e}")
        return (
            f"{type_icon} <b>新入库 {type_cn} {name}</b> ({year})\n\n⭐ 评分：{rating} / 10\n"
            f"🕒 时间：{_datetime_provider().datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            f"📝 <b>剧情简介：</b>\n{overview}"
        )


def _get_platform(channels):
    return (
        "all"
        if "tg_bot" in channels and "wecom" in channels
        else "tg"
        if "tg_bot" in channels
        else "wecom"
        if "wecom" in channels
        else "none"
    )


def handle_library_new_item(bot, item):
    if not _enable_library_notify_provider()():
        return

    try:
        name = item.get("Name", "未知")
        year = item.get("ProductionYear", "")
        rating = item.get("CommunityRating", "N/A")
        overview = _format_overview(item)

        type_raw = item.get("Type")
        type_cn, type_icon = _format_type(type_raw)

        quality_info = _media_quality_info_provider()(item.get("Id", ""))

        base_url = _get_base_url()
        play_url = f"{base_url}/web/index.html#!/item?id={item['Id']}&serverId={item.get('ServerId','')}"

        tpl_vars = {
            "name": name,
            "type_icon": type_icon,
            "type_cn": type_cn,
            "year": year,
            "rating": rating,
            "time": _datetime_provider().datetime.now().strftime("%Y-%m-%d %H:%M"),
            "overview": overview,
            "quality": quality_info.get("quality", ""),
            "quality_icon": quality_info.get("quality_icon", "🎬"),
            "video_codec": quality_info.get("video_codec", ""),
            "audio_codec": quality_info.get("audio_codec", ""),
            "resolution": quality_info.get("resolution", ""),
            "hdr": quality_info.get("hdr", ""),
        }
        caption = _render_caption(tpl_vars, type_icon, type_cn, name, year, rating, overview)

        keyboard = None
        if base_url and base_url.startswith(("http://", "https://")):
            keyboard = {"inline_keyboard": [[{"text": "▶️ 立即播放", "url": play_url}]]}

        primary_io = bot._download_emby_image(item["Id"], "Primary")
        backdrop_io = bot._download_emby_image(item["Id"], "Backdrop")
        tg_img = backdrop_io or primary_io or _report_cover_url_provider()
        wecom_img = backdrop_io or primary_io or _report_cover_url_provider()

        channels = _notify_channels_provider()("library_new")
        platform = _get_platform(channels)

        if platform != "none":
            bot.send_photo(
                "sys_notify",
                tg_img,
                caption,
                reply_markup=keyboard,
                platform=platform,
                wecom_photo_io=wecom_img,
            )

        if "tg_channel" in channels:
            bot._notify_channels(tg_img, caption, keyboard, type_raw.lower() if type_raw else "movie", item)
    except Exception as e:
        _logger_provider().error(f"[入库通知] 处理失败: {e}")
