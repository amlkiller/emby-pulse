import re

from app.infra.clients.media_server_client import media_api


_media_api_provider = lambda: media_api
_admin_id_provider = lambda: _default_get_admin_id
_media_server_main_public_or_host_provider = lambda: _default_media_server_url
_media_server_host_provider = lambda: _default_media_server_url
_report_cover_url_provider = lambda: ""


def _default_get_admin_id():
    return None


def _default_media_server_url():
    return ""


def set_dependency_providers(
    *,
    media_api_provider=None,
    admin_id_provider=None,
    media_server_main_public_or_host_provider=None,
    media_server_host_provider=None,
    report_cover_url_provider=None,
):
    global _media_api_provider
    global _admin_id_provider
    global _media_server_main_public_or_host_provider
    global _media_server_host_provider
    global _report_cover_url_provider

    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if admin_id_provider is not None:
        _admin_id_provider = admin_id_provider
    if media_server_main_public_or_host_provider is not None:
        _media_server_main_public_or_host_provider = media_server_main_public_or_host_provider
    if media_server_host_provider is not None:
        _media_server_host_provider = media_server_host_provider
    if report_cover_url_provider is not None:
        _report_cover_url_provider = report_cover_url_provider


def extract_tech_info(item):
    sources = item.get("MediaSources", [])
    if not sources:
        return "📼 未知"
    info_parts = []
    video = next((s for s in sources[0].get("MediaStreams", []) if s.get("Type") == "Video"), None)
    if video:
        w = video.get("Width", 0)
        if w >= 3800:
            res = "4K"
        elif w >= 1900:
            res = "1080P"
        elif w >= 1200:
            res = "720P"
        else:
            res = "SD"
        extra = []
        v_range = video.get("VideoRange", "")
        title = video.get("DisplayTitle", "").upper()
        if "HDR" in v_range or "HDR" in title:
            extra.append("HDR")
        if "DOVI" in title or "DOLBY VISION" in title:
            extra.append("DoVi")
        res_str = f"{res} {' '.join(extra)}"
        info_parts.append(res_str.strip())
        bitrate = sources[0].get("Bitrate", 0)
        if bitrate > 0:
            info_parts.append(f"{round(bitrate / 1000000, 1)}Mbps")
    return " | ".join(info_parts) if info_parts else "📼 未知"


def cmd_search(bot, chat_id, text, platform):
    parts = text.split(' ', 1)
    if len(parts) < 2:
        return bot.send_message(chat_id, "🔍 请使用: /search 关键词", platform=platform)
    keyword = parts[1].strip()
    try:
        user_id = _admin_id_provider()()
        if not user_id:
            return bot.send_message(chat_id, "❌ 错误: 无法获取 Emby 用户身份", platform=platform)

        fields = "ProductionYear,Type,Id"
        params = {"SearchTerm": keyword, "IncludeItemTypes": "Movie,Series", "Recursive": "true", "Fields": fields, "Limit": 5}
        media_api_obj = _media_api_provider()
        res = media_api_obj.get(f"/Users/{user_id}/Items", params=params, timeout=10)
        if res.status_code != 200:
            return bot.send_message(chat_id, f"❌ 搜索失败", platform=platform)
        items = res.json().get("Items", [])
        if not items:
            return bot.send_message(chat_id, f"📭 未找到与 <b>{keyword}</b> 相关的资源", platform=platform)

        top = items[0]
        type_raw = top.get("Type")
        tech_info_str = "查询中..."
        ep_count_str = ""
        details = {}

        try:
            if type_raw == "Series":
                details = media_api_obj.get(
                    f"/Users/{user_id}/Items/{top['Id']}",
                    params={"Fields": "Overview,CommunityRating,Genres,RecursiveItemCount"},
                    timeout=5,
                ).json()
                ep_count = details.get("RecursiveItemCount", 0)
                ep_count_str = f"📊 共 {ep_count} 集"
                sample_res = media_api_obj.get(
                    f"/Users/{user_id}/Items",
                    params={"ParentId": top['Id'], "Recursive": "true", "IncludeItemTypes": "Episode", "Limit": 1, "Fields": "MediaSources"},
                    timeout=5,
                )
                if sample_res.status_code == 200 and sample_res.json().get("Items"):
                    tech_info_str = bot._extract_tech_info(sample_res.json().get("Items")[0])
            else:
                details = media_api_obj.get(
                    f"/Users/{user_id}/Items/{top['Id']}",
                    params={"Fields": "Overview,CommunityRating,Genres,MediaSources"},
                    timeout=8,
                ).json()
                tech_info_str = bot._extract_tech_info(details)
        except Exception:
            tech_info_str = "暂无技术信息"

        name = details.get("Name", top.get("Name"))
        year = details.get("ProductionYear", top.get("ProductionYear"))
        year_str = f"({year})" if year else ""
        rating = details.get("CommunityRating", "N/A")
        genres = " / ".join(details.get("Genres", [])[:3]) or "未分类"

        overview = str(details.get("Overview") or "")
        overview = re.sub(r'<[^>]+>', '', overview).strip()
        if not overview:
            overview = "暂无简介"
        if len(overview) > 120:
            overview = overview[:120] + "..."

        type_icon = "🎬" if type_raw == "Movie" else "📺"
        info_line = f"{ep_count_str} | {tech_info_str}" if type_raw == "Series" else tech_info_str

        base_url = _media_server_main_public_or_host_provider()() or _media_server_host_provider()()
        if base_url and not base_url.startswith(('http://', 'https://')):
            base_url = 'https://' + base_url
        play_url = f"{base_url}/web/index.html#!/item?id={top.get('Id')}&serverId={top.get('ServerId')}"

        caption = (f"{type_icon} <b>{name}</b> {year_str}\n"
                   f"⭐️ {rating}  |  🎭 {genres}\n"
                   f"💿 {info_line}\n\n"
                   f"📝 <b>剧情简介：</b>\n{overview}\n")

        if len(items) > 1:
            caption += "\n🔎 <b>其他结果：</b>\n"
            for i, sub in enumerate(items[1:]):
                sub_year = f"({sub.get('ProductionYear')})" if sub.get('ProductionYear') else ""
                sub_type = "📺" if sub.get("Type") == "Series" else "🎬"
                caption += f"{sub_type} {sub.get('Name')} {sub_year}\n"

        keyboard = None
        if base_url and base_url.startswith(('http://', 'https://')):
            keyboard = {"inline_keyboard": [[{"text": "▶️ 立即播放", "url": play_url}]]}
        primary_io = bot._download_emby_image(top.get("Id"), 'Primary')
        backdrop_io = bot._download_emby_image(top.get("Id"), 'Backdrop')

        report_cover_url = _report_cover_url_provider()
        tg_img = primary_io or backdrop_io or report_cover_url
        wecom_img = backdrop_io or primary_io or report_cover_url
        bot.send_photo(chat_id, tg_img, caption.strip(), reply_markup=keyboard, platform=platform, wecom_photo_io=wecom_img)
    except Exception:
        bot.send_message(chat_id, "❌ 搜索时发生错误", platform=platform)
