from fastapi import APIRouter
from app.domains.playback import dashboard_cache_service
from app.domains.playback.badges_router import (
    api_badges,
    router as badges_router,
    set_dependency_providers as set_badges_dependency_providers,
)
from app.domains.playback.chart_router import (
    api_chart_stats,
    router as chart_router,
    set_dependency_providers as set_chart_dependency_providers,
)
from app.domains.playback.dashboard_router import (
    api_dashboard,
    router as dashboard_router,
    set_dependency_providers as set_dashboard_dependency_providers,
)
from app.domains.playback.dashboard_init_router import (
    api_dashboard_init,
    router as dashboard_init_router,
    set_dependency_providers as set_dashboard_init_dependency_providers,
)
from app.domains.playback.item_detail_router import (
    api_item_detail,
    router as item_detail_router,
    set_dependency_providers as set_item_detail_dependency_providers,
)
from app.domains.playback.latest_router import (
    api_latest_media,
    router as latest_router,
    set_dependency_providers as set_latest_dependency_providers,
)
from app.domains.playback.live_router import (
    api_live_sessions,
    api_live_sessions_legacy,
    router as live_router,
    set_dependency_providers as set_live_dependency_providers,
)
from app.domains.playback.monthly_router import (
    api_monthly_stats,
    router as monthly_router,
    set_dependency_providers as set_monthly_dependency_providers,
)
from app.domains.playback.poster_router import (
    api_poster_data,
    router as poster_router,
    set_dependency_providers as set_poster_dependency_providers,
)
from app.domains.playback.preload_status_router import (
    api_preload_status,
    router as preload_status_router,
    set_dependency_providers as set_preload_status_dependency_providers,
)
from app.domains.playback.recent_added_router import (
    api_recent_added,
    router as recent_added_router,
    set_dependency_providers as set_recent_added_dependency_providers,
)
from app.domains.playback.recent_activity_router import (
    api_recent_activity,
    router as recent_activity_router,
    set_dependency_providers as set_recent_activity_dependency_providers,
)
from app.domains.playback.system_monitor_router import (
    api_system_monitor,
    router as system_monitor_router,
    set_dependency_providers as set_system_monitor_dependency_providers,
)
from app.domains.playback.top_users_router import (
    api_top_users_list,
    router as top_users_router,
    set_dependency_providers as set_top_users_dependency_providers,
)
from app.domains.playback.top_movies_router import (
    api_top_movies,
    router as top_movies_router,
    set_dependency_providers as set_top_movies_dependency_providers,
)
from app.domains.playback.user_details_router import (
    api_user_details,
    router as user_details_router,
    set_dependency_providers as set_user_details_dependency_providers,
)
from app.domains.playback.libraries_router import (
    api_get_libraries,
    router as libraries_router,
    set_dependency_providers as set_libraries_dependency_providers,
)
from app.domains.playback.stats_helpers import (
    STATS_CACHE_TTL,
    _stats_cache,
    check_login,
    get_admin_user_id,
    get_cached_stats,
    get_clean_name,
    get_user_map_local,
    require_admin_login,
    resolve_poster_ids,
    set_cached_stats,
)
from app.domains.playback.stats_queries import build_stats_base_filter, get_playback_column_name
from app.infra.db.playback_store import playback_store
from app.utils.proxy_helper import get_safe_proxies  # 🔒 SSRF 安全代理读取
# 🔥 引入核心适配器
from app.infra.clients.media_server_client import media_api
from app.infra.clients.tmdb_client import tmdb_client
from app.infra.config.user_visibility_settings import get_hidden_users
from app.domains.users import public_service as user_service  # 🔒 引入管理员权限检查
import re
import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor
import psutil
import time  # 🔥 用于预热缓存时间戳
import copy
import logging
from app.core.security_utils import safe_error_message

logger = logging.getLogger("uvicorn")

router = APIRouter()

set_libraries_dependency_providers(
    user_service_provider=lambda: user_service,
    media_api_provider=lambda: media_api,
    get_admin_user_id_provider=lambda: get_admin_user_id,
    safe_error_message_provider=lambda: safe_error_message,
)

