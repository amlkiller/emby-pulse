from fastapi import APIRouter, BackgroundTasks, Request
import threading
import concurrent.futures
from datetime import datetime
from typing import List, Dict, Any, Optional
import json
import re
import time
import logging

from app.core.config import cfg
from app.dao.gap_dao import (
    add_gap_perfect_series,
    delete_gap_perfect_series,
    delete_gap_record_by_id,
    delete_gap_record_by_series_episode,
    delete_gap_records_by_series_id,
    ensure_gap_tables,
    get_gap_cache_interval_hours,
    get_gap_config_map,
    get_gap_config_value,
    list_gap_ignore_records,
    list_gap_perfect_records,
    list_gap_perfect_series_ids,
    list_gap_records_for_lock,
    list_ignored_series_ids,
    load_gap_scan_cache,
    save_gap_config_value,
    save_gap_record_status,
    save_gap_scan_cache,
)
from app.routers.search import get_emby_sys_info, is_new_emby_router
from app.routers.auth import is_admin_user
# 🔥 引入核心适配器
from app.infra.clients.media_server_client import media_api
from app.infra.clients.moviepilot_client import moviepilot_client
from app.infra.clients.qbittorrent_client import qbittorrent_client
from app.infra.clients.transmission_client import transmission_client
from app.infra.clients.tmdb_client import tmdb_client

logger = logging.getLogger("uvicorn")

router = APIRouter(prefix="/api/gaps", tags=["gaps"])

# 模块加载时确保表存在
def _ensure_gap_tables():
    """确保缺集相关表存在"""
    try:
        ensure_gap_tables(logger)
    except Exception as e:
        logger.error(f"[缺集管理] 初始化表失败: {e}")

_ensure_gap_tables()

scan_state = {"is_scanning": False, "progress": 0, "total": 0, "current_item": "系统准备中...", "results": [], "error": None}
state_lock = threading.Lock()

def update_progress(item_name=None):
    with state_lock:
        scan_state["progress"] += 1
        if item_name: scan_state["current_item"] = f"分析剧集: {item_name[:20]}"

def _get_proxies():
    from app.utils.proxy_helper import get_safe_proxies
    return get_safe_proxies()

def get_admin_user_id():
    try:
        # 🚀 替换为 media_api
        users = media_api.get("/Users", timeout=5).json()
        for u in users:
            if u.get("Policy", {}).get("IsAdministrator"): return u['Id']
        return users[0]['Id'] if users else None
    except: return None

# 🔥 修复：移除了多余的 key 参数
def process_single_series(series, lock_map, host, tmdb_key, proxies, today, global_inventory, server_id, use_new_route):
    series_id = series.get("Id"); series_name = series.get("Name", "未知剧集")
    tmdb_id = series.get("ProviderIds", {}).get("Tmdb")
    if not tmdb_id or lock_map.get(f"{series_id}_-1_-1", 0) == 1:
        update_progress(series_name)
        return None

    local_inventory = global_inventory.get(series_id, {})
    try:
        tmdb_series_data = tmdb_client.get_tv_details(tmdb_id, proxies=proxies, timeout=10).json()
        tmdb_seasons = tmdb_series_data.get("seasons", []); tmdb_status = tmdb_series_data.get("status", "") 
    except: 
        update_progress(series_name)
        return None

    series_gaps = []
    for season in tmdb_seasons:
        s_num = season.get("season_number")
        if not s_num or season.get("episode_count", 0) == 0: continue
        local_season_inventory = local_inventory.get(s_num, set())
        if len(local_season_inventory) >= season.get("episode_count", 0): continue
        try: tmdb_episodes = tmdb_client.get_tv_season(tmdb_id, s_num, proxies=proxies, timeout=10).json().get("episodes", [])
        except: continue
        for tmdb_ep in tmdb_episodes:
            e_num = tmdb_ep.get("episode_number"); air_date = tmdb_ep.get("air_date")
            
            if not air_date or air_date >= today: continue
                
            if e_num not in local_season_inventory and lock_map.get(f"{series_id}_{s_num}_{e_num}", 0) != 1:
                series_gaps.append({"season": s_num, "episode": e_num, "title": tmdb_ep.get("name", f"第 {e_num} 集"), "status": lock_map.get(f"{series_id}_{s_num}_{e_num}", 0)})
    
    update_progress(series_name) 
    if series_gaps:
        public_host = (cfg.get_main_public_url() or cfg.get("emby_host") or host).rstrip('/')
        emby_url = f"{public_host}/web/index.html#!/item?id={series_id}&serverId={server_id}" if use_new_route else f"{public_host}/web/index.html#!/item/details.html?id={series_id}&serverId={server_id}"
        return {"series_id": series_id, "series_name": series_name, "tmdb_id": tmdb_id, "tmdb_status": tmdb_status, "poster": f"/api/library/image/{series_id}?type=Primary&width=300", "emby_url": emby_url, "gaps": series_gaps}
    else:
        if tmdb_status in ["Ended", "Canceled"]:
            try: add_gap_perfect_series(series_id, tmdb_id, series_name)
            except Exception: pass
        return None

# 🔥 定时任务：后台自动刷新缺集缓存
def _start_background_gap_sync():
    """
    后台独立线程：定时自动刷新缺集扫描缓存。
    间隔时间从 gap_config 表读取 cache_interval_hours 配置（默认6小时）。
    """
    def sync_task():
        # 延迟 120 秒启动，确保系统核心组件已就绪
        time.sleep(120)
        while True:
            try:
                # 从数据库读取缓存间隔配置
                interval_hours = get_gap_cache_interval_hours()
                
                logger.info(f"🔄 [定时任务] 开始在后台自动刷新缺集扫描缓存（间隔: {interval_hours}小时）...")
                
                # 执行扫描任务
                run_scan_task()
                
                logger.info("✅ [定时任务] 缺集扫描后台更新成功，数据已持久化至 SQLite。")
            except Exception as e:
                logger.error(f"❌ [定时任务] 后台同步缺集缓存失败: {e}")
            
            # 休眠指定小时数
            time.sleep(interval_hours * 3600)
    
    # daemon=True 确保主进程退出时线程能正常销毁
    t = threading.Thread(target=sync_task, daemon=True)
    t.start()

# 🔥 启动后台定时任务（延迟启动，等待 run_scan_task 定义完成）
import atexit
from app.core.security_utils import safe_error_message
def _delayed_start_background_sync():
    # 使用定时器延迟启动，确保所有函数已定义
    def start_after_delay():
        time.sleep(5)
        _start_background_gap_sync()
    t = threading.Thread(target=start_after_delay, daemon=True)
    t.start()

_delayed_start_background_sync()

