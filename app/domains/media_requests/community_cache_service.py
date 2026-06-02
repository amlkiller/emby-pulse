import logging
import random
import threading
import time

from app.domains.playback import stats as playback_stats
from app.infra.clients.media_server_client import media_api

logger = logging.getLogger("uvicorn")

# 缓存结构: {key: {"data": ..., "expires_at": timestamp}}
_community_cache = {}
_community_cache_lock = threading.Lock()
_COMMUNITY_CACHE_MAX_SIZE = 64
_community_refresh_lock = threading.Lock()
_community_refresh_started = False
_community_refresh_start_lock = threading.Lock()
_community_refresh_stop_event = threading.Event()
_community_refresh_thread = None

# 缓存 TTL 配置（秒）
COMMUNITY_CACHE_TTL = 300
COMMUNITY_CACHE_TTL_HUB = 600
COMMUNITY_CACHE_TTL_TOP = 300
COMMUNITY_CACHE_TTL_LATEST = 180


def _get_cache(key: str):
    """获取缓存数据，过期或空数据返回 None"""
    with _community_cache_lock:
        entry = _community_cache.get(key)
        if entry and entry["expires_at"] > time.time():
            data = entry["data"]
            if data:
                return data
    return None


def _set_cache(key: str, data, ttl: int = COMMUNITY_CACHE_TTL):
    """设置缓存"""
    with _community_cache_lock:
        now = time.time()
        expired_keys = [k for k, v in _community_cache.items() if v.get("expires_at", 0) <= now]
        for k in expired_keys:
            _community_cache.pop(k, None)
        if len(_community_cache) >= _COMMUNITY_CACHE_MAX_SIZE and key not in _community_cache:
            oldest_key = min(_community_cache, key=lambda k: _community_cache[k].get("expires_at", 0))
            _community_cache.pop(oldest_key, None)
        _community_cache[key] = {
            "data": data,
            "expires_at": now + ttl,
        }


def _invalidate_cache(key: str = None):
    """清除缓存（可选指定 key，不指定则清除全部）"""
    with _community_cache_lock:
        if key:
            _community_cache.pop(key, None)
        else:
            _community_cache.clear()


def _get_emby_admin():
    try:
        users = media_api.get("/Users", timeout=5).json()
        for u in users:
            if u.get("Policy", {}).get("IsAdministrator"):
                return u["Id"]
        return users[0]["Id"] if users else None
    except Exception:
        return None


def _refresh_community_cache(admin_resolver=None):
    """后台刷新用户社区首页缓存（由定时任务调用）"""
    if not _community_refresh_lock.acquire(blocking=False):
        logger.info("用户社区缓存正在刷新，跳过本次请求")
        return
    try:
        admin_resolver = admin_resolver or _get_emby_admin
        admin_id = admin_resolver()
        if not admin_id:
            logger.warning("缓存刷新失败: 无法获取 admin 用户")
            return

        try:
            tr_res = media_api.get("/Items", params={
                "IncludeItemTypes": "Movie,Series",
                "Recursive": "true",
                "SortBy": "CommunityRating",
                "SortOrder": "Descending",
                "Limit": 100,
                "Fields": "CommunityRating",
            }, timeout=10).json()
            items = tr_res.get("Items", [])
            logger.debug(f"[后台刷新] 镇站之宝返回: {len(items)} 条")

            for idx, item in enumerate(items[:3]):
                logger.debug(
                    f"[后台刷新] 镇站之宝第{idx+1}条: "
                    f"Name={item.get('Name')}, CommunityRating={item.get('CommunityRating')}, Type={item.get('Type')}"
                )

            valid_items = []
            for i in items:
                rating = i.get("CommunityRating", 0) or 0
                if 8.0 <= rating <= 9.8:
                    valid_items.append({
                        "Id": i.get("Id"),
                        "Name": i.get("Name"),
                        "Type": i.get("Type"),
                        "CommunityRating": rating,
                    })
            random.shuffle(valid_items)
            top_rated = valid_items[:10]
            logger.debug(f"[后台刷新] 镇站之宝筛选后: {len(top_rated)} 条")

            g_res = media_api.get("/Items", params={
                "IncludeItemTypes": "Movie,Series",
                "Recursive": "true",
                "SortBy": "DateCreated",
                "SortOrder": "Descending",
                "Limit": 200,
                "Fields": "Genres",
            }, timeout=10).json()
            g_items = g_res.get("Items", [])
            logger.debug(f"[后台刷新] 流派分析返回: {len(g_items)} 条")

            for idx, item in enumerate(g_items[:3]):
                logger.debug(f"[后台刷新] 流派第{idx+1}条: Name={item.get('Name')}, Genres={item.get('Genres')}")

            genre_counts = {}
            total_items = 0
            for i in g_items:
                gs = i.get("Genres", [])
                if gs:
                    total_items += 1
                    for g in gs:
                        genre_counts[g] = genre_counts.get(g, 0) + 1

            genres_data = []
            if total_items > 0:
                sorted_genres = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)[:6]
                for k, v in sorted_genres:
                    genres_data.append({"name": k, "count": v, "pct": round(v / total_items * 100)})
            logger.debug(f"[后台刷新] 流派分析结果: {len(genres_data)} 种")

            _set_cache("hub_data", {"top_rated": top_rated, "genres": genres_data}, COMMUNITY_CACHE_TTL_HUB)
            logger.info("hub_data 缓存已刷新")
        except Exception as e:
            logger.error(f"hub_data 缓存刷新失败: {e}")

        try:
            global_res = playback_stats.api_latest_media(limit=40)
            global_items = global_res.get("data", [])
            if global_items:
                _set_cache("safe_latest", global_items, COMMUNITY_CACHE_TTL_LATEST)
                logger.info("safe_latest 缓存已刷新")
        except Exception as e:
            logger.error(f"safe_latest 缓存刷新失败: {e}")

        try:
            for category in ["Movie", "Episode"]:
                global_res = playback_stats.api_top_movies(user_id="all", category=category, sort_by="count")
                global_items = global_res.get("data", [])
                if global_items:
                    _set_cache(f"safe_top_{category}", global_items[:50], COMMUNITY_CACHE_TTL_TOP)
                    logger.info(f"safe_top_{category} 缓存已刷新")
        except Exception as e:
            logger.error(f"safe_top 缓存刷新失败: {e}")

    except Exception as e:
        logger.error(f"用户社区缓存刷新失败: {e}")
    finally:
        try:
            _community_refresh_lock.release()
        except RuntimeError:
            pass


def start_community_cache_refresh_loop(refresh_func=None) -> None:
    global _community_refresh_started, _community_refresh_thread
    refresh_func = refresh_func or _refresh_community_cache
    with _community_refresh_start_lock:
        if _community_refresh_started:
            return
        _community_refresh_started = True
        _community_refresh_stop_event.clear()

    def _refresh_loop():
        if _community_refresh_stop_event.wait(15):
            return
        refresh_func()
        while not _community_refresh_stop_event.wait(300):
            refresh_func()

    _community_refresh_thread = threading.Thread(target=_refresh_loop, daemon=True, name="community-cache-refresh")
    _community_refresh_thread.start()


def stop_community_cache_refresh_loop() -> None:
    global _community_refresh_started, _community_refresh_thread
    with _community_refresh_start_lock:
        if not _community_refresh_started:
            return
        _community_refresh_stop_event.set()
        thread = _community_refresh_thread
        _community_refresh_started = False
        _community_refresh_thread = None
    if thread and thread.is_alive():
        thread.join(timeout=1)
