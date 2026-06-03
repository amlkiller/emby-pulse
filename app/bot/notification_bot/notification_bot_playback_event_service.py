import datetime
import logging
import re

from app.core.config import REPORT_COVER_URL
from app.infra.clients.media_server_client import media_api
from app.infra.config.media_server_settings import (
    get_media_server_host,
    get_media_server_main_public_or_host,
)
from app.infra.config.notification_settings import get_enable_notify
from app.utils.ip_location import get_location


logger = logging.getLogger("uvicorn")


def _default_get_plugin(plugin_name):
    from app.plugins import get_plugin

    return get_plugin(plugin_name)


_enable_notify_provider = lambda: get_enable_notify
_media_api_provider = lambda: media_api
_location_provider = lambda: get_location
_media_server_main_public_or_host_provider = lambda: get_media_server_main_public_or_host
_media_server_host_provider = lambda: get_media_server_host
_get_plugin_provider = lambda: _default_get_plugin
_report_cover_url_provider = lambda: REPORT_COVER_URL
_datetime_provider = lambda: datetime
_re_provider = lambda: re
_logger_provider = lambda: logger


def set_dependency_providers(
    *,
    enable_notify_provider=None,
    media_api_provider=None,
    location_provider=None,
    media_server_main_public_or_host_provider=None,
    media_server_host_provider=None,
    get_plugin_provider=None,
    report_cover_url_provider=None,
    datetime_provider=None,
    re_provider=None,
    logger_provider=None,
):
    global _enable_notify_provider
    global _media_api_provider
    global _location_provider
    global _media_server_main_public_or_host_provider
    global _media_server_host_provider
    global _get_plugin_provider
    global _report_cover_url_provider
    global _datetime_provider
    global _re_provider
    global _logger_provider

    if enable_notify_provider is not None:
        _enable_notify_provider = enable_notify_provider
    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if location_provider is not None:
        _location_provider = location_provider
    if media_server_main_public_or_host_provider is not None:
        _media_server_main_public_or_host_provider = media_server_main_public_or_host_provider
    if media_server_host_provider is not None:
        _media_server_host_provider = media_server_host_provider
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


def _coerce_ticks(value):
    try:
        return int(value)
    except:
        return 0


def _enrich_item_details(data, session, item, user_id, target_id, pos_ticks):
    detail_res = {}
    if target_id and user_id:
        try:
            api = _media_api_provider()
            resp = api.get(f"/Users/{user_id}/Items/{target_id}", timeout=2)
            if resp.status_code == 200:
                detail_res = resp.json()

            if pos_ticks <= 0 and session.get("Id"):
                sess_res = api.get("/Sessions", timeout=2).json()
                for s in sess_res:
                    if s.get("Id") == session.get("Id"):
                        pos_ticks = int(s.get("PlayState", {}).get("PositionTicks") or 0)
                        break
        except Exception:
            pass

    run_ticks = item.get("RunTimeTicks") or session.get("NowPlayingItem", {}).get("RunTimeTicks") or data.get("RunTimeTicks") or 0
    run_ticks = _coerce_ticks(run_ticks)
    if run_ticks <= 0:
        run_ticks = int(detail_res.get("RunTimeTicks") or 0)

    return detail_res, pos_ticks, run_ticks


def _get_episode_series_fallback(user_id, series_id, overview_raw, rating_raw):
    try:
        series_res = _media_api_provider().get(f"/Users/{user_id}/Items/{series_id}", timeout=2).json()
        if not str(overview_raw).strip():
            overview_raw = series_res.get("Overview") or ""
        if not rating_raw:
            rating_raw = series_res.get("CommunityRating")
    except Exception:
        pass
    return overview_raw, rating_raw


def _format_overview(overview_raw):
    overview = _re_provider().sub(r"<[^>]+>", "", str(overview_raw)).strip()
    if not overview:
        overview = "暂无简介..."
    elif len(overview) > 150:
        overview = overview[:140] + "..."
    return overview


def _format_progress(bot, pos_ticks, run_ticks):
    if run_ticks <= 1:
        return "🟢 实时流/未知总时长"

    pct = int((pos_ticks / run_ticks) * 100)
    pct = min(max(pct, 0), 100)
    pos_str = bot._format_ticks(pos_ticks)
    run_str = bot._format_ticks(run_ticks)
    return f"{pos_str} / {run_str} ({pct}%)"


def _format_title_and_type(item, raw_type):
    title = item.get("Name") or "未知内容"
    ep_info = ""
    type_map = {"Episode": "剧集", "Movie": "电影", "Audio": "音乐", "MusicVideo": "MV", "LiveTvProgram": "直播", "TvChannel": "频道"}
    type_cn = type_map.get(raw_type, "媒体")

    if raw_type == "Episode" and item.get("SeriesName"):
        idx = item.get("IndexNumber", 0)
        parent_idx = item.get("ParentIndexNumber", 1)
        ep_info = f" S{str(parent_idx).zfill(2)}E{str(idx).zfill(2)} {title}"
        title = f"{item.get('SeriesName')}"
    elif raw_type == "Audio" and item.get("Artists"):
        artist_str = ", ".join(item.get("Artists"))
        title = f"{title} - {artist_str}"

    return title, ep_info, type_cn