def run_scan_task():
    try:
        logger.info("[缺集扫描] 开始扫描任务...")
        host = cfg.get("emby_host"); tmdb_key = cfg.get("tmdb_api_key"); admin_id = get_admin_user_id()
        proxies = _get_proxies(); today = datetime.now().strftime("%Y-%m-%d")
        
        if not admin_id:
            logger.error("[缺集扫描] 无法获取管理员用户ID")
            return
        
        logger.info(f"[缺集扫描] 管理员ID: {admin_id}, 今日: {today}")
        
        try:
            # 🚀 替换为 media_api
            sys_info = media_api.get("/System/Info/Public", timeout=5).json()
            server_id = sys_info.get("Id", ""); use_new_route = is_new_emby_router(sys_info)
            logger.info(f"[缺集扫描] 服务器ID: {server_id}, 新路由: {use_new_route}")
        except: server_id = ""; use_new_route = True

        # 表结构已由 db_schemas.py 统一创建，此处仅确保数据操作

        records = list_gap_records_for_lock()
        lock_map = {f"{r['series_id']}_{r['season_number']}_{r['episode_number']}": r['status'] for r in records} if records else {}
        logger.info(f"[缺集扫描] 已忽略记录: {len(lock_map)} 条")
        
        perfect_set = set(list_gap_perfect_series_ids())
        logger.info(f"[缺集扫描] 完结免检剧集: {len(perfect_set)} 部")

        # 获取屏蔽的媒体库列表
        excluded_libraries = get_gap_config_value("excluded_libraries")
        excluded_libs = set()
        if excluded_libraries:
            try:
                excluded_libs = set(json.loads(excluded_libraries))
                logger.info(f"[缺集扫描] 屏蔽媒体库: {excluded_libs}")
            except Exception: pass

        # 使用 /Library/VirtualFolders API 获取媒体库
        lib_res = media_api.get("/Library/VirtualFolders", timeout=10)
        all_libraries = lib_res.json() if lib_res.status_code == 200 else []
        logger.info(f"[缺集扫描] 获取到 {len(all_libraries)} 个媒体库")
        
        library_ids = {lib.get("Guid") or lib.get("Id") for lib in all_libraries}

        # 递归获取每个媒体库下的所有Series
        all_series = []
        for lib in all_libraries:
            lib_id = lib.get("Guid") or lib.get("Id")
            lib_name = lib.get("Name", "")
            # 如果该媒体库被屏蔽，跳过
            if lib_id in excluded_libs or lib_name in excluded_libs:
                logger.info(f"[缺集扫描] 跳过屏蔽媒体库: {lib_name}")
                continue
            try:
                lib_series = media_api.get(f"/Users/{admin_id}/Items", params={
                    "ParentId": lib_id,
                    "IncludeItemTypes": "Series",
                    "Recursive": "true",
                    "Fields": "ProviderIds"
                }, timeout=15).json().get("Items", [])
                logger.info(f"[缺集扫描] 媒体库 [{lib_name}] 获取到 {len(lib_series)} 部剧集")
                # 标记每个剧集所属的媒体库
                for s in lib_series:
                    s["_library_id"] = lib_id
                    s["_library_name"] = lib_name
                all_series.extend(lib_series)
            except Exception as e:
                logger.warning(f"[缺集扫描] 获取媒体库 {lib_name} 的剧集失败: {e}")

        # 过滤掉已完结的剧集
        pending_series = [s for s in all_series if s.get("Id") not in perfect_set]
        logger.info(f"[缺集扫描] 待扫描剧集: {len(pending_series)} 部 (已过滤完结免检 {len(perfect_set)} 部)")

        with state_lock:
            scan_state["total"] = len(pending_series)
            scan_state["current_item"] = "正在拉取全库单集缓存..."

        if not pending_series:
            with state_lock: scan_state["results"] = []
            logger.info("[缺集扫描] 无待扫描剧集，任务结束")
            return

        # 🚀 替换为 media_api
        logger.info("[缺集扫描] 正在获取全库单集缓存...")
        all_eps_data = media_api.get(f"/Users/{admin_id}/Items", params={"IncludeItemTypes":"Episode","Recursive":"true","Fields":"IndexNumberEnd"}, timeout=45).json().get("Items", [])
        logger.info(f"[缺集扫描] 获取到 {len(all_eps_data)} 个单集")
        
        global_inventory = {}
        for ep in all_eps_data:
            ser_id = ep.get("SeriesId"); s_num = ep.get("ParentIndexNumber"); e_num = ep.get("IndexNumber"); e_end = ep.get("IndexNumberEnd")
            if not ser_id or s_num is None or e_num is None: continue
            if ser_id not in global_inventory: global_inventory[ser_id] = {}
            if s_num not in global_inventory[ser_id]: global_inventory[ser_id][s_num] = set()
            for i in range(e_num, (e_end if e_end else e_num) + 1): global_inventory[ser_id][s_num].add(i)

        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            # 🔥 修复：调用时移除了多余的 key
            futures = [executor.submit(process_single_series, s, lock_map, host, tmdb_key, proxies, today, global_inventory, server_id, use_new_route) for s in pending_series]
            for f in concurrent.futures.as_completed(futures):
                res = f.result()
                if res: results.append(res)
        
        logger.info(f"[缺集扫描] 扫描完成，发现 {len(results)} 部有缺集的剧集")
        with state_lock: scan_state["results"] = results
        try: save_gap_scan_cache(results)
        except Exception: pass
    except Exception as e:
        logger.error(f"[缺集扫描] 扫描异常: {e}")
        with state_lock: scan_state["error"] = safe_error_message(e)
    finally:
        with state_lock: scan_state["is_scanning"] = False; scan_state["current_item"] = "扫描完成"
        logger.info("[缺集扫描] 任务结束")

@router.post("/scan/start")
def start_scan(request: Request, bg_tasks: BackgroundTasks):
    # 🔒 管理员专用
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    with state_lock:
        if scan_state["is_scanning"]: return {"status": "error"}
        scan_state.update({"is_scanning": True, "progress": 0, "total": 0, "results": [], "error": None, "current_item": "系统准备中..."})
    logger.info("[缺集扫描] 用户触发扫描任务")
    bg_tasks.add_task(run_scan_task)
    return {"status": "success"}

@router.get("/scan/progress")
def get_progress(request: Request):
    # 🔒 管理员专用
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    with state_lock:
        if not scan_state["is_scanning"]:
            if not scan_state["results"]:
                try:
                    cached_results = load_gap_scan_cache()
                    if cached_results: scan_state["results"] = cached_results
                except Exception: pass
            try:
                ignore_ids = set(list_ignored_series_ids())
                scan_state["results"] = [s for s in scan_state["results"] if s.get('series_id') not in ignore_ids]
            except Exception: pass
        return {"status": "success", "data": scan_state}

