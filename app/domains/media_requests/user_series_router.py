from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Request

from app.core.security_utils import safe_error_message
from app.domains.media_requests.discovery_router import get_emby_admin
from app.domains.media_requests.media_request_dao import (
    decode_gap_cache,
    get_update_cost_config,
    get_user_series_db_context,
)
from app.infra.clients.media_server_client import media_api
from app.infra.clients.tmdb_client import tmdb_client
from app.utils.proxy_helper import get_safe_proxies


router = APIRouter()

_media_api_provider = lambda: media_api
_get_emby_admin_provider = lambda: get_emby_admin
_tmdb_client_provider = lambda: tmdb_client
_safe_proxies_provider = lambda: get_safe_proxies
_get_user_series_db_context_provider = lambda: get_user_series_db_context
_decode_gap_cache_provider = lambda: decode_gap_cache
_get_update_cost_config_provider = lambda: get_update_cost_config
_safe_error_message_provider = lambda: safe_error_message


def _default_gap_scan_dependencies():
    from app.domains.media_requests.gaps import run_scan_task, scan_state, state_lock

    return scan_state, state_lock, run_scan_task


_gap_scan_dependencies_provider = _default_gap_scan_dependencies


def set_dependency_providers(
    *,
    media_api_provider=None,
    get_emby_admin_provider=None,
    tmdb_client_provider=None,
    safe_proxies_provider=None,
    get_user_series_db_context_provider=None,
    decode_gap_cache_provider=None,
    get_update_cost_config_provider=None,
    safe_error_message_provider=None,
    gap_scan_dependencies_provider=None,
):
    global _media_api_provider
    global _get_emby_admin_provider
    global _tmdb_client_provider
    global _safe_proxies_provider
    global _get_user_series_db_context_provider
    global _decode_gap_cache_provider
    global _get_update_cost_config_provider
    global _safe_error_message_provider
    global _gap_scan_dependencies_provider

    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if get_emby_admin_provider is not None:
        _get_emby_admin_provider = get_emby_admin_provider
    if tmdb_client_provider is not None:
        _tmdb_client_provider = tmdb_client_provider
    if safe_proxies_provider is not None:
        _safe_proxies_provider = safe_proxies_provider
    if get_user_series_db_context_provider is not None:
        _get_user_series_db_context_provider = get_user_series_db_context_provider
    if decode_gap_cache_provider is not None:
        _decode_gap_cache_provider = decode_gap_cache_provider
    if get_update_cost_config_provider is not None:
        _get_update_cost_config_provider = get_update_cost_config_provider
    if safe_error_message_provider is not None:
        _safe_error_message_provider = safe_error_message_provider
    if gap_scan_dependencies_provider is not None:
        _gap_scan_dependencies_provider = gap_scan_dependencies_provider


def _get_local_episodes(series_id: str, season: int) -> set:
    """获取库里某剧集某季已有的集数"""
    try:
        admin_id = _get_emby_admin_provider()()
        if not admin_id:
            return set()

        eps_data = _media_api_provider().get(f"/Users/{admin_id}/Items", params={
            "ParentId": series_id,
            "IncludeItemTypes": "Episode",
            "Recursive": "true",
            "Fields": "IndexNumber,ParentIndexNumber"
        }, timeout=10).json().get("Items", [])

        local_eps = set()
        for ep in eps_data:
            sn = ep.get("ParentIndexNumber")
            en = ep.get("IndexNumber")
            if sn == season and en is not None:
                local_eps.add(en)

        return local_eps
    except Exception as e:
        print(f"[追新] 获取本地集数失败: {e}")
        return set()


def _get_tmdb_season_episodes(tmdb_id: int, season: int) -> dict:
    """获取 TMDB 某季的集数信息"""
    proxies = _safe_proxies_provider()()

    try:
        res = _tmdb_client_provider().get_tv_season(tmdb_id, season, proxies=proxies, timeout=10).json()

        episodes = []
        for ep in res.get("episodes", []):
            episodes.append({
                "episode_number": ep.get("episode_number"),
                "name": ep.get("name", ""),
                "air_date": ep.get("air_date", "")
            })

        return {
            "total_episodes": len(episodes),
            "episodes": episodes
        }
    except Exception as e:
        print(f"[追新] 获取 TMDB 集数失败: {e}")
        return {"total_episodes": 0, "episodes": []}