set_latest_dependency_providers(
    check_login_provider=lambda: check_login,
    get_admin_user_id_provider=lambda: get_admin_user_id,
    media_api_provider=lambda: media_api,
    tmdb_client_provider=lambda: tmdb_client,
    get_safe_proxies_provider=lambda: get_safe_proxies,
)

set_live_dependency_providers(
    user_service_provider=lambda: user_service,
    media_api_provider=lambda: media_api,
)

set_top_movies_dependency_providers(
    check_login_provider=lambda: check_login,
    build_stats_base_filter_provider=lambda: build_stats_base_filter,
    playback_store_provider=lambda: playback_store,
    get_clean_name_provider=lambda: get_clean_name,
    resolve_poster_ids_provider=lambda: resolve_poster_ids,
    logger_provider=lambda: logger,
)

set_user_details_dependency_providers(
    check_login_provider=lambda: check_login,
    build_stats_base_filter_provider=lambda: build_stats_base_filter,
    get_playback_column_name_provider=lambda: get_playback_column_name,
    playback_store_provider=lambda: playback_store,
    get_user_map_local_provider=lambda: get_user_map_local,
    get_clean_name_provider=lambda: get_clean_name,
    resolve_poster_ids_provider=lambda: resolve_poster_ids,
    media_api_provider=lambda: media_api,
)

set_chart_dependency_providers(
    check_login_provider=lambda: check_login,
    build_stats_base_filter_provider=lambda: build_stats_base_filter,
    playback_store_provider=lambda: playback_store,
)

set_poster_dependency_providers(
    check_login_provider=lambda: check_login,
    build_stats_base_filter_provider=lambda: build_stats_base_filter,
    playback_store_provider=lambda: playback_store,
    media_api_provider=lambda: media_api,
    get_clean_name_provider=lambda: get_clean_name,
    resolve_poster_ids_provider=lambda: resolve_poster_ids,
)

set_top_users_dependency_providers(
    user_service_provider=lambda: user_service,
    build_stats_base_filter_provider=lambda: build_stats_base_filter,
    playback_store_provider=lambda: playback_store,
    get_user_map_local_provider=lambda: get_user_map_local,
    get_hidden_users_provider=lambda: get_hidden_users,
)

set_badges_dependency_providers(
    check_login_provider=lambda: check_login,
    build_stats_base_filter_provider=lambda: build_stats_base_filter,
    get_playback_column_name_provider=lambda: get_playback_column_name,
    playback_store_provider=lambda: playback_store,
)

set_monthly_dependency_providers(
    check_login_provider=lambda: check_login,
    build_stats_base_filter_provider=lambda: build_stats_base_filter,
    playback_store_provider=lambda: playback_store,
)

set_recent_added_dependency_providers(
    check_login_provider=lambda: check_login,
    get_added_stats_sync_provider=lambda: _get_added_stats_sync,
)

set_recent_activity_dependency_providers(
    check_login_provider=lambda: check_login,
    build_stats_base_filter_provider=lambda: build_stats_base_filter,
    playback_store_provider=lambda: playback_store,
    get_user_map_local_provider=lambda: get_user_map_local,
    media_api_provider=lambda: media_api,
)

set_system_monitor_dependency_providers(
    user_service_provider=lambda: user_service,
    psutil_provider=lambda: psutil,
    safe_error_message_provider=lambda: safe_error_message,
)

set_dashboard_dependency_providers(
    check_login_provider=lambda: check_login,
    build_stats_base_filter_provider=lambda: build_stats_base_filter,
    playback_store_provider=lambda: playback_store,
    get_cached_stats_provider=lambda: get_cached_stats,
    set_cached_stats_provider=lambda: set_cached_stats,
    media_api_provider=lambda: media_api,
)

set_preload_status_dependency_providers(
    user_service_provider=lambda: user_service,
    get_dashboard_cache_entry_provider=lambda: _get_dashboard_cache_entry,
    dashboard_preload_key_provider=lambda: _DASHBOARD_PRELOAD_KEY,
    dashboard_cache_ttl_provider=lambda: _DASHBOARD_CACHE_TTL,
    time_provider=lambda: time,
)