def run_verify_task():
    try:
        with state_lock:
            if scan_state["is_scanning"] or not scan_state.get("results"): return
            results_copy = json.loads(json.dumps(scan_state["results"]))
            
        admin_id = get_admin_user_id()
        if not admin_id: return
        
        changed = False
        for s in results_copy:
            s_id = s.get("series_id")
            if not s.get("gaps"): continue
            
            try:
                # 🚀 替换为 media_api
                eps_data = media_api.get(f"/Users/{admin_id}/Items", params={"ParentId":s_id,"IncludeItemTypes":"Episode","Recursive":"true","Fields":"IndexNumberEnd"}, timeout=5).json().get("Items", [])
                local_eps = set()
                for ep in eps_data:
                    s_num = ep.get("ParentIndexNumber")
                    e_num = ep.get("IndexNumber")
                    e_end = ep.get("IndexNumberEnd")
                    if s_num is None or e_num is None: continue
                    for i in range(e_num, (e_end if e_end else e_num) + 1):
                        local_eps.add(f"{s_num}_{i}")
                
                original_len = len(s["gaps"])
                new_gaps = []
                for gap in s["gaps"]:
                    if f"{gap['season']}_{gap['episode']}" in local_eps:
                        changed = True
                        try: delete_gap_record_by_series_episode(s_id, gap['season'], gap['episode'])
                        except Exception: pass
                    else:
                        new_gaps.append(gap)
                s["gaps"] = new_gaps
                
                if len(new_gaps) == 0 and changed:
                    if s.get("tmdb_status") in ["Ended", "Canceled"]:
                        try: add_gap_perfect_series(s_id, s.get("tmdb_id"), s.get("series_name"))
                        except Exception: pass
            except Exception: pass
                
        if changed:
            with state_lock:
                if not scan_state["is_scanning"]:
                    scan_state["results"] = [s for s in results_copy if len(s.get("gaps", [])) > 0]
                    try: save_gap_scan_cache(scan_state["results"])
                    except Exception: pass
    except Exception: pass

@router.post("/scan/verify")
def trigger_verify_gaps(request: Request, bg_tasks: BackgroundTasks):
    # 🔒 管理员专用
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    with state_lock:
        if scan_state["is_scanning"]: return {"status": "success"}
    bg_tasks.add_task(run_verify_task)
    return {"status": "success"}



@router.post("/ignore")
def ignore_gap(request: Request, payload: dict):
    # 🔒 管理员专用
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    try:
        s_id = payload.get("series_id"); s_num = int(payload.get("season_number", 0)); e_num = int(payload.get("episode_number", 0))
        save_gap_record_status(s_id, payload.get("series_name", ""), s_num, e_num, 1)
        with state_lock:
            for s in scan_state["results"]:
                if s.get("series_id") == s_id: s["gaps"] = [ep for ep in s.get("gaps", []) if not (ep["season"] == s_num and ep["episode"] == e_num)]
            scan_state["results"] = [s for s in scan_state["results"] if len(s.get("gaps", [])) > 0]
        return {"status": "success"}
    except Exception as e: return {"status": "error"}

@router.post("/ignore/series")
def ignore_entire_series(request: Request, payload: dict):
    # 🔒 管理员专用
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    try:
        s_id = payload.get("series_id")
        save_gap_record_status(s_id, payload.get("series_name", ""), -1, -1, 1)
        with state_lock: scan_state["results"] = [s for s in scan_state["results"] if s.get("series_id") != s_id]
        return {"status": "success"}
    except Exception as e: return {"status": "error"}

@router.get("/ignores")
def get_ignored_list(request: Request):
    # 🔒 管理员专用
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    try:
        records = list_gap_ignore_records()
        perfects = list_gap_perfect_records()
        data = []
        if records:
            for r in records: data.append({"type": "record", "id": r['id'], "series_name": r['series_name'], "target": "全剧集" if r['season_number'] == -1 else f"S{str(r['season_number']).zfill(2)}E{str(r['episode_number']).zfill(2)}", "time": r['created_at']})
        if perfects:
            for r in perfects:
                series_name = r['series_name']
                marked_at = r['marked_at']
                # 检测旧数据格式错误：series_name 存的是 TMDB ID（数字），marked_at 存的是剧集名称
                if series_name and series_name.isdigit() and marked_at and not marked_at.isdigit():
                    # 旧数据格式错误，交换回来
                    series_name = marked_at
                    time_str = r['tmdb_id'] or ''
                else:
                    time_str = marked_at
                data.append({"type": "perfect", "id": r['series_id'], "series_name": series_name, "target": "完结免检金牌", "time": time_str})
        data.sort(key=lambda x: str(x['time'] or '0000-00-00'), reverse=True)
        return {"status": "success", "data": data}
    except Exception as e: return {"status": "error"}

@router.post("/unignore")
def unignore_item(request: Request, payload: dict):
    # 🔒 管理员专用
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    try:
        if payload.get("type") == "record": delete_gap_record_by_id(payload.get("id"))
        elif payload.get("type") == "perfect": delete_gap_perfect_series(payload.get("id"))
        return {"status": "success"}
    except Exception as e: return {"status": "error"}

@router.post("/ignore/delete")
def delete_ignore_item(request: Request, payload: dict):
    # 🔒 管理员专用
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    """彻底删除忽略记录"""
    try:
        item_id = payload.get("id")
        target = payload.get("target")

        if target == "全剧集":
            # 删除 gap_records 中该剧的所有记录
            delete_gap_records_by_series_id(item_id)
        else:
            # 删除单条记录
            delete_gap_record_by_id(item_id)

        return {"status": "success"}
    except Exception as e: return {"status": "error", "message": safe_error_message(e)}

@router.get("/config")
def get_gap_config(request: Request):
    # 🔒 管理员专用
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    conf = get_gap_config_map()
    # 解析 excluded_libraries
    if conf.get('excluded_libraries'):
        try:
            conf['excluded_libraries'] = json.loads(conf['excluded_libraries'])
        except:
            conf['excluded_libraries'] = []
    else:
        conf['excluded_libraries'] = []
    return {"status": "success", "data": conf}

@router.get("/libraries")
def get_libraries(request: Request):
    # 🔒 管理员专用
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    """获取所有媒体库列表（用于屏蔽设置）"""
    try:
        # 使用 /Library/VirtualFolders API 获取媒体库（更可靠）
        lib_res = media_api.get("/Library/VirtualFolders", timeout=10)
        if lib_res.status_code != 200:
            return {"status": "error", "message": f"媒体服务器返回 {lib_res.status_code}"}
        
        libraries = lib_res.json()
        admin_id = get_admin_user_id()

        # 返回所有媒体库，并附带剧集数量（用于显示）
        result = []
        for lib in libraries:
            lib_id = lib.get("Guid") or lib.get("Id")
            lib_name = lib.get("Name", "未知")
            lib_collection_type = lib.get("CollectionType", "")
            
            # 获取剧集数量（用于显示，不再作为过滤条件）
            series_count = 0
            try:
                series_count = media_api.get(f"/Users/{admin_id}/Items", params={
                    "ParentId": lib_id,
                    "IncludeItemTypes": "Series",
                    "Limit": 1
                }, timeout=5).json().get("TotalRecordCount", 0)
            except:
                pass

            result.append({
                "id": lib_id,
                "name": lib_name,
                "series_count": series_count,
                "collection_type": lib_collection_type
            })

        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"[缺集管理] 获取媒体库失败: {e}")
        return {"status": "error", "message": safe_error_message(e)}