@router.get("/api/user/my_series")
def get_user_series(request: Request):
    """获取用户观看过的剧集列表（用于追新）- 缓存优化版"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}

    uid = user['Id']
    proxies = _safe_proxies_provider()()

    try:
        # 🚀 优化：从缺集管理缓存读取数据，大幅提速
        cache_row, cache_interval_hours, update_requests = _get_user_series_db_context_provider()()

        # 3. 检查缓存是否过期
        cache_expired = False
        if cache_row:
            updated_at = cache_row["updated_at"] or ""
            try:
                cache_time = datetime.strptime(updated_at, "%Y-%m-%d %H:%M:%S")
                now = datetime.now()
                cache_expired = (now - cache_time) > timedelta(hours=cache_interval_hours)
            except:
                cache_expired = True

        # 4. 获取用户最近播放的剧集（用于匹配缓存）
        try:
            eps_res = _media_api_provider().get(f"/Users/{uid}/Items", params={
                "IncludeItemTypes": "Episode",
                "Recursive": "true",
                "SortBy": "DatePlayed",
                "SortOrder": "Descending",
                "Limit": 50,
                "Fields": "SeriesId,SeriesName",
            }, timeout=10).json()
        except:
            eps_res = {"Items": []}

        # 5. 按 series_id 分组用户观看的剧集
        user_series_ids = set()
        for ep in eps_res.get("Items", []):
            series_id = ep.get("SeriesId")
            if series_id:
                user_series_ids.add(series_id)

        # 🚀 7. 从缓存匹配用户观看的剧集
        results = []
        gap_cache = _decode_gap_cache_provider()(cache_row)

        # 如果缓存为空或过期，提示用户刷新
        if not gap_cache:
            # 获取追新积分配置
            update_config = _get_update_cost_config_provider()()

            return {
                "status": "success",
                "data": [],
                "cache_info": {
                    "exists": False,
                    "expired": True,
                    "updated_at": "",
                    "interval_hours": cache_interval_hours
                },
                "update_cost_info": {
                    "enabled": update_config["enabled"],
                    "cost": update_config["cost"]
                }
            }

        # 8. 匹配用户观看的剧集
        for series in gap_cache:
            series_id = series.get("series_id")
            tmdb_id = series.get("tmdb_id")  # 🔥 修复：用 tmdb_id 查询状态
            if series_id not in user_series_ids:
                continue

            # 过滤掉已完结的剧集
            if series.get("tmdb_status") in ["Ended", "Canceled"]:
                continue

            # 获取该剧的追新请求状态 - 🔥 修复：用 tmdb_id + season
            gaps = series.get("gaps", [])
            series_request_status = {}
            for gap in gaps:
                season = gap.get("season")
                req_key = f"{tmdb_id}_{season}"  # tmdb_id + season
                if req_key in update_requests:
                    series_request_status[season] = update_requests[req_key]

            # 构建每季的缺集信息
            seasons_info = []
            grouped_gaps = {}
            for gap in gaps:
                sn = gap.get("season")
                if sn not in grouped_gaps:
                    grouped_gaps[sn] = []
                grouped_gaps[sn].append(gap.get("episode"))

            # 🔥 按季排序显示
            for sn in sorted(grouped_gaps.keys()):
                missing_eps = sorted(grouped_gaps[sn]) if grouped_gaps[sn] else []
                req_key = f"{tmdb_id}_{sn}"  # 🔥 修复：用 tmdb_id + season
                req_status = update_requests.get(req_key)

                # 🔥 修复：从 gaps 数据推断总集数和本地集数
                # gaps 里只有缺失的集数，无法准确知道总集数
                # 使用缺失集数的最大值作为最小总集数估计
                tmdb_total = max(missing_eps) if missing_eps else 10  # 默认假设10集
                local_count = 0  # 缓存模式无法准确获取本地集数

                seasons_info.append({
                    "season": int(sn),  # 🔥 确保是整数
                    "local_count": local_count,
                    "tmdb_total": tmdb_total,
                    "local_eps": [],
                    "missing_eps": missing_eps,
                    "unaired_eps": [],
                    "request_status": req_status
                })

            if seasons_info:
                results.append({
                    "series_id": series_id,
                    "series_name": series.get("series_name", "未知剧集"),
                    "tmdb_id": series.get("tmdb_id"),
                    "poster": series.get("poster", ""),
                    "year": "",
                    "total_seasons": len(seasons_info),
                    "seasons": seasons_info
                })

        # 9. 获取追新积分配置
        update_config = _get_update_cost_config_provider()()

        return {
            "status": "success",
            "data": results[:10],
            "cache_info": {
                "exists": bool(cache_row),
                "expired": cache_expired,
                "updated_at": cache_row["updated_at"] if cache_row else "",
                "interval_hours": cache_interval_hours
            },
            "update_cost_info": {
                "enabled": update_config["enabled"],
                "cost": update_config["cost"],
                "mode": update_config["mode"],
                "base_cost": update_config["cost"]
            }
        }

    except Exception as e:
        return {"status": "error", "message": _safe_error_message_provider()(e)}


@router.post("/api/user/my_series/refresh")
def refresh_my_series_cache(request: Request, bg_tasks: BackgroundTasks):
    """手动刷新追剧缓存（触发后台重新扫描）"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}

    # 触发缺集管理重新扫描
    try:
        # 调用 gaps 模块的扫描功能
        scan_state, state_lock, run_scan_task = _gap_scan_dependencies_provider()

        with state_lock:
            if scan_state["is_scanning"]:
                return {"status": "success", "message": "正在扫描中，请稍后再查看"}
            scan_state.update({"is_scanning": True, "progress": 0, "total": 0, "results": [], "error": None, "current_item": "系统准备中..."})

        bg_tasks.add_task(run_scan_task)
        return {"status": "success", "message": "已触发后台扫描，请稍后刷新查看"}
    except Exception as e:
        return {"status": "error", "message": _safe_error_message_provider()(e)}