set_dashboard_init_dependency_providers(
    user_service_provider=lambda: user_service,
    get_dashboard_context_provider=lambda: _get_dashboard_context,
    mark_dashboard_access_provider=lambda: _mark_dashboard_access,
    get_dashboard_cached_data_provider=lambda: _get_dashboard_cached_data,
    fetch_dashboard_core_provider=lambda: _fetch_dashboard_core,
    fetch_users_list_provider=lambda: _fetch_users_list,
    fetch_libraries_provider=lambda: _fetch_libraries,
    fetch_top_users_provider=lambda: _fetch_top_users,
    fetch_trend_provider=lambda: _fetch_trend,
    get_dashboard_cache_entry_provider=lambda: _get_dashboard_cache_entry,
    set_dashboard_cache_provider=lambda: _set_dashboard_cache,
    asyncio_provider=lambda: asyncio,
    copy_provider=lambda: copy,
    time_provider=lambda: time,
)

set_item_detail_dependency_providers(
    check_login_provider=lambda: check_login,
    media_api_provider=lambda: media_api,
    playback_store_provider=lambda: playback_store,
    get_user_map_local_provider=lambda: get_user_map_local,
    logger_provider=lambda: logger,
    re_provider=lambda: re,
    safe_error_message_provider=lambda: safe_error_message,
)

router.include_router(dashboard_router)

router.include_router(libraries_router)

router.include_router(recent_activity_router)

router.include_router(latest_router)

router.include_router(live_router)

router.include_router(top_movies_router)


router.include_router(user_details_router)

router.include_router(chart_router)

router.include_router(poster_router)

router.include_router(top_users_router)

router.include_router(badges_router)

router.include_router(monthly_router)

router.include_router(recent_added_router)

# ==========================================
# 🔥 仪表盘聚合 API - 核心数据快速返回
# ==========================================
_executor = ThreadPoolExecutor(max_workers=8)

# Dashboard cache service compatibility exports. Existing tests and diagnostics
# reach these names through stats.py, while the implementation now lives in the
# domain-local service module.
_DASHBOARD_PRELOAD_KEY = dashboard_cache_service._DASHBOARD_PRELOAD_KEY
_dashboard_cache = dashboard_cache_service._dashboard_cache
_dashboard_cache_user_ids = dashboard_cache_service._dashboard_cache_user_ids
_DASHBOARD_CACHE_TTL = dashboard_cache_service._DASHBOARD_CACHE_TTL
_dashboard_last_access = dashboard_cache_service._dashboard_last_access

_normalize_dashboard_user_id = dashboard_cache_service._normalize_dashboard_user_id
_get_dashboard_context = dashboard_cache_service._get_dashboard_context
_get_dashboard_cache_entry = dashboard_cache_service._get_dashboard_cache_entry
_set_dashboard_cache = dashboard_cache_service._set_dashboard_cache
_mark_dashboard_access = dashboard_cache_service._mark_dashboard_access
_fetch_dashboard_core = dashboard_cache_service._fetch_dashboard_core
_fetch_users_list = dashboard_cache_service._fetch_users_list
_fetch_libraries = dashboard_cache_service._fetch_libraries
_fetch_top_users = dashboard_cache_service._fetch_top_users
_fetch_trend = dashboard_cache_service._fetch_trend
preload_dashboard_cache = dashboard_cache_service.preload_dashboard_cache
start_dashboard_cache_refresh_loop = dashboard_cache_service.start_dashboard_cache_refresh_loop

_dashboard_cache_tasks_started = False
_dashboard_preload_task = None
_dashboard_refresh_task = None


def _sync_dashboard_task_state() -> None:
    global _dashboard_cache_tasks_started, _dashboard_preload_task, _dashboard_refresh_task
    _dashboard_cache_tasks_started = dashboard_cache_service._dashboard_cache_tasks_started
    _dashboard_preload_task = dashboard_cache_service._dashboard_preload_task
    _dashboard_refresh_task = dashboard_cache_service._dashboard_refresh_task


