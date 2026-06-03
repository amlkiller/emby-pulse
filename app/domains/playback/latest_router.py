from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import APIRouter, Request

from app.domains.playback.stats_helpers import check_login, get_admin_user_id
from app.infra.clients.media_server_client import media_api
from app.infra.clients.tmdb_client import tmdb_client
from app.utils.proxy_helper import get_safe_proxies


router = APIRouter()

_check_login_provider = lambda: check_login
_get_admin_user_id_provider = lambda: get_admin_user_id
_media_api_provider = lambda: media_api
_tmdb_client_provider = lambda: tmdb_client
_get_safe_proxies_provider = lambda: get_safe_proxies


def set_dependency_providers(
    *,
    check_login_provider=None,
    get_admin_user_id_provider=None,
    media_api_provider=None,
    tmdb_client_provider=None,
    get_safe_proxies_provider=None,
):
    global _check_login_provider
    global _get_admin_user_id_provider
    global _media_api_provider
    global _tmdb_client_provider
    global _get_safe_proxies_provider

    if check_login_provider is not None:
        _check_login_provider = check_login_provider
    if get_admin_user_id_provider is not None:
        _get_admin_user_id_provider = get_admin_user_id_provider
    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if tmdb_client_provider is not None:
        _tmdb_client_provider = tmdb_client_provider
    if get_safe_proxies_provider is not None:
        _get_safe_proxies_provider = get_safe_proxies_provider


@router.get("/api/stats/latest")
def api_latest_media(request: Request = None, limit: int = 60):
    # 🔒 安全检查（内部调用时 request 为 None，跳过检查）
    if request and not _check_login_provider()(request):
        return {"status": "error", "message": "请先登录"}
    """获取最近入库资源 - 封面优先 TMDB 公网 URL"""
    try:
        # 🔥 管理员登录后显示所有最近入库（使用管理员ID）
        user_id = _get_admin_user_id_provider()()
        if not user_id:
            return {"status": "error", "data": []}

        params = {
            "SortBy": "DateCreated", "SortOrder": "Descending",
            "IncludeItemTypes": "Movie,Episode", "Recursive": "true",
            "Limit": 500, "Fields": "ProductionYear,SeriesName,SeriesId,ParentIndexNumber,IndexNumber,DateCreated,Overview,ImageTags,ProviderIds"
        }
        res = _media_api_provider().get(f"/Users/{user_id}/Items", params=params, timeout=15)
        if res.status_code != 200: return {"status": "error", "data": []}

        items_raw = res.json().get("Items", [])
        data = []; seen_series = {}
        proxies = _get_safe_proxies_provider()()

        # 🔥 批量获取 TMDB 封面（并发）
        tmdb_requests = []
        pending_items = []

        for item in items_raw:
            if len(pending_items) >= limit: break
            itype = item.get("Type")

            if itype == "Episode":
                sid = item.get("SeriesId") or ""
                if not sid: continue
                if sid in seen_series:
                    ep_idx = item.get("IndexNumber")
                    if ep_idx:
                        seen_series[sid]["EpisodeMin"] = min(seen_series[sid]["EpisodeMin"], ep_idx)
                        seen_series[sid]["EpisodeMax"] = max(seen_series[sid]["EpisodeMax"], ep_idx)
                        seen_series[sid]["EpisodeCount"] += 1
                    continue

                tmdb_id = item.get("ProviderIds", {}).get("Tmdb")
                ep_idx = item.get("IndexNumber")
                season_idx = item.get("ParentIndexNumber") or 1
                # 🔥 获取 ImageTag 用于缓存版本控制
                image_tag = item.get("ImageTags", {}).get("Primary", "")[:8] if item.get("ImageTags", {}).get("Primary") else ""

                seen_series[sid] = {
                    "Id": sid,
                    "Name": item.get("SeriesName", item.get("Name", "")),
                    "SeriesId": sid,
                    "Year": item.get("ProductionYear"),
                    "Type": "Series",
                    "SeasonIndex": season_idx,
                    "EpisodeMin": ep_idx or 1,
                    "EpisodeMax": ep_idx or 1,
                    "EpisodeCount": 1,
                    "Poster": "",  # 🔥 默认空，前端会使用代理 API
                    "Overview": "",
                    "TmdbId": tmdb_id,
                    "ImageTag": image_tag  # 🔥 添加 ImageTag
                }
                pending_items.append(("series", sid))

                if tmdb_id:
                    tmdb_requests.append((tmdb_id, "tv", sid))

            elif itype == "Movie":
                tmdb_id = item.get("ProviderIds", {}).get("Tmdb")
                item_id = item.get("Id")
                # 🔥 获取 ImageTag 用于缓存版本控制
                image_tag = item.get("ImageTags", {}).get("Primary", "")[:8] if item.get("ImageTags", {}).get("Primary") else ""
                pending_items.append(("movie", item_id, image_tag))  # 🔥 传递 image_tag
                if tmdb_id:
                    tmdb_requests.append((tmdb_id, "movie", item_id))

        # 🔥 并发获取 TMDB 封面
        tmdb_cache = {}
        def fetch_tmdb(tmdb_id, media_type):
            try:
                if media_type == "movie":
                    r = _tmdb_client_provider().get_movie_details(tmdb_id, proxies=proxies, timeout=8)
                else:
                    r = _tmdb_client_provider().get_tv_details(tmdb_id, proxies=proxies, timeout=8)
                if r.status_code == 200:
                    d = r.json()
                    poster_path = d.get("poster_path")
                    # 🔥 返回 TMDB 公网 URL
                    poster = f"https://image.tmdb.org/t/p/w300{poster_path}" if poster_path else ""
                    overview = (d.get("overview", "") or "")[:200]
                    return poster, overview
            except:
                pass
            return "", ""

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(fetch_tmdb, t[0], t[1]): t[2] for t in tmdb_requests}
            for future in as_completed(futures, timeout=30):
                key = futures[future]
                poster, overview = future.result()
                tmdb_cache[key] = {"poster": poster, "overview": overview}

        # 🔥 组装数据 - Poster 只使用 TMDB URL，不使用 Emby URL
        for item in pending_items:
            if item[0] == "series":
                key = item[1]
                item_data = seen_series.get(key)
                if item_data:
                    cached = tmdb_cache.get(item_data.get("TmdbId") or key, {})
                    # 🔥 只使用 TMDB URL，前端会通过代理 API 处理无封面的情况
                    item_data["Poster"] = cached.get("poster", "")
                    item_data["Overview"] = cached.get("overview", "")
                    data.append(item_data)
            elif item[0] == "movie":
                key = item[1]
                image_tag = item[2] if len(item) > 2 else ""
                for raw in items_raw:
                    if raw.get("Id") == key and raw.get("Type") == "Movie":
                        cached = tmdb_cache.get(raw.get("ProviderIds", {}).get("Tmdb") or key, {})
                        data.append({
                            "Id": key,
                            "Name": raw.get("Name", ""),
                            "Year": raw.get("ProductionYear"),
                            "Type": "Movie",
                            "Poster": cached.get("poster", ""),  # 🔥 只使用 TMDB URL
                            "Overview": cached.get("overview", ""),
                            "TmdbId": raw.get("ProviderIds", {}).get("Tmdb"),
                            "ImageTag": image_tag  # 🔥 添加 ImageTag
                        })
                        break

        return {"status": "success", "data": data[:limit]}
    except Exception as e:
        print(f"[latest] error: {e}")
    return {"status": "error", "data": []}
