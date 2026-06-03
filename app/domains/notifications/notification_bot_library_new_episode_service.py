import datetime
import logging
import re
from collections import defaultdict

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


def _format_episode_suffix(episodes):
    season_groups = defaultdict(list)
    for ep in episodes:
        season_groups[ep.get("ParentIndexNumber", 1)].append(ep)

    season_strs = []
    total_eps = 0

    for s_idx in sorted(season_groups.keys()):
        s_eps = season_groups[s_idx]
        ep_indices = sorted(list(set([e.get("IndexNumber", 0) for e in s_eps if e.get("IndexNumber") is not None])))
        total_eps += len(ep_indices)
        if len(ep_indices) > 1:
            ranges = []
            start = ep_indices[0]
            end = ep_indices[0]
            for idx in ep_indices[1:]:
                if idx == end + 1:
                    end = idx
                else:
                    ranges.append(f"E{str(start).zfill(2)}" if start == end else f"E{str(start).zfill(2)}-E{str(end).zfill(2)}")
                    start = idx
                    end = idx
            ranges.append(f"E{str(start).zfill(2)}" if start == end else f"E{str(start).zfill(2)}-E{str(end).zfill(2)}")
            season_strs.append(f"S{str(s_idx).zfill(2)}{', '.join(ranges)}")
        elif len(ep_indices) == 1:
            season_strs.append(f"S{str(s_idx).zfill(2)}E{str(ep_indices[0]).zfill(2)}")

    final_ep_str = ", ".join(season_strs)
    title_suffix = f"{final_ep_str} (共{total_eps}集)" if total_eps > 1 else final_ep_str

    if total_eps == 1 and len(episodes) == 1:
        ep_name = episodes[0].get("Name", "")
        if ep_name and "Episode" not in ep_name and "第" not in ep_name:
            title_suffix += f" {ep_name}"

    return title_suffix


def _format_overview(series_info):
    overview = str(series_info.get("Overview") or "")
    overview = _re_provider().sub(r"<[^>]+>", "", overview).strip()
    if not overview:
        overview = "暂无简介..."
    if len(overview) > 150:
        overview = overview[:140] + "..."
    return overview


def _get_quality_info(episodes):
    quality_info = {"quality": "", "video_codec": "", "audio_codec": "", "resolution": "", "hdr": "", "quality_icon": ""}
    if episodes:
        ep_id = episodes[0].get("Id", "")
        _logger_provider().info(f"[媒体质量] 准备获取剧集质量信息: ep_id={ep_id}")
        quality_info = _media_quality_info_provider()(ep_id)
        _logger_provider().info(f"[媒体质量] 获取结果: {quality_info}")
    return quality_info


def _get_base_url():
    base_url = _media_server_main_public_or_host_provider()() or _media_server_host_provider()()
    if base_url and not base_url.startswith(("http://", "https://")):
        base_url = "https://" + base_url
    return base_url


def _render_caption(tpl_vars, series_name, title_suffix, year, rating, overview):
    try:
        tpl_plugin = _get_plugin_provider()("notify_template")
        if tpl_plugin and tpl_plugin.enabled:
            return tpl_plugin.render("library_new_episode", tpl_vars)
        raise Exception("fallback")
    except:
        return (
            f"📺 <b>新入库 剧集 {series_name}</b> {title_suffix}\n\n📌 年份：{year}  |  ⭐ 评分：{rating}\n"
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


def handle_library_new_episode(bot, data):
    if not _enable_library_notify_provider()():
        return

    series_id = data["series_id"]
    episodes = data["episodes"]
    series_info = data["series_info"]

    title_suffix = _format_episode_suffix(episodes)
    series_name = series_info.get("Name", "未知剧集")
    year = series_info.get("ProductionYear", "")
    rating = series_info.get("CommunityRating", "N/A")
    overview = _format_overview(series_info)
    quality_info = _get_quality_info(episodes)

    base_url = _get_base_url()
    play_url = f"{base_url}/web/index.html#!/item?id={series_id}&serverId={series_info.get('ServerId','')}"

    tpl_vars = {
        "series_name": series_name,
        "episode_info": title_suffix,
        "year": year,
        "rating": rating,
        "time": _datetime_provider().datetime.now().strftime("%Y-%m-%d %H:%M"),
        "overview": overview,
        "quality": quality_info.get("quality", ""),
        "quality_icon": quality_info.get("quality_icon", "📺"),
        "video_codec": quality_info.get("video_codec", ""),
        "audio_codec": quality_info.get("audio_codec", ""),
        "resolution": quality_info.get("resolution", ""),
        "hdr": quality_info.get("hdr", ""),
    }
    caption = _render_caption(tpl_vars, series_name, title_suffix, year, rating, overview)

    keyboard = None
    if base_url and base_url.startswith(("http://", "https://")):
        keyboard = {"inline_keyboard": [[{"text": "▶️ 立即播放", "url": play_url}]]}

    primary_io = bot._download_emby_image(series_id, "Primary")
    backdrop_io = bot._download_emby_image(series_id, "Backdrop")
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
        bot._notify_channels(tg_img, caption, keyboard, "episode", series_info)