@router.post("/config")
def save_gap_config(request: Request, payload: dict):
    # 🔒 管理员专用
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    for k, v in payload.items():
        save_gap_config_value(k, v)
    return {"status": "success"}

# ==================== 影巢搜索 ====================
@router.post("/search_hdhive")
def search_hdhive_for_gap(request: Request = None, payload: dict = None):
    # 🔒 管理员专用（内部调用时 request 为 None，跳过检查）
    if request and not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    """搜索影巢资源（仅115网盘）"""
    series_name = payload.get("series_name", "") if payload else ""
    tmdb_id = payload.get("tmdb_id")
    season = payload.get("season")
    episodes = payload.get("episodes", [])
    res_type = payload.get("type", "tv")  # movie or tv
    
    logger.info(f"[缺集搜索] 开始影巢搜索: {series_name} S{season}E{episodes}, tmdb_id={tmdb_id}")

    if not series_name and not tmdb_id:
        return {"status": "error", "message": "缺少参数"}

    # 调用影巢插件 API
    try:
        from app.plugins import get_plugin
        hdhive = get_plugin("hdhive")
        if not hdhive or not hdhive.enabled:
            return {"status": "error", "message": "影巢插件未启用"}

        # 构建请求参数
        search_data = {}
        if tmdb_id:
            search_data["tmdb_id"] = tmdb_id
            search_data["type"] = res_type
        else:
            # 构造搜索关键词：剧名 + 季
            keyword = series_name
            if season:
                keyword += f" S{str(season).zfill(2)}"
            search_data["keyword"] = keyword

        proxies = _get_proxies()
        
        # 如果有 TMDB ID，直接查影巢
        if tmdb_id:
            result = hdhive.search_by_tmdb(tmdb_id, res_type)
            return result
        
        # 否则用关键词搜索 TMDB 再查影巢
        if not tmdb_client.api_key:
            return {"status": "error", "message": "未配置 TMDB API Key"}

        # 构造搜索关键词：剧名 + 季
        keyword = series_name
        if season:
            keyword += f" S{str(season).zfill(2)}"
        
        try:
            movie_res = tmdb_client.search_movie(keyword, proxies=proxies, timeout=15, page=1)
            tv_res = tmdb_client.search_tv(keyword, proxies=proxies, timeout=15, page=1)

            # 优先使用剧集结果
            first_match = None
            if tv_res.status_code == 200:
                tv_data = tv_res.json()
                if tv_data.get("results"):
                    item = next((i for i in tv_data["results"] if i.get("media_type") == "tv"), tv_data["results"][0])
                    first_match = {"type": "tv", "tmdb_id": item.get("id")}
            
            if not first_match and movie_res.status_code == 200:
                movie_data = movie_res.json()
                if movie_data.get("results"):
                    item = next((i for i in movie_data["results"] if i.get("media_type") == "movie"), movie_data["results"][0])
                    first_match = {"type": "movie", "tmdb_id": item.get("id")}
            
            if not first_match:
                return {"status": "error", "message": "未找到相关资源"}
            
            result = hdhive.search_by_tmdb(first_match["tmdb_id"], first_match["type"])
            return result
            
        except Exception as e:
            logger.error(f"[Gaps影巢搜索] TMDB搜索失败: {e}")
            return {"status": "error", "message": safe_error_message(e, "搜索失败")}

    except Exception as e:
        import logging
        logging.getLogger("uvicorn").error(f"[Gaps影巢搜索] 失败: {e}")
        return {"status": "error", "message": safe_error_message(e)}


@router.post("/download_hdhive")
def download_hdhive_for_gap(request: Request = None, payload: dict = None):
    # 🔒 管理员专用（内部调用时 request 为 None，跳过检查）
    if request and not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    """解锁影巢资源并转存到115"""
    import logging
    logger = logging.getLogger("uvicorn")
    
    slug = payload.get("slug", "") if payload else ""
    folder_cid = payload.get("folder_cid", "") if payload else ""
    logger.info(f"[HDHive download] slug={slug}, folder_cid={folder_cid}, payload={payload}")
    if not slug:
        return {"status": "error", "message": "缺少 slug"}

    try:
        from app.plugins import get_plugin
        hdhive = get_plugin("hdhive")
        if not hdhive or not hdhive.enabled:
            return {"status": "error", "message": "影巢插件未启用"}

        # 调用解锁API
        result = hdhive.unlock(slug, auto_transfer=False)
        if result.get("status") != "success":
            return result

        unlock_data = result.get("data", {})
        url = unlock_data.get("url", "")
        access_code = unlock_data.get("access_code", "")
        title = unlock_data.get("title", "未知资源")

        if not url:
            return {"status": "error", "message": "解锁成功但未获取到链接"}

        # 拼接完整链接
        full_link = url
        if access_code:
            sep = "&" if "?" in url else "?"
            full_link = f"{url}{sep}password={access_code}"

        # 触发115转存（带文件夹选择）
        cloud115 = get_plugin("cloud115")
        if cloud115 and cloud115.enabled:
            config = cloud115._get_config()
            cookie = config.get("cookie", "")

            if not cookie:
                return {"status": "error", "message": "115插件未配置Cookie"}

            folders = cloud115._parse_folders(config)

            if not folders:
                return {"status": "error", "message": "115插件未配置目标文件夹"}

            # 如果指定了folder_cid，使用指定的；否则使用第一个
            target_folder = None
            logger.info(f"[HDHive download] folders={folders}, checking folder_cid={folder_cid}")
            if folder_cid:
                for f in folders:
                    logger.info(f"[HDHive download] comparing: str(f.get('cid'))={str(f.get('cid'))} vs str(folder_cid)={str(folder_cid)}")
                    if str(f.get("cid")) == str(folder_cid):
                        target_folder = f
                        logger.info(f"[HDHive download] matched! target_folder={target_folder}")
                        break

            if not target_folder:
                if len(folders) == 1:
                    target_folder = folders[0]
                else:
                    # 多个文件夹但未指定，返回文件夹列表让前端选择
                    return {"status": "need_folder", "folders": folders, "link": full_link, "title": title}

            # 执行转存（同步执行并返回结果）
            try:
                result = cloud115._do_transfer_sync(full_link, target_folder.get("cid"), target_folder.get("name"), cookie)
                if result.get("status") == "success":
                    return {"status": "success", "message": f"已转存: {title}", "title": title, "folder": target_folder.get("name"), "files": result.get("files", [])}
                else:
                    return {"status": "error", "message": result.get("message", "转存失败")}
            except Exception as e:
                return {"status": "error", "message": safe_error_message(e, "转存异常")}

        return {"status": "success", "message": "解锁成功", "url": url, "access_code": access_code, "title": title}

    except Exception as e:
        import logging
        logging.getLogger("uvicorn").error(f"[Gaps影巢解锁] 失败: {e}")
        return {"status": "error", "message": safe_error_message(e)}


