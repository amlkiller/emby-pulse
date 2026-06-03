import datetime
import logging
import time

from app.core.config import REPORT_COVER_URL
from app.infra.clients.tmdb_client import tmdb_client
from app.infra.config.notification_settings import get_notify_item_deleted
from app.utils.proxy_helper import get_safe_proxies


logger = logging.getLogger("uvicorn")

_notify_item_deleted_provider = lambda: get_notify_item_deleted
_time_provider = lambda: time
_datetime_provider = lambda: datetime
_tmdb_client_provider = lambda: tmdb_client
_safe_proxies_provider = lambda: get_safe_proxies
_report_cover_url_provider = lambda: REPORT_COVER_URL
_logger_provider = lambda: logger


def set_dependency_providers(
    *,
    notify_item_deleted_provider=None,
    time_provider=None,
    datetime_provider=None,
    tmdb_client_provider=None,
    safe_proxies_provider=None,
    report_cover_url_provider=None,
    logger_provider=None,
):
    global _notify_item_deleted_provider
    global _time_provider
    global _datetime_provider
    global _tmdb_client_provider
    global _safe_proxies_provider
    global _report_cover_url_provider
    global _logger_provider

    if notify_item_deleted_provider is not None:
        _notify_item_deleted_provider = notify_item_deleted_provider
    if time_provider is not None:
        _time_provider = time_provider
    if datetime_provider is not None:
        _datetime_provider = datetime_provider
    if tmdb_client_provider is not None:
        _tmdb_client_provider = tmdb_client_provider
    if safe_proxies_provider is not None:
        _safe_proxies_provider = safe_proxies_provider
    if report_cover_url_provider is not None:
        _report_cover_url_provider = report_cover_url_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


def _is_duplicate(bot, item_id, unique_name, now):
    if (item_id and item_id in bot.delete_cache and (now - bot.delete_cache[item_id] < 300)) or (
        unique_name and unique_name in bot.delete_cache and (now - bot.delete_cache[unique_name] < 300)
    ):
        return True

    if item_id:
        bot.delete_cache[item_id] = now
    if unique_name:
        bot.delete_cache[unique_name] = now
    bot.delete_cache = {key: value for key, value in bot.delete_cache.items() if now - value < 600}
    return False


def _format_deleted_item(item, raw_type, title, series_name, season_num, ep_num):
    del_type = "媒体"

    if raw_type == "Movie":
        del_type = "电影"
    elif raw_type == "Series":
        del_type = "整剧"
    elif raw_type == "Season":
        del_type = "整季"
        s_num = ep_num if ep_num is not None else season_num
        title = f"{series_name or title} - 第 {s_num} 季" if s_num else f"{series_name or title}"
    elif raw_type == "Episode" or (series_name and ep_num is not None):
        del_type = "单集"
        s_str = str(season_num).zfill(2) if season_num is not None else "01"
        e_str = str(ep_num).zfill(2) if ep_num is not None else "XX"
        title = f"{series_name or '未知剧集'} S{s_str}E{e_str} {title}"

    return del_type, title


def _get_tmdb_poster_url(item, raw_type):
    tmdb_id = item.get("ProviderIds", {}).get("Tmdb")
    if not tmdb_id and item.get("SeriesProviderIds"):
        tmdb_id = item.get("SeriesProviderIds", {}).get("Tmdb")

    tmdb = _tmdb_client_provider()
    if not tmdb_id or not tmdb.api_key:
        return None

    try:
        proxies = _safe_proxies_provider()()
        if raw_type == "Movie":
            tmdb_res = tmdb.get_movie_details(tmdb_id, proxies=proxies, timeout=5)
        else:
            tmdb_res = tmdb.get_tv_details(tmdb_id, proxies=proxies, timeout=5)
        if tmdb_res.status_code == 200:
            poster_path = tmdb_res.json().get("poster_path")
            if poster_path:
                return f"https://image.tmdb.org/t/p/w500{poster_path}"
    except Exception:
        pass
    return None


def _get_notification_image(bot, item, raw_type):
    primary_io = bot._download_emby_image(item.get("Id"), "Primary") if item.get("Id") else None
    backdrop_io = bot._download_emby_image(item.get("Id"), "Backdrop") if item.get("Id") else None
    if not primary_io and not backdrop_io and item.get("SeriesId"):
        primary_io = bot._download_emby_image(item.get("SeriesId"), "Primary")

    tmdb_img_url = None
    if not primary_io and not backdrop_io:
        tmdb_img_url = _get_tmdb_poster_url(item, raw_type)

    return primary_io or backdrop_io or tmdb_img_url or _report_cover_url_provider()


def handle_item_deleted(bot, data):
    if not _notify_item_deleted_provider()():
        return
    try:
        item = data.get("Item") or data
        raw_type = item.get("Type", "")
        title = item.get("Name") or item.get("Title") or "未知资源"

        if raw_type == "User" or "删除了用户" in title:
            return

        series_name = item.get("SeriesName")
        season_num = item.get("ParentIndexNumber")
        ep_num = item.get("IndexNumber")
        year = item.get("ProductionYear", "")
        item_id = str(item.get("Id", ""))
        unique_name = f"{series_name}_{season_num}_{ep_num}_{title}" if series_name else title

        if _is_duplicate(bot, item_id, unique_name, _time_provider().time()):
            return

        year_str = f" ({year})" if year else ""
        del_type, title = _format_deleted_item(item, raw_type, title, series_name, season_num, ep_num)

        msg = (
            f"🗑️ <b>系统告警：{del_type}被删除</b>\n\n"
            f"🎬 <b>内容：</b>{title}{year_str}\n"
            f"🕒 <b>时间：</b>{_datetime_provider().datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            f"<i>* 该项目已从媒体库物理存储中被永久移除。</i>"
        )

        tg_img = _get_notification_image(bot, item, raw_type)
        bot.send_photo("sys_notify", tg_img, msg, platform="all", wecom_photo_io=tg_img)
    except Exception as e:
        _logger_provider().error(f"删除通知组装异常: {e}")
