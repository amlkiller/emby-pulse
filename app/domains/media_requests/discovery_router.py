import logging
import random
from datetime import date

from fastapi import APIRouter, Request

from app.core.security_utils import safe_error_message
from app.domains.media_requests import community_cache_service
from app.domains.users import public_service as user_service
from app.infra.clients.media_server_client import media_api
from app.infra.clients.tmdb_client import tmdb_client
from app.infra.config.media_server_settings import get_media_server_main_public_or_host
from app.utils.proxy_helper import get_safe_proxies


router = APIRouter()

_user_service_provider = lambda: user_service
_media_api_provider = lambda: media_api
_tmdb_client_provider = lambda: tmdb_client
_get_cache_provider = lambda: community_cache_service._get_cache
_set_cache_provider = lambda: community_cache_service._set_cache
_cache_ttl_hub_provider = lambda: community_cache_service.COMMUNITY_CACHE_TTL_HUB
_main_server_url_provider = lambda: get_media_server_main_public_or_host
_safe_proxies_provider = lambda: get_safe_proxies
_safe_error_message_provider = lambda: safe_error_message
_logger_provider = lambda: logging.getLogger("uvicorn")


def _check_user_exists(user_id: str) -> bool:
    """检查 Emby 用户是否仍然存在"""
    if not user_id:
        return False
    try:
        media = _media_api_provider()
        if media and media.host and media.api_key:
            res = media.get(f"/Users/{user_id}", timeout=5)
            return res.status_code == 200
    except:
        pass
    return True  # 网络异常时不误判，允许继续操作


_check_user_exists_provider = lambda: _check_user_exists


def get_tmdb_season_info(tmdb_id: int, season: int) -> tuple:
    """获取 TMDB 季信息（总集数、未播出集数）

    Returns:
        (total_episodes, unaired_episodes)
    """
    tmdb = _tmdb_client_provider()
    get_proxies = _safe_proxies_provider()

    if not tmdb_id or not season:
        return 0, []
    try:
        if not tmdb.api_key:
            return 0, []
        proxies = get_proxies()
        season_data = tmdb.get_tv_season(tmdb_id, season, proxies=proxies, timeout=8).json()
        episodes = season_data.get("episodes", [])
        total = len(episodes)

        # 计算未播出的集数
        today = date.today().strftime("%Y-%m-%d")
        unaired_eps = []
        for ep in episodes:
            ep_num = ep.get("episode_number", 0)
            air_date = ep.get("air_date", "")
            if air_date and air_date > today:
                unaired_eps.append(ep_num)

        return total, unaired_eps
    except:
        return 0, []


def get_emby_admin():
    media = _media_api_provider()
    try:
        users = media.get("/Users", timeout=5).json()
        for u in users:
            if u.get("Policy", {}).get("IsAdministrator"):
                return u["Id"]
        return users[0]["Id"] if users else None
    except:
        return None


_get_emby_admin_provider = lambda: get_emby_admin


def check_emby_exists(tmdb_id, media_type, season=0):
    media = _media_api_provider()
    get_admin = _get_emby_admin_provider()

    if not media.host or not media.api_key:
        return False
    try:
        admin_id = get_admin()
        if not admin_id:
            return False
        type_filter = "Movie" if media_type == "movie" else "Series"
        res = media.get(f"/Users/{admin_id}/Items", params={
            "AnyProviderIdEquals": f"tmdb.{tmdb_id}",
            "IncludeItemTypes": type_filter,
            "Recursive": "true",
        }, timeout=5).json()
        if not res.get("Items"):
            return False
        if media_type == "movie":
            return True
        sid = res["Items"][0]["Id"]
        s_res = media.get(f"/Shows/{sid}/Seasons", params={"UserId": admin_id}, timeout=5).json()
        local_seasons = [s.get("IndexNumber") for s in s_res.get("Items", [])]
        return season in local_seasons
    except:
        return False


_check_emby_exists_provider = lambda: check_emby_exists


def set_dependency_providers(
    *,
    user_service_provider=None,
    media_api_provider=None,
    tmdb_client_provider=None,
    check_user_exists_provider=None,
    get_emby_admin_provider=None,
    check_emby_exists_provider=None,
    get_cache_provider=None,
    set_cache_provider=None,
    cache_ttl_hub_provider=None,
    main_server_url_provider=None,
    safe_proxies_provider=None,
    safe_error_message_provider=None,
    logger_provider=None,
):
    global _user_service_provider
    global _media_api_provider
    global _tmdb_client_provider
    global _check_user_exists_provider
    global _get_emby_admin_provider
    global _check_emby_exists_provider
    global _get_cache_provider
    global _set_cache_provider
    global _cache_ttl_hub_provider
    global _main_server_url_provider
    global _safe_proxies_provider
    global _safe_error_message_provider
    global _logger_provider

    if user_service_provider is not None:
        _user_service_provider = user_service_provider
    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if tmdb_client_provider is not None:
        _tmdb_client_provider = tmdb_client_provider
    if check_user_exists_provider is not None:
        _check_user_exists_provider = check_user_exists_provider
    if get_emby_admin_provider is not None:
        _get_emby_admin_provider = get_emby_admin_provider
    if check_emby_exists_provider is not None:
        _check_emby_exists_provider = check_emby_exists_provider
    if get_cache_provider is not None:
        _get_cache_provider = get_cache_provider
    if set_cache_provider is not None:
        _set_cache_provider = set_cache_provider
    if cache_ttl_hub_provider is not None:
        _cache_ttl_hub_provider = cache_ttl_hub_provider
    if main_server_url_provider is not None:
        _main_server_url_provider = main_server_url_provider
    if safe_proxies_provider is not None:
        _safe_proxies_provider = safe_proxies_provider
    if safe_error_message_provider is not None:
        _safe_error_message_provider = safe_error_message_provider
    if logger_provider is not None:
        _logger_provider = logger_provider