@router.get("/115/folders")
def get_115_folders(request: Request):
    # 🔒 管理员专用
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    """获取115转存文件夹列表"""
    try:
        from app.plugins import get_plugin
        cloud115 = get_plugin("cloud115")
        if not cloud115 or not cloud115.enabled:
            return {"status": "error", "message": "115插件未启用"}

        config = cloud115._get_config()
        folders = cloud115._parse_folders(config)

        return {"status": "success", "data": folders}
    except Exception as e:
        import logging
        logging.getLogger("uvicorn").error(f"[Gaps获取115文件夹] 失败: {e}")
        return {"status": "error", "message": safe_error_message(e)}


# ==================== MP搜索 ====================
@router.post("/search_mp")
def search_mp_for_gap(request: Request = None, payload: dict = None):
    # 🔒 管理员专用（内部调用时 request 为 None，跳过检查）
    if request and not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    series_id = payload.get("series_id") if payload else None
    series_name = payload.get("series_name") if payload else None
    season = payload.get("season") if payload else None
    episodes = payload.get("episodes", []) if payload else []
    mp_url = cfg.get("moviepilot_url"); mp_token = cfg.get("moviepilot_token")
    if not mp_url or not mp_token: return {"status": "error", "message": "未配置 MP"}
    
    logger.info(f"[缺集搜索] 开始MP搜索: {series_name} S{season}E{episodes}")
    
    # 将目标集数转为整数集合
    target_episodes = set([int(e) for e in episodes])
    
    admin_id = get_admin_user_id(); genes = []
    if admin_id:
        try:
            # 🚀 替换为 media_api
            items = media_api.get(f"/Users/{admin_id}/Items", params={"ParentId":series_id,"IncludeItemTypes":"Episode","Recursive":"true","Limit":1,"Fields":"MediaSources"}, timeout=5).json().get("Items", [])
            if items and items[0].get("MediaSources"):
                v = next((s for s in items[0]["MediaSources"][0].get("MediaStreams", []) if s.get("Type") == "Video"), None)
                if v:
                    if v.get("Width", 0) >= 3800: genes.append("4K")
                    elif v.get("Width", 0) >= 1900: genes.append("1080P")
                    if "HDR" in v.get("VideoRange", "") or "HDR" in v.get("DisplayTitle", "").upper(): genes.append("HDR")
                    if "DOVI" in v.get("DisplayTitle", "").upper() or "DOLBY VISION" in v.get("DisplayTitle", "").upper(): genes.append("DoVi")
        except Exception: pass
    if not genes: genes = ["无明显特效"]
    
    def deep_extract(d, keys):
        for k in keys:
            if d.get(k) is not None and str(d.get(k)).strip() != "": return d.get(k)
        for n in ["torrent", "torrent_info", "detail", "data", "info"]:
            if isinstance(d.get(n), dict):
                for k in keys:
                    if d[n].get(k) is not None and str(d[n].get(k)).strip() != "": return d[n].get(k)
        return None

    try:
        results = []; is_pack = False
        # 先搜单集关键词
        if len(episodes) == 1:
            kw = f"{series_name} S{str(season).zfill(2)}E{str(episodes[0]).zfill(2)}"
            res_data = moviepilot_client.search_title(mp_url, mp_token, kw, timeout=20).json()
            if isinstance(res_data, dict): res_data = res_data.get("data") or res_data.get("results") or []
            if isinstance(res_data, list): results = res_data
        
        # 如果没结果，搜整季关键词
        if len(results) == 0:
            kw2 = f"{series_name} S{str(season).zfill(2)}"
            res_data2 = moviepilot_client.search_title(mp_url, mp_token, kw2, timeout=20).json()
            if isinstance(res_data2, dict): res_data2 = res_data2.get("data") or res_data2.get("results") or []
            if isinstance(res_data2, list): results = res_data2; is_pack = True

        processed = []
        for r in results:
            score = 0
            title = str(deep_extract(r, ["name", "title", "torrent_name"]) or "未提取到种名")
            desc = str(deep_extract(r, ["description", "desc", "detail", "subtitle"]) or "")
            text = (title + " " + desc).upper()
            size_val = deep_extract(r, ["size", "enclosure_size", "torrent_size"]) or 0
            site_val = deep_extract(r, ["site_name", "site", "indexer"]) or "未知站点"
            seeders_val = deep_extract(r, ["seeders", "seeder"]) or 0

            # 🔥 关键修复：从标题提取集数并匹配目标集数
            extracted_eps = extract_episodes_from_filename(title)
            if desc:
                # 也从描述中提取集数（可能包含文件列表）
                extracted_eps.update(extract_episodes_from_filename(desc))
            
            # 计算集数匹配得分（最高权重）
            episode_match_score = 0
            matched_episodes = set()
            if extracted_eps and target_episodes:
                # 检查是否有交集
                matched_episodes = extracted_eps & target_episodes
                match_ratio = len(matched_episodes) / len(target_episodes) if target_episodes else 0
                
                if match_ratio == 1.0:
                    # 完全匹配所有目标集数
                    episode_match_score = 100
                    # 单集种子优先（比整季包高）
                    if len(extracted_eps) == len(target_episodes):
                        episode_match_score = 120  # 精确单集
                elif match_ratio >= 0.5:
                    # 至少匹配一半
                    episode_match_score = int(match_ratio * 80)
                elif match_ratio > 0:
                    # 部分匹配
                    episode_match_score = int(match_ratio * 40)
                else:
                    # 不匹配目标集数，大幅扣分
                    episode_match_score = -50
            
            score += episode_match_score
            
            # 保存提取的集数信息
            r["ui_extracted_episodes"] = sorted(list(extracted_eps)) if extracted_eps else []
            r["ui_matched_episodes"] = sorted(list(matched_episodes)) if matched_episodes else []
            r["ui_episode_match_ratio"] = round(len(matched_episodes) / len(target_episodes) * 100, 1) if target_episodes else 0

            # 提取折扣信息 (使用 MP 完整字段: volume_factor, freedate, free)
            volume_factor = deep_extract(r, ["volume_factor", "free", "is_free", "free_status", "freebie"]) or "1.0"
            freedate = deep_extract(r, ["freedate", "free_time"]) or None

            # 处理 volume_factor (如 "0.0" = 免费, "1.0" = 正常, "0.5" = 半价)
            try:
                vf = float(str(volume_factor).strip())
            except:
                vf = 1.0

            is_free = False
            if vf == 0 or str(volume_factor).lower() in ["0", "0.0", "free", "freebie", "true", "yes"]:
                is_free = True
                r["ui_free"] = True
                r["ui_discount"] = "免费"
                r["ui_discount_pct"] = 0
                score += 15
            elif vf > 0 and vf < 1:
                r["ui_free"] = False
                # 转换为百分比显示 (0.5 -> 50%)
                pct = int(vf * 100)
                r["ui_discount"] = f"{pct}%"
                r["ui_discount_pct"] = pct
                score += int((1 - vf) * 20)
            else:
                r["ui_free"] = False
                r["ui_discount_pct"] = 100
                if freedate:
                    r["ui_discount"] = "限时免费"
                else:
                    r["ui_discount"] = None

            # 提取 H&R (Hit and Run)
            hit_and_run = deep_extract(r, ["hit_and_run", "hr", "hit_and_run"])
            hnr_str = str(hit_and_run).lower() if hit_and_run else ""
            r["ui_hnr"] = hnr_str in ["1", "true", "yes", "hr", "1.0", "0"]
            if r["ui_hnr"]:
                score -= 10  # H&R 扣分

            # 🔥 改进的分辨率提取：优先使用 MP 字段，再从标题提取
            resolution = ""
            # 1. 尝试从 MP 字段获取
            res_field = deep_extract(r, ["resolution", "video_resolution", "resolution_term", "quality"])
            if res_field:
                resolution = str(res_field)
            
            # 2. 从标题提取分辨率
            if not resolution:
                if "2160P" in text or "4K" in text or "UHD" in text:
                    resolution = "4K/2160P"
                elif "1080P" in text or "1080I" in text or "FHD" in text:
                    resolution = "1080P"
                elif "720P" in text or "HD" in text:
                    resolution = "720P"
                elif "480P" in text or "SD" in text:
                    resolution = "480P"
            
            r["ui_resolution"] = resolution

            # 提取质量/资源标签 (从字段或从标题中提取)
            resource_term = deep_extract(r, ["resource_term", "quality", "resource"]) or ""
            if not resource_term:
                # 从标题中提取常见质量标识
                if "REMUX" in text:
                    resource_term = "REMUX"
                elif "BluRay" in text or "BLURAY" in text:
                    resource_term = "BluRay"
                elif "WEB-DL" in text or "WEBDL" in text:
                    resource_term = "WEB-DL"
                elif "HDTV" in text:
                    resource_term = "HDTV"
                elif "DVD" in text:
                    resource_term = "DVD"
            r["ui_resource"] = str(resource_term) if resource_term else None

            # 提取标签
            labels = deep_extract(r, ["labels", "tags", "category"]) or []
            if isinstance(labels, str):
                labels = [l.strip() for l in labels.split(",") if l.strip()]
            r["ui_labels"] = labels[:5] if labels else []  # 限制5个标签

            # 提取中文备注
            r["ui_desc"] = desc[:200] if desc else ""  # 限制长度

            # 检测国语和中字
            has_chinese_audio = False
            has_chinese_sub = False
            full_text = title + " " + desc

            # 国语检测
            if any(kw in full_text for kw in ["国语", "普通话", "国配", "中文配音", "配音"]):
                has_chinese_audio = True
                score += 5
            # 中字检测
            if any(kw in full_text for kw in ["中字", "中字幕", "简体", "繁体", "SRT", "chs", "cht", "gb", "big5"]):
                has_chinese_sub = True
                score += 5

            r["ui_chinese_audio"] = has_chinese_audio
            r["ui_chinese_sub"] = has_chinese_sub

            # 分辨率评分（次要权重）
            if "4K" in resolution or "2160P" in resolution:
                score += 30
            elif "1080P" in resolution:
                score += 25
            elif "720P" in resolution:
                score += 10
            
            # 特殊格式加分
            if "DoVi" in text or "VISION" in text or "DOLBY VISION" in text: score += 20
            if "HDR" in text or "HDR10" in text: score += 15
            if "REMUX" in text: score += 10

            r["ui_title"] = title; r["ui_site"] = str(site_val)
            try: r["ui_size"] = float(size_val)
            except: r["ui_size"] = 0
            try: r["ui_seeders"] = int(seeders_val)
            except: r["ui_seeders"] = 0

            r["match_score"] = score
            r["is_pack"] = is_pack or len(extracted_eps) > 1  # 多集资源标记为包
            r["org_payload"] = r.get("torrent_info", r)

            # 提取显示标签
            tags = []
            if resolution: tags.append(resolution)
            if resource_term: tags.append(resource_term)
            if "DOVI" in text or "VISION" in text: tags.append("DoVi")
            elif "HDR" in text: tags.append("HDR")
            # 检测编码
            if "H.265" in text or "HEVC" in text: tags.append("HEVC")
            elif "H.264" in text or "AVC" in text: tags.append("AVC")
            elif "X265" in text: tags.append("X265")
            elif "X264" in text: tags.append("X264")
            r["extracted_tags"] = tags

            processed.append(r)

        # 按匹配得分排序
        processed.sort(key=lambda x: x["match_score"], reverse=True)
        logger.info(f"[缺集搜索] MP搜索完成: 找到 {len(processed)} 个资源，返回前10个")
        return {"status": "success", "data": {"genes": genes, "results": processed[:10]}}
    except Exception as e: 
        logger.error(f"[缺集搜索] MP搜索异常: {e}")
        return {"status": "error", "message": safe_error_message(e)}

