import json
import logging
import time

from app.infra.clients.media_server_client import media_api
from app.infra.clients.network_client import network_client
from app.infra.config.media_server_settings import get_media_server_public_url


logger = logging.getLogger("uvicorn")

_media_api_provider = lambda: media_api
_network_client_provider = lambda: network_client
_media_server_public_url_provider = lambda: get_media_server_public_url
_logger_provider = lambda: logger
_time_provider = lambda: time


def set_dependency_providers(
    *,
    media_api_provider=None,
    network_client_provider=None,
    media_server_public_url_provider=None,
    logger_provider=None,
    time_provider=None,
):
    global _media_api_provider
    global _network_client_provider
    global _media_server_public_url_provider
    global _logger_provider
    global _time_provider

    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if network_client_provider is not None:
        _network_client_provider = network_client_provider
    if media_server_public_url_provider is not None:
        _media_server_public_url_provider = media_server_public_url_provider
    if logger_provider is not None:
        _logger_provider = logger_provider
    if time_provider is not None:
        _time_provider = time_provider


def _append_public_route_latency(msg):
    try:
        raw_url_str = _media_server_public_url_provider()()
        routes = []
        try:
            parsed = json.loads(raw_url_str)
            if isinstance(parsed, list):
                routes = parsed
        except Exception:
            if raw_url_str:
                routes = [{"name": "默认主线路", "url": raw_url_str}]

        if routes:
            msg += "\n\n🌐 <b>公网节点延迟测速</b>\n"
            for r in routes:
                r_name = r.get("name", "未命名线路")
                r_url = r.get("url", "").rstrip("/")
                if r_url:
                    try:
                        r_start = _time_provider().time()
                        _network_client_provider().get(f"{r_url}/web/favicon.ico", timeout=3)
                        r_delay = int((_time_provider().time() - r_start) * 1000)
                        icon = "🟢" if r_delay < 100 else ("🟡" if r_delay < 300 else "🔴")
                        msg += f"{icon} {r_name}: {r_delay}ms\n"
                    except Exception:
                        msg += f"🔴 {r_name}: 超时/离线\n"
    except Exception as e:
        _logger_provider().error(f"Route ping error in bot check: {e}")
    return msg


def cmd_check(bot, cid, platform):
    start = _time_provider().time()
    try:
        res = _media_api_provider().get("/System/Info", timeout=5)
        if res.status_code == 200:
            info = res.json()
            delay = int((_time_provider().time() - start) * 1000)
            version = info.get("Version", "未知")
            os_name = info.get("OperatingSystem", "未知")

            movie_count = series_count = ep_count = 0
            try:
                c_res = _media_api_provider().get("/Items/Counts", timeout=3).json()
                movie_count = c_res.get("MovieCount", 0)
                series_count = c_res.get("SeriesCount", 0)
                ep_count = c_res.get("EpisodeCount", 0)
            except Exception:
                pass

            active_users = 0
            try:
                s_res = _media_api_provider().get("/Sessions", timeout=3).json()
                active_users = len([s for s in s_res if s.get("NowPlayingItem")])
            except Exception:
                pass

            msg = (f"📡 <b>Emby 服务器状态探针</b>\n\n"
                   f"🟢 <b>运行状态</b>：在线 (响应延迟: {delay}ms)\n"
                   f"🏷️ <b>系统版本</b>：Emby Server {version}\n"
                   f"💻 <b>宿主环境</b>：{os_name}\n\n"
                   f"📊 <b>媒体库容量</b>\n"
                   f"🎬 电影：{movie_count} 部\n"
                   f"📺 剧集：{series_count} 部 (共 {ep_count} 集)\n\n"
                   f"👥 <b>当前活跃</b>：{active_users} 人正在观看")

            msg = _append_public_route_latency(msg)
            bot.send_message(cid, msg.strip(), platform=platform)
    except Exception:
        bot.send_message(cid, "❌ 离线或无法连接到服务器", platform=platform)