def _render_message(action, tpl_vars, user_name, title, ep_info, type_cn, rating_str, progress_str, ip, loc, client, device, overview):
    template_key = "playback_start" if action == "start" else "playback_stop"
    try:
        tpl_plugin = _get_plugin_provider()("notify_template")
        if tpl_plugin and tpl_plugin.enabled:
            return tpl_plugin.render(template_key, tpl_vars)
        raise Exception("fallback")
    except Exception:
        emoji = "▶️" if action == "start" else "⏹️"
        act = "开始播放" if action == "start" else "停止播放"
        return (
            f"{emoji} <b>【{user_name}】{act} {type_cn} {title}</b>{ep_info}\n\n"
            f"⭐ <b>评分：</b>{rating_str} ｜ 📚 <b>类型：</b>{type_cn}\n"
            f"🔄 <b>进度：</b>{progress_str}\n"
            f"🌐 <b>IP地址：</b>{ip} {loc}\n"
            f"📱 <b>设备：</b>{client} {device}\n"
            f"🕒 <b>时间：</b>{_datetime_provider().datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"📝 <b>剧情：</b>{overview}"
        )


def _get_base_url():
    base_url = _media_server_main_public_or_host_provider()() or _media_server_host_provider()()
    if base_url and not base_url.startswith(("http://", "https://")):
        base_url = "https://" + base_url
    return base_url


def _get_target_jump_id(item, raw_type, target_id, series_id):
    target_jump_id = target_id
    if raw_type == "Episode" and series_id:
        target_jump_id = series_id
    elif raw_type == "Audio" and item.get("AlbumId"):
        target_jump_id = item.get("AlbumId")
    return target_jump_id


def _get_images(bot, item, target_jump_id):
    primary_io = bot._download_emby_image(target_jump_id, "Primary")
    backdrop_io = bot._download_emby_image(target_jump_id, "Backdrop")
    if not primary_io and not backdrop_io:
        primary_io = bot._download_emby_image(item.get("Id"), "Primary")
        backdrop_io = bot._download_emby_image(item.get("Id"), "Backdrop")

    tg_img = backdrop_io or primary_io or _report_cover_url_provider()
    wecom_img = backdrop_io or primary_io or _report_cover_url_provider()
    return tg_img, wecom_img


def handle_playback_event(bot, data, action):
    if not _enable_notify_provider()():
        _logger_provider().info("🔇 [播放通知] 开关未开启，跳过")
        return

    session = data.get("Session") or data
    item = data.get("Item") or session.get("NowPlayingItem") or {}
    user = data.get("User") or session
    user_name = user.get("Name") or user.get("UserName") or "未知用户"
    user_id = user.get("Id") or session.get("UserId")

    _logger_provider().info(f"🔔 [播放通知] 收到 {action} 事件，用户: {user_name} (ID: {user_id})")

    try:
        if bot._is_muted(user_id, "playback"):
            _logger_provider().info(f"🔇 [播放通知] 用户 {user_name} 被静音，跳过")
            return

        play_state = session.get("PlayState", {})
        playback_info = data.get("PlaybackInfo", {})
        pos_ticks = (
            data.get("PlaybackPositionTicks")
            or data.get("PositionTicks")
            or playback_info.get("PositionTicks")
            or play_state.get("PositionTicks")
            or 0
        )
        pos_ticks = _coerce_ticks(pos_ticks)

        target_id = item.get("Id")
        raw_type = item.get("Type", "")
        series_id = item.get("SeriesId") or session.get("NowPlayingItem", {}).get("SeriesId")

        detail_res, pos_ticks, run_ticks = _enrich_item_details(data, session, item, user_id, target_id, pos_ticks)

        overview_raw = detail_res.get("Overview") or item.get("Overview") or ""
        rating_raw = detail_res.get("CommunityRating") or item.get("CommunityRating")

        if not series_id:
            series_id = detail_res.get("SeriesId") or detail_res.get("ParentId")

        if raw_type == "Episode" and series_id:
            if not str(overview_raw).strip() or not rating_raw:
                overview_raw, rating_raw = _get_episode_series_fallback(user_id, series_id, overview_raw, rating_raw)

        overview = _format_overview(overview_raw)
        rating_str = f"{rating_raw}/10" if rating_raw else "无"
        title, ep_info, type_cn = _format_title_and_type(item, raw_type)

        ip = session.get("RemoteEndPoint") or data.get("RemoteEndPoint") or "127.0.0.1"
        loc = _location_provider()(ip)
        progress_str = _format_progress(bot, pos_ticks, run_ticks)
        client = session.get("Client") or data.get("Client") or "未知端"
        device = session.get("DeviceName") or data.get("DeviceName") or "未知设备"

        tpl_vars = {
            "username": user_name,
            "title": title,
            "ep_info": ep_info,
            "type_cn": type_cn,
            "rating": rating_str,
            "progress": progress_str,
            "ip": ip,
            "location": loc,
            "client": client,
            "device": device,
            "time": _datetime_provider().datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "overview": overview,
        }
        msg = _render_message(
            action,
            tpl_vars,
            user_name,
            title,
            ep_info,
            type_cn,
            rating_str,
            progress_str,
            ip,
            loc,
            client,
            device,
            overview,
        )

        target_jump_id = _get_target_jump_id(item, raw_type, target_id, series_id)
        base_url = _get_base_url()

        keyboard = None
        if base_url and base_url.startswith(("http://", "https://")):
            play_url = f"{base_url}/web/index.html#!/item?id={target_jump_id}&serverId={item.get('ServerId','')}"
            keyboard = {"inline_keyboard": [[{"text": "🔗 跳转详情", "url": play_url}]]}

        tg_img, wecom_img = _get_images(bot, item, target_jump_id)
        bot.send_photo("sys_notify", tg_img, msg, reply_markup=keyboard, platform="all", wecom_photo_io=wecom_img)
    except Exception as e:
        _logger_provider().error(f"[Bot] Playback event error: {e}")