def extract_episodes_from_filename(filename: str) -> set:
    """从文件名中提取集数，支持多种命名格式"""
    eps = set()
    fname = filename.upper()
    
    # 1. S01E05 或 S01E05-E08 格式
    s_e = re.findall(r'S\d{1,2}E(\d{1,3})(?:-E?(\d{1,3}))?', fname)
    for e1, e2 in s_e:
        eps.add(int(e1))
        if e2: eps.update(range(int(e1), int(e2)+1))
    
    # 2. EP05 或 E05 或 EPISODE 05 格式
    ep = re.findall(r'(?:EPISODE|EP|E)[\s\.\-]*(\d{1,3})(?:-E?(\d{1,3}))?', fname)
    for e1, e2 in ep:
        eps.add(int(e1))
        if e2: eps.update(range(int(e1), int(e2)+1))
    
    # 3. 中文格式：第5集 或 第5-10集
    zh = re.findall(r'第\s*(\d{1,3})\s*(?:-|至|到)\s*(\d{1,3})\s*集', filename)
    for e1, e2 in zh:
        eps.update(range(int(e1), int(e2)+1))
    zh_single = re.findall(r'第\s*(\d{1,3})\s*集', filename)
    for e in zh_single: eps.add(int(e))
    
    # 4. 纯数字格式：[05] 或 .05. 或 -05-（需要排除分辨率等干扰数字）
    if not eps:
        naked = re.findall(r'(?:\[|\s-?\s|\.)(\d{2,4})(?:\]|\s|\.)', fname)
        for e in naked:
            num = int(e)
            # 排除分辨率、年份、编码格式
            if num not in (480, 720, 1080, 2160, 264, 265, 2020, 2021, 2022, 2023, 2024, 2025, 2026, 2027):
                eps.add(num)
    
    # 5. 最后尝试：文件名开头或结尾的纯数字（如 01.mkv）
    if not eps:
        # 匹配文件名开头数字：01.xxx 或 01-02.xxx
        prefix = re.match(r'^(\d{1,3})(?:-(\d{1,3}))?\s*[\.\[]', filename)
        if prefix:
            eps.add(int(prefix.group(1)))
            if prefix.group(2):
                eps.update(range(int(prefix.group(1)), int(prefix.group(2))+1))
    
    return eps