def _get_dashboard_cached_data(cache_key: str, now: float = None):
    now = now or time.time()
    entry = _get_dashboard_cache_entry(cache_key)
    if entry.get("data") and (now - entry.get("ts", 0)) < _DASHBOARD_CACHE_TTL:
        return entry["data"]
    return None

router.include_router(preload_status_router)

router.include_router(dashboard_init_router)


def start_dashboard_cache_tasks() -> None:
    dashboard_cache_service.start_dashboard_cache_tasks(
        preload_func=preload_dashboard_cache,
        refresh_func=start_dashboard_cache_refresh_loop,
    )
    _sync_dashboard_task_state()


def stop_dashboard_cache_tasks() -> None:
    dashboard_cache_service.stop_dashboard_cache_tasks()
    _sync_dashboard_task_state()


# 入库统计内存缓存
_added_stats_cache = {"data": None, "ts": 0}
_ADDED_STATS_CACHE_TTL = 300  # 5分钟缓存

def _get_added_stats_sync():
    """同步获取入库统计（用于线程池执行）"""
    import time
    
    # 🔥 检查内存缓存
    now = time.time()
    if _added_stats_cache["data"] and (now - _added_stats_cache["ts"]) < _ADDED_STATS_CACHE_TTL:
        return _added_stats_cache["data"]
    
    try:
        admin_id = None
        try:
            users = media_api.get("/Users", timeout=5).json()
            for u in users:
                if u.get("Policy", {}).get("IsAdministrator"):
                    admin_id = u['Id']
                    break
            if not admin_id and users:
                admin_id = users[0]['Id']
        except:
            pass

        # 获取所有媒体库
        libraries = []
        try:
            lib_res = media_api.get(f"/Users/{admin_id}/Views", timeout=10).json()
            libraries = lib_res.get("Items", [])
        except:
            pass

        today = datetime.datetime.now()
        start_of_week = today - datetime.timedelta(days=today.weekday())
        start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)

        week_counts = [0] * 7
        total_this_week = 0

        # 按媒体库分别查询
        for lib in libraries:
            try:
                lib_id = lib.get("Id")
                if not lib_id:
                    continue
                
                lib_count = 0
                start_index = 0
                page_size = 500
                should_stop = False
                
                while not should_stop and start_index < 10000:
                    params = {
                        "ParentId": lib_id,
                        "SortBy": "DateCreated",
                        "SortOrder": "Descending",
                        "IncludeItemTypes": "Movie,Series,Episode",
                        "Recursive": "true",
                        "StartIndex": start_index,
                        "Limit": page_size,
                        "Fields": "DateCreated"
                    }
                    res = media_api.get(f"/Users/{admin_id}/Items", params=params, timeout=20).json()
                    items = res.get("Items", [])
                    
                    if not items:
                        break
                    
                    page_has_this_week = False
                    for item in items:
                        date_str = item.get("DateCreated")
                        if not date_str:
                            continue
                        try:
                            clean_date = date_str.split('.')[0].replace("Z", "")
                            dt = datetime.datetime.fromisoformat(clean_date)
                            # UTC 转北京时间
                            dt_local = dt + datetime.timedelta(hours=8)
                            
                            if dt_local >= start_of_week:
                                week_counts[dt_local.weekday()] += 1
                                total_this_week += 1
                                lib_count += 1
                                page_has_this_week = True
                            else:
                                should_stop = True
                                break
                        except:
                            pass
                    
                    if not page_has_this_week:
                        should_stop = True
                    
                    start_index += page_size
                    if len(items) < page_size:
                        break
                        
            except:
                continue

        result = {"total_this_week": total_this_week, "trend": week_counts}
        
        # 🔥 更新缓存
        _added_stats_cache["data"] = result
        _added_stats_cache["ts"] = now
        
        return result
    except:
        return {"total_this_week": 0, "trend": [0]*7}


router.include_router(system_monitor_router)

router.include_router(item_detail_router)