@router.get("/api/requests/item_info")
def get_item_info(item_id: str, request: Request):
    users = _user_service_provider()
    media = _media_api_provider()
    get_admin = _get_emby_admin_provider()

    # 🔒 安全检查：管理员或已绑定 Emby 的报片用户
    if not (users.is_admin_user(request) or request.session.get("req_user")):
        return {"status": "error", "message": "请先登录"}
    try:
        admin_id = get_admin()
        if not admin_id:
            return {"status": "error"}

        res = media.get(f"/Users/{admin_id}/Items/{item_id}", timeout=5)
        if res.status_code == 200:
            d = res.json()
            return {"status": "success", "data": {
                "Id": d.get("Id"),
                "Name": d.get("Name", "未知"),
                "Type": d.get("Type", ""),
                "ProductionYear": d.get("ProductionYear", ""),
                "CommunityRating": d.get("CommunityRating", "N/A"),
                "Overview": d.get("Overview", ""),
                "Genres": d.get("Genres", []),
            }}
        return {"status": "error"}
    except Exception as e:
        return {"status": "error"}


@router.get("/api/requests/hub_data")
def get_hub_data(request: Request):
    media = _media_api_provider()
    get_cache = _get_cache_provider()
    set_cache = _set_cache_provider()
    cache_ttl_hub = _cache_ttl_hub_provider()
    get_main_server_url = _main_server_url_provider()
    logger = _logger_provider()

    user = request.session.get("req_user")
    if not user:
        return {"status": "error"}

    # 🔥 尝试从缓存获取（hub_data 是全局数据，不依赖用户）
    cache_key = "hub_data"
    cached = get_cache(cache_key)
    if cached:
        return {"status": "success", "data": cached, "from_cache": True}

    host = get_main_server_url()
    uid = user["Id"]

    top_rated = []
    genres_data = []
    try:
        # 🔥 使用 /Items API 而不是 /Users/{uid}/Items
        tr_res = media.get("/Items", params={
            "IncludeItemTypes": "Movie,Series",
            "Recursive": "true",
            "SortBy": "CommunityRating",
            "SortOrder": "Descending",
            "Limit": 100,
            "Fields": "CommunityRating",
        }, timeout=5).json()
        logger.debug(f"[hub_data] 镇站之宝返回: {len(tr_res.get('Items', []))} 条")

        valid_items = []
        for i in tr_res.get("Items", []):
            rating = i.get("CommunityRating", 0)
            if 8.0 <= rating <= 9.8:
                valid_items.append({
                    "Id": i.get("Id"), "Name": i.get("Name"), "Type": i.get("Type"),
                    "CommunityRating": rating,
                })

        random.shuffle(valid_items)
        top_rated = valid_items[:10]
        logger.debug(f"[hub_data] 镇站之宝筛选后: {len(top_rated)} 条")

        # 🔥 使用 /Items API
        g_res = media.get("/Items", params={
            "IncludeItemTypes": "Movie,Series",
            "Recursive": "true",
            "SortBy": "DateCreated",
            "SortOrder": "Descending",
            "Limit": 200,
            "Fields": "Genres",
        }, timeout=5).json()
        logger.debug(f"[hub_data] 流派分析返回: {len(g_res.get('Items', []))} 条")
        genre_counts = {}
        total_items = 0
        for i in g_res.get("Items", []):
            gs = i.get("Genres", [])
            if gs:
                total_items += 1
                for g in gs:
                    genre_counts[g] = genre_counts.get(g, 0) + 1

        if total_items > 0:
            sorted_genres = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)[:6]
            for k, v in sorted_genres:
                genres_data.append({"name": k, "count": v, "pct": round(v / total_items * 100)})
        logger.debug(f"[hub_data] 流派分析结果: {len(genres_data)} 种")
    except Exception as e:
        logger.error(f"[hub_data] 获取失败: {e}")

    # 🔥 存入缓存
    result_data = {"top_rated": top_rated, "genres": genres_data}
    set_cache(cache_key, result_data, cache_ttl_hub)

    return {"status": "success", "data": result_data}