def hook_qbittorrent(host, user, password, expected_size, target_episodes, torrent_name=None):
    """
    qBittorrent 截胡功能
    :param host: QB WebUI 地址
    :param user: 用户名
    :param password: 密码
    :param expected_size: 预期种子大小（字节）
    :param target_episodes: 目标集数列表
    :param torrent_name: 种子名称关键词（用于辅助匹配）
    """
    import logging
    logger = logging.getLogger("uvicorn")
    try:
        s = qbittorrent_client.create_session()
        login = qbittorrent_client.login(s, host, user, password, timeout=10)
        if login.status_code != 200 or "Ok" not in login.text:
            logger.error(f"[QB截胡] 登录失败: status={login.status_code}, response={login.text[:100]}")
            return False, "qBittorrent 登录失败"
        
        target_hash = None
        target_torrent = None
        match_method = None
        logger.info(f"[QB截胡] 开始轮询，expected_size={expected_size}, target_episodes={target_episodes}, torrent_name={torrent_name}")
        
        for attempt in range(20):
            time.sleep(3)
            res = qbittorrent_client.list_torrents(s, host, timeout=10)
            if res.status_code != 200:
                logger.warning(f"[QB截胡] 获取种子列表失败: status={res.status_code}")
                continue
                
            torrents = res.json()
            logger.debug(f"[QB截胡] 第 {attempt+1} 次轮询，找到 {len(torrents)} 个种子")
            
            for t in torrents:
                age = time.time() - t.get("added_on", 0)
                if age > 300: continue  # 只看5分钟内添加的
                
                t_size = t.get("total_size", 0)
                t_name = t.get("name", "")
                t_hash = t.get("hash", "")
                
                # 优先级1：大小精确匹配（容差 100MB）
                if expected_size > 0 and abs(t_size - expected_size) < 100 * 1024 * 1024:
                    target_hash = t_hash
                    target_torrent = t
                    match_method = "大小匹配"
                    logger.info(f"[QB截胡] 大小匹配成功: {t_name}, size={t_size}, expected={expected_size}, diff={abs(t_size-expected_size)/1024/1024:.1f}MB")
                    break
                
                # 优先级2：名称关键词匹配（如果提供了种子名称）
                if torrent_name and torrent_name.lower() in t_name.lower():
                    target_hash = t_hash
                    target_torrent = t
                    match_method = "名称匹配"
                    logger.info(f"[QB截胡] 名称匹配成功: {t_name}, 关键词={torrent_name}")
                    break
            
            if target_hash:
                break
            
            # 优先级3：如果没有精确匹配，取最新添加的种子（expected_size=0 时的回退策略）
            if expected_size == 0 and torrents:
                for t in torrents:
                    age = time.time() - t.get("added_on", 0)
                    if age <= 300:
                        target_hash = t.get("hash")
                        target_torrent = t
                        match_method = "最新种子"
                        logger.info(f"[QB截胡] 回退到最新种子: {t.get('name')}, age={int(age)}s")
                        break
                if target_hash:
                    break
        
        if not target_hash:
            return False, "轮询 60 秒超时：未找到匹配的种子"
        
        # 获取文件列表
        f_res = qbittorrent_client.list_files(s, host, target_hash, timeout=10)
        if f_res.status_code != 200:
            logger.error(f"[QB截胡] 获取文件列表失败: status={f_res.status_code}")
            return False, f"获取种子文件列表失败 (HTTP {f_res.status_code})"
        
        files = f_res.json()
        if not files:
            return False, "种子文件列表为空"
        
        logger.info(f"[QB截胡] 种子 '{target_torrent.get('name')}' 包含 {len(files)} 个文件")
        
        # 单文件种子
        if len(files) == 1:
            fname = files[0].get("name", "")
            logger.info(f"[QB截胡] 单文件种子: {fname}")
            return True, f"📦 单文件种子，无需截胡"
        
        # 多文件种子：识别集数
        wanted, unwanted, wanted_names, unwanted_names = [], [], [], []
        video_extensions = ('.mp4', '.mkv', '.avi', '.ts', '.iso', '.wmv', '.flv', '.m2ts', '.vob')
        
        for i, f in enumerate(files):
            fname = f.get("name", "")
            f_progress = f.get("progress", 0)
            
            # 非视频文件直接跳过下载
            if not fname.lower().endswith(video_extensions):
                unwanted.append(str(i))
                unwanted_names.append(fname)
                logger.debug(f"[QB截胡] 跳过非视频文件: {fname}")
                continue
            
            # 提取集数
            f_eps = extract_episodes_from_filename(fname)
            logger.debug(f"[QB截胡] 文件 '{fname}' 识别集数: {f_eps}")
            
            is_wanted = any(e in target_episodes for e in f_eps)
            if is_wanted:
                wanted.append(str(i))
                wanted_names.append(f"{fname} (集数:{f_eps})")
            else:
                unwanted.append(str(i))
                unwanted_names.append(f"{fname} (集数:{f_eps})")
        
        logger.info(f"[QB截胡] 匹配结果: wanted={len(wanted)}, unwanted={len(unwanted)}")
        logger.info(f"[QB截胡] 想要的文件: {wanted_names}")
        logger.info(f"[QB截胡] 不想要的文件: {unwanted_names}")
        
        # 没有识别出任何想要的集数
        if not wanted:
            logger.warning(f"[QB截胡] 未能识别出目标集数，target_episodes={target_episodes}")
            return False, "⚠️ 未能识别出目标集数，为防止误删已放行全包下载"
        
        # 没有不想要的文件（全部都要）
        if not unwanted:
            return True, f"✅ 种子内所有 {len(wanted)} 个视频文件均为目标集数，无需截胡"
        
        # 执行截胡：设置文件优先级
        # 注意：priority=0 表示"不下载"，priority=1 表示"正常下载"
        try:
            if unwanted:
                prio_res = qbittorrent_client.set_file_priority(
                    s, host, target_hash, "|".join(unwanted), 0, timeout=10
                )
                logger.info(f"[QB截胡] 设置不下载文件: {unwanted}, 响应: {prio_res.status_code}")
            
            if wanted:
                prio_res = qbittorrent_client.set_file_priority(
                    s, host, target_hash, "|".join(wanted), 1, timeout=10
                )
                logger.info(f"[QB截胡] 设置下载文件: {wanted}, 响应: {prio_res.status_code}")
            
            return True, f"🔪 截胡成功！保留 {len(wanted)} 个目标文件，跳过 {len(unwanted)} 个多余文件"
            
        except Exception as e:
            logger.error(f"[QB截胡] 设置文件优先级失败: {e}")
            return False, safe_error_message(e, "设置文件优先级失败")
            
    except qbittorrent_client.Timeout:
        logger.error("[QB截胡] 连接超时")
        return False, "qBittorrent 连接超时，请检查网络"
    except qbittorrent_client.ConnectionError:
        logger.error("[QB截胡] 连接失败")
        return False, "qBittorrent 连接失败，请检查地址是否正确"
    except Exception as e:
        logger.error(f"[QB截胡] 异常: {e}", exc_info=True)
        return False, safe_error_message(e, "qB 交互异常")

def hook_transmission(host, user, password, expected_size, target_episodes):
    try:
        auth = (user, password) if user else None
        s = transmission_client.create_session()
        res = transmission_client.handshake(s, host, auth=auth, timeout=10)
        session_id = res.headers.get('X-Transmission-Session-Id')
        if not session_id: return False, "Transmission 认证失败"
        s.headers.update({'X-Transmission-Session-Id': session_id})
        target_id = None
        for attempt in range(20):
            time.sleep(3)
            payload = {"method": "torrent-get", "arguments": {"fields": ["id", "addedDate", "totalSize", "files"]}}
            r = transmission_client.torrent_get(s, host, payload, auth=auth, timeout=10)
            if r.status_code == 200:
                torrents = r.json().get("arguments", {}).get("torrents", [])
                for t in torrents:
                    if time.time() - t.get("addedDate", 0) < 300:
                        if expected_size > 0 and abs(t.get("totalSize", 0) - expected_size) < 10 * 1024 * 1024:
                            target_id = t.get("id"); files = t.get("files", []); break
            if target_id and files and len(files) > 0 and files[0].get("length", 0) > 0:
                wanted, unwanted = [], []
                for i, f in enumerate(files):
                    fname = f.get("name", "")
                    if not fname.lower().endswith(('.mp4', '.mkv', '.avi', '.ts', '.iso')):
                        unwanted.append(i); continue
                    f_eps = extract_episodes_from_filename(fname)
                    if any(e in target_episodes for e in f_eps): wanted.append(i)
                    else: unwanted.append(i)
                if not wanted: return False, "⚠️ 正则未匹配到视频集数，为防止误杀，已放行全包下载"
                set_payload = {"method": "torrent-set", "arguments": {"id": target_id}}
                if unwanted: set_payload["arguments"]["files-unwanted"] = unwanted
                if wanted: set_payload["arguments"]["files-wanted"] = wanted
                transmission_client.torrent_get(s, host, set_payload, auth=auth, timeout=10)
                return True, f"🔪 TR 截胡成功！保留 {len(wanted)} 集，剔除 {len(unwanted)} 个文件"
        return False, "轮询 60 秒超时：未锁定种子"
    except Exception as e: return False, safe_error_message(e, "TR 交互异常")

@router.post("/download")
def download_gap_item(request: Request = None, payload: dict = None):
    # 🔒 管理员专用（内部调用时 request 为 None，跳过检查）
    if request and not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    series_id = payload.get("series_id") if payload else None
    series_name = payload.get("series_name") if payload else None
    season = payload.get("season") if payload else None
    episodes = payload.get("episodes", []) if payload else []
    torrent_info = payload.get("torrent_info", {}) if payload else {}

    mp_url = cfg.get("moviepilot_url"); mp_token = cfg.get("moviepilot_token")
    ui_conf = get_gap_config_map()
    
    client_type = ui_conf.get("client_type", ""); client_url = ui_conf.get("client_url", "")
    client_user = ui_conf.get("client_user", ""); client_pass = ui_conf.get("client_pass", "")
    
    pure_torrent_in = torrent_info.get("org_payload", torrent_info)
    try: pure_torrent_in["size"] = int(float(pure_torrent_in.get("size", 0)))
    except: pure_torrent_in["size"] = 0
    
    # 提取种子名称用于辅助匹配
    torrent_name = pure_torrent_in.get("title") or pure_torrent_in.get("name") or pure_torrent_in.get("enclosure_name")

    mp_payload = {"torrent_in": pure_torrent_in}

    # 异步执行推送和截胡，立即返回响应
    def download_async():
        import logging
        logger = logging.getLogger("uvicorn")
        try:
            res = moviepilot_client.add_download(mp_url, mp_token, mp_payload, timeout=60)
            if res.status_code in [200, 201]:
                logger.info(f"[缺集下载] MP推送成功: {series_name} S{season}E{episodes}")
                
                # 更新缺集状态为"下载中"
                for ep in episodes:
                    save_gap_record_status(series_id, series_name, int(season), int(ep), 2)
                
                with state_lock:
                    for s in scan_state["results"]:
                        if s.get("series_id") == series_id:
                            for ep_obj in s.get("gaps", []):
                                if ep_obj["season"] == int(season) and ep_obj["episode"] in [int(e) for e in episodes]: ep_obj["status"] = 2
                
                # 执行截胡
                if client_type and client_url and len(episodes) > 0:
                    expected_size = pure_torrent_in.get("size", 0)
                    try:
                        if client_type == "qbittorrent":
                            success, msg = hook_qbittorrent(client_url, client_user, client_pass, expected_size, episodes, torrent_name)
                        elif client_type == "transmission":
                            success, msg = hook_transmission(client_url, client_user, client_pass, expected_size, episodes)
                        logger.info(f"[缺集下载] 截胡完成: success={success}, msg={msg}")
                    except Exception as e:
                        logger.error(f"[缺集下载] 截胡异常: {e}")
            else:
                logger.error(f"[缺集下载] MP推送失败: HTTP {res.status_code}, {res.text[:200]}")
        except Exception as e:
            logger.error(f"[缺集下载] 异步下载异常: {e}")
    
    import threading
    download_thread = threading.Thread(target=download_async, daemon=True)
    download_thread.start()
    
    return {"status": "success", "message": "种子已提交到后台队列，正在处理..."}