@router.get("/api/requests/search")
def search_tmdb(query: str, request: Request):
    check_user_exists = _check_user_exists_provider()
    tmdb = _tmdb_client_provider()
    get_proxies = _safe_proxies_provider()
    safe_error = _safe_error_message_provider()

    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}

    # 检查 Emby 账号是否仍然存在
    if not check_user_exists(user.get("Id")):
        request.session.pop("req_user", None)
        return {"status": "error", "message": "账号已被删除", "account_deleted": True}

    proxies = get_proxies()
    try:
        res = tmdb.search_multi(query, proxies=proxies, timeout=10).json()
        results = []
        for i in res.get("results", []):
            if i.get("media_type") in ["movie", "tv"]:
                results.append({"tmdb_id": i["id"], "media_type": i["media_type"], "title": i.get("title") or i.get("name"), "year": (i.get("release_date") or i.get("first_air_date") or "")[:4], "poster_path": f"https://image.tmdb.org/t/p/w500{i['poster_path']}" if i.get("poster_path") else "", "overview": i.get("overview", ""), "vote_average": round(i.get("vote_average", 0), 1), "local_status": -1})
        return {"status": "success", "data": results}
    except Exception as e:
        return {"status": "error", "message": safe_error(e)}


@router.get("/api/requests/trending")
def get_tmdb_trending(request: Request):
    check_user_exists = _check_user_exists_provider()
    tmdb = _tmdb_client_provider()
    get_proxies = _safe_proxies_provider()
    safe_error = _safe_error_message_provider()

    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}

    # 检查 Emby 账号是否仍然存在
    if not check_user_exists(user.get("Id")):
        request.session.pop("req_user", None)
        return {"status": "error", "message": "账号已被删除", "account_deleted": True}

    proxies = get_proxies()
    try:
        results = []
        for page in [1, 2]:
            res = tmdb.get_trending(media_type="all", time_window="week", page=page, proxies=proxies, timeout=10).json()
            for i in res.get("results", []):
                if i.get("media_type") in ["movie", "tv"] and i.get("poster_path"):
                    results.append({
                        "tmdb_id": i["id"],
                        "media_type": i["media_type"],
                        "title": i.get("title") or i.get("name"),
                        "year": (i.get("release_date") or i.get("first_air_date") or "")[:4],
                        "poster_path": f"https://image.tmdb.org/t/p/w500{i['poster_path']}",
                        "overview": i.get("overview", ""),
                        "vote_average": round(i.get("vote_average", 0), 1),
                        "local_status": -1,
                    })
        return {"status": "success", "data": results}
    except Exception as e:
        return {"status": "error", "message": safe_error(e)}


@router.get("/api/requests/tv/{tmdb_id}")
def get_tv_details(tmdb_id: int, request: Request):
    users = _user_service_provider()
    media = _media_api_provider()
    tmdb = _tmdb_client_provider()
    get_admin = _get_emby_admin_provider()
    get_proxies = _safe_proxies_provider()
    safe_error = _safe_error_message_provider()

    # 🔒 安全检查：管理员或已绑定 Emby 的报片用户
    if not (users.is_admin_user(request) or request.session.get("req_user")):
        return {"status": "error", "message": "请先登录"}
    proxies = get_proxies()
    try:
        local_seasons_map = {}

        admin_id = get_admin()
        if admin_id:
            s_res = media.get(f"/Users/{admin_id}/Items", params={
                "AnyProviderIdEquals": f"tmdb.{tmdb_id}",
                "IncludeItemTypes": "Series",
                "Recursive": "true",
            }, timeout=5).json()
            if s_res.get("Items"):
                sid = s_res["Items"][0]["Id"]
                ep_res = media.get(f"/Users/{admin_id}/Items", params={
                    "ParentId": sid,
                    "IncludeItemTypes": "Episode",
                    "Recursive": "true",
                    "Fields": "ParentIndexNumber",
                }, timeout=5).json()
                for ep in ep_res.get("Items", []):
                    sn = ep.get("ParentIndexNumber")
                    if sn is not None:
                        local_seasons_map[sn] = local_seasons_map.get(sn, 0) + 1

        tmdb_res = tmdb.get_tv_details(tmdb_id, proxies=proxies, timeout=10).json()
        seasons = []
        for s in tmdb_res.get("seasons", []):
            if s["season_number"] > 0:
                sn = s["season_number"]
                seasons.append({
                    "season_number": sn,
                    "name": s["name"],
                    "episode_count": s["episode_count"],
                    "exists_locally": sn in local_seasons_map,
                    "local_ep_count": local_seasons_map.get(sn, 0),
                })
        return {"status": "success", "seasons": seasons}
    except Exception as e:
        return {"status": "error", "message": safe_error(e)}


@router.get("/api/requests/check/{media_type}/{tmdb_id}")
def check_local_status(media_type: str, tmdb_id: int, request: Request):
    users = _user_service_provider()
    check_exists = _check_emby_exists_provider()

    # 🔒 安全检查：管理员或已绑定 Emby 的报片用户
    if not (users.is_admin_user(request) or request.session.get("req_user")):
        return {"status": "error", "message": "请先登录"}
    exists = check_exists(tmdb_id, media_type)
    return {"status": "success", "exists": exists}
