from fastapi import APIRouter, Request
from typing import Optional
from app.domains.playback.stats_queries import build_stats_base_filter, get_playback_column_name, query_stats
from app.utils.proxy_helper import get_safe_proxies  # 🔒 SSRF 安全代理读取
# 🔥 引入核心适配器
from app.infra.clients.media_server_client import media_api
from app.infra.clients.tmdb_client import tmdb_client
from app.infra.config.stats_settings import get_dashboard_cache_ttl
from app.infra.config.user_visibility_settings import get_hidden_users
from app.domains.users.auth import is_admin_user  # 🔒 引入管理员权限检查
import re
import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
import asyncio
from concurrent.futures import ThreadPoolExecutor
import psutil
import time  # 🔥 用于预热缓存时间戳
import copy
import logging
from app.core.security_utils import safe_error_message

logger = logging.getLogger("uvicorn")

router = APIRouter()

# ==================== 🔥 统计数据缓存 ====================
_stats_cache = {
    "overview": {"data": None, "expires": 0},
    "plays": {"data": None, "expires": 0},
    "users": {"data": None, "expires": 0},
}
STATS_CACHE_TTL = 300  # 5 分钟缓存

def get_cached_stats(key: str):
    """获取缓存的统计数据"""
    if key in _stats_cache:
        cache = _stats_cache[key]
        if cache["data"] and time.time() < cache["expires"]:
            return cache["data"]
    return None

def set_cached_stats(key: str, data):
    """设置统计数据缓存"""
    _stats_cache[key] = {
        "data": data,
        "expires": time.time() + STATS_CACHE_TTL
    }

# ==================== 安全检查 ====================

def check_login(request: Request) -> bool:
    """检查用户是否登录（公共API，支持管理端和用户端）"""
    # 管理端登录：session 中有 user
    # 用户端登录：session 中有 req_user
    return request.session.get("user") is not None or request.session.get("req_user") is not None

def check_admin_login(request: Request) -> bool:
    """检查是否为管理员登录（管理API，仅后台管理员）"""
    return is_admin_user(request)

def require_admin_login(request: Request):
    """要求管理员登录"""
    if not check_admin_login(request):
        return {"status": "error", "message": "需要管理员权限"}
    return None

# --- 🧹 智能清洗引擎 ---
def get_clean_name(item_name, item_type):
    if not item_name: return "未知内容"
    item_name = str(item_name)
    if str(item_type) != 'Episode': return item_name.split(' - ')[0]

    parts = [p.strip() for p in item_name.split(' - ')]
    series_name = parts[0]
    season_num = None

    cn_map = {'一':1, '二':2, '三':3, '四':4, '五':5, '六':6, '七':7, '八':8, '九':9, '十':10}

    for part in parts[1:]:
        m1 = re.search(r'(?:S|Season\s*)0*(\d+)', part, re.I)
        if m1: season_num = int(m1.group(1)); break
        m2 = re.search(r'第\s*(\d+)\s*季', part)
        if m2: season_num = int(m2.group(1)); break
        m3 = re.search(r'第\s*([一二三四五六七八九十]+)\s*季', part)
        if m3: season_num = cn_map.get(m3.group(1), 1); break

    if season_num is not None: return f"{series_name} - 第 {season_num} 季"
    m_f1 = re.search(r'(?:S|Season\s*)0*(\d+)', item_name, re.I)
    if m_f1: return f"{series_name} - 第 {int(m_f1.group(1))} 季"
    m_f2 = re.search(r'第\s*([一二三四五六七八九十]+)\s*季', item_name)
    if m_f2: return f"{series_name} - 第 {cn_map.get(m_f2.group(1), 1)} 季"
    m_f3 = re.search(r'第\s*(\d+)\s*季', item_name)
    if m_f3: return f"{series_name} - 第 {int(m_f3.group(1))} 季"

    return series_name

def resolve_poster_ids(items_list):
    if not items_list: return
    ids = ",".join(list(set([str(x['ItemId']) for x in items_list if x.get('ItemId')])))
    if not ids: return
    
    try:
        # 🚀 替换为 media_api
        logger.debug(f"[resolve_poster_ids] 查询 ItemIds: {ids[:100]}...")
        res = media_api.get("/Items", params={"Ids": ids}, timeout=5)
        logger.debug(f"[resolve_poster_ids] 状态码: {res.status_code}")
        if res.status_code == 200:
            emby_items = res.json().get("Items", [])
            logger.debug(f"[resolve_poster_ids] 返回 Items 数量: {len(emby_items)}")
            id_map = {}
            for e in emby_items:
                best_id = e.get("SeriesId") or e.get("SeasonId") or e.get("Id")
                id_map[str(e.get("Id"))] = best_id
            logger.debug(f"[resolve_poster_ids] ID 映射数量: {len(id_map)}")
            for x in items_list:
                orig_id = str(x.get('ItemId'))
                if orig_id in id_map: 
                    # 🔥 不修改原始 ItemId，而是添加 PosterId 用于显示海报
                    x['PosterId'] = id_map[orig_id]
                    x['smart_poster'] = f"/api/proxy/smart_image?item_id={id_map[orig_id]}&type=Primary"
        else:
            logger.warning(f"[resolve_poster_ids] 请求失败: {res.text[:200]}")
    except Exception as e:
        logger.error(f"[resolve_poster_ids] 异常: {e}")

def get_admin_user_id():
    try:
        # 🚀 替换为 media_api
        res = media_api.get("/Users", timeout=5)
        if res.status_code == 200:
            users = res.json()
            for u in users:
                if u.get("Policy", {}).get("IsAdministrator"): return u['Id']
            if users: return users[0]['Id']
    except Exception: pass
    return None

def get_user_map_local():
    user_map = {}
    try:
        # 🚀 替换为 media_api
        res = media_api.get("/Users", timeout=2)
        if res.status_code == 200:
            for u in res.json(): user_map[u['Id']] = u['Name']
    except Exception: pass
    return user_map

@router.get("/api/stats/dashboard")
def api_dashboard(request: Request, user_id: Optional[str] = None):
    # 🔒 安全检查：必须登录
    if not check_login(request):
        return {"status": "error", "message": "请先登录"}

    # 🔒 权限检查：普通用户只能查看自己的数据
    admin_user = request.session.get("user", {})
    req_user = request.session.get("req_user", {})
    is_admin = admin_user.get("auth_type") == "emby" or admin_user.get("role") == "admin"

    if not is_admin:
        if req_user:
            user_id = req_user.get("Id")
        elif admin_user:
            user_id = admin_user.get("id")

    # 🔥 尝试使用缓存（仅全局统计，不缓存特定用户）
    cache_key = f"dashboard_{user_id or 'all'}"
    cached = get_cached_stats(cache_key)
    if cached:
        return cached
    
    try:
        where, params = build_stats_base_filter(user_id)
        plays = query_stats(f"SELECT COUNT(*) as c FROM PlaybackActivity {where}", params)[0]['c']
        # 🔥 时区修复
        users = query_stats(f"SELECT COUNT(DISTINCT UserId) as c FROM PlaybackActivity {where} AND DateCreated > date('now', 'localtime', '-30 days')", params)[0]['c']
        dur = query_stats(f"SELECT SUM(PlayDuration) as c FROM PlaybackActivity {where}", params)[0]['c'] or 0
        base = {"total_plays": plays, "active_users": users, "total_duration": dur}
        lib = {"movie": 0, "series": 0, "episode": 0}
        
        try:
            # 🚀 替换为 media_api
            res = media_api.get("/Items/Counts", timeout=5)
            if res.status_code == 200:
                d = res.json()
                lib = {"movie": d.get("MovieCount", 0), "series": d.get("SeriesCount", 0), "episode": d.get("EpisodeCount", 0)}
        except Exception: pass
        
        result = {"status": "success", "data": {**base, "library": lib}}
        # 🔥 缓存结果
        set_cached_stats(cache_key, result)
        return result
    except: return {"status": "error", "data": {"total_plays":0, "library": {}}}

@router.get("/api/stats/libraries")
def api_get_libraries(request: Request):
    """获取媒体库列表（管理员显示所有媒体库）"""
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    try:
        # 🔥 管理员登录后显示所有媒体库（使用 /Library/VirtualFolders）
        lib_res = media_api.get("/Library/VirtualFolders", timeout=10)
        if lib_res.status_code != 200:
            return {"status": "error", "message": "获取媒体库失败"}
        
        libraries = []
        for lib in lib_res.json():
            item_id = lib.get("ItemId") or lib.get("Guid") or lib.get("Id")
            
            # 获取图片标签
            image_tag = ""
            if item_id:
                try:
                    admin_id = get_admin_user_id()
                    if admin_id:
                        item_res = media_api.get(f"/Users/{admin_id}/Items/{item_id}", timeout=3)
                        if item_res.status_code == 200:
                            item_data = item_res.json()
                            image_tag = item_data.get("ImageTags", {}).get("Primary", "")[:8] if item_data.get("ImageTags", {}).get("Primary") else ""
                except:
                    pass
            
            lib_info = {
                "Id": item_id,
                "Name": lib.get("Name", "未命名"),
                "CollectionType": lib.get("CollectionType", "unknown"),
                "ImageTag": image_tag
            }
            libraries.append(lib_info)
        
        return {"status": "success", "data": libraries}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

@router.get("/api/stats/recent")
def api_recent_activity(request: Request, user_id: Optional[str] = None):
    # 🔒 安全检查
    if not check_login(request):
        return {"status": "error", "message": "请先登录"}

    # 🔒 权限检查：普通用户只能查看自己的数据
    admin_user = request.session.get("user", {})
    req_user = request.session.get("req_user", {})
    is_admin = admin_user.get("auth_type") == "emby" or admin_user.get("role") == "admin"

    if not is_admin:
        if req_user:
            user_id = req_user.get("Id")
        elif admin_user:
            user_id = admin_user.get("id")

    try:
        where, params = build_stats_base_filter(user_id)
        results = query_stats(f"SELECT DateCreated, UserId, ItemId, ItemName, ItemType FROM PlaybackActivity {where} ORDER BY DateCreated DESC LIMIT 50", params)
        if not results: return {"status": "success", "data": []}
        user_map = get_user_map_local()
        
        # 🔥 批量获取 ImageTag（减少 API 调用）
        item_ids = [row['ItemId'] for row in results]
        image_tags = {}
        if item_ids:
            try:
                # 批量查询 Emby 获取 ImageTags
                res = media_api.get("/Items", params={
                    "Ids": ",".join(item_ids[:50]),  # 最多50个
                    "Fields": "ImageTags"
                }, timeout=5)
                if res.status_code == 200:
                    for item in res.json().get("Items", []):
                        tag = item.get("ImageTags", {}).get("Primary", "")
                        if tag:
                            image_tags[item.get("Id")] = tag[:8]
            except:
                pass
        
        data = []
        for row in results:
            item = dict(row)
            item['UserName'] = user_map.get(item['UserId'], "User")
            item['DisplayName'] = item.get('ItemName') or '未知记录'
            item['ImageTag'] = image_tags.get(item['ItemId'], "")  # 🔥 添加 ImageTag
            if not is_admin:
                item.pop('UserId', None)  # 🔒 非管理员不暴露原始 UserId
            data.append(item)
        return {"status": "success", "data": data}
    except: return {"status": "error", "data": []}

@router.get("/api/stats/latest")
def api_latest_media(request: Request = None, limit: int = 60):
    # 🔒 安全检查（内部调用时 request 为 None，跳过检查）
    if request and not check_login(request):
        return {"status": "error", "message": "请先登录"}
    """获取最近入库资源 - 封面优先 TMDB 公网 URL"""
    try:
        # 🔥 管理员登录后显示所有最近入库（使用管理员ID）
        user_id = get_admin_user_id()
        if not user_id:
            return {"status": "error", "data": []}
        
        params = {
            "SortBy": "DateCreated", "SortOrder": "Descending",
            "IncludeItemTypes": "Movie,Episode", "Recursive": "true",
            "Limit": 500, "Fields": "ProductionYear,SeriesName,SeriesId,ParentIndexNumber,IndexNumber,DateCreated,Overview,ImageTags,ProviderIds"
        }
        res = media_api.get(f"/Users/{user_id}/Items", params=params, timeout=15)
        if res.status_code != 200: return {"status": "error", "data": []}

        items_raw = res.json().get("Items", [])
        data = []; seen_series = {}
        proxies = get_safe_proxies()
        
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
                    r = tmdb_client.get_movie_details(tmdb_id, proxies=proxies, timeout=8)
                else:
                    r = tmdb_client.get_tv_details(tmdb_id, proxies=proxies, timeout=8)
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
        
        from concurrent.futures import ThreadPoolExecutor, as_completed
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

@router.get("/api/stats/live")
def api_live_sessions(request: Request):
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    try:
        # 🚀 替换为 media_api
        res = media_api.get("/Sessions", timeout=5)
        if res.status_code == 200: return {"status": "success", "data": [s for s in res.json() if s.get("NowPlayingItem")]}
    except Exception: pass
    return {"status": "success", "data": []}

@router.get("/api/live")
def api_live_sessions_legacy(request: Request):
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    return api_live_sessions(request)

@router.get("/api/stats/top_movies")
def api_top_movies(request: Request = None, user_id: Optional[str] = None, category: str = 'all', sort_by: str = 'count', exclude_types: Optional[str] = None, period: str = 'all'):
    # 🔒 安全检查（内部调用时 request 为 None，跳过检查）
    if request and not check_login(request):
        return {"status": "error", "message": "请先登录"}
    
    # 🔒 权限检查：普通用户只能查看自己的数据
    if request:
        admin_user = request.session.get("user", {})
        req_user = request.session.get("req_user", {})
        is_admin = admin_user.get("auth_type") == "emby" or admin_user.get("role") == "admin"
        
        if not is_admin:
            if req_user:
                user_id = req_user.get("Id")
            elif admin_user:
                user_id = admin_user.get("id")
    
    """
    获取播放排行
    
    Args:
        user_id: 用户ID，'all' 表示全服
        category: 类型过滤，'all'/'Movie'/'Episode'
        sort_by: 排序方式，'count' 按播放量，'time' 按时长
        exclude_types: 排除的媒体类型，逗号分隔，如 'Audio,MusicVideo'
        period: 时间维度，'today'/'week'/'month'/'quarter'/'year'/'all'
    """
    try:
        where, params = build_stats_base_filter(user_id)
        
        # 🔥 时间维度筛选 - 使用 SQLite 原生日期函数确保时区一致
        if period == 'today':
            where += " AND DateCreated >= date('now', 'localtime', 'start of day')"
        elif period == 'week':
            where += " AND DateCreated >= date('now', 'localtime', '-7 days')"
        elif period == 'month':
            where += " AND DateCreated >= date('now', 'localtime', 'start of month')"
        elif period == 'quarter':
            # SQLite 没有季度函数，使用 Python 计算
            now = datetime.datetime.now()
            quarter_month = ((now.month - 1) // 3) * 3 + 1
            quarter_start = now.replace(month=quarter_month, day=1, hour=0, minute=0, second=0, microsecond=0)
            where += " AND DateCreated >= ?"
            params.append(quarter_start.strftime('%Y-%m-%d'))
        elif period == 'year':
            where += " AND DateCreated >= date('now', 'localtime', 'start of year')"
        
        if category == 'Movie': where += " AND ItemType = 'Movie'"
        elif category == 'Episode': where += " AND ItemType = 'Episode'"
        
        # 排除指定媒体类型
        if exclude_types:
            excluded = [t.strip() for t in exclude_types.split(',') if t.strip()]
            if excluded:
                placeholders = ','.join(['?' for _ in excluded])
                where += f" AND ItemType NOT IN ({placeholders})"
                params.extend(excluded)  # params 是列表，用 extend
        
        sql = f"SELECT ItemName, ItemId, ItemType, PlayDuration FROM PlaybackActivity {where} LIMIT 5000"
        logger.debug(f"[api_top_movies] SQL: {sql}, params: {params}")
        rows = query_stats(sql, params)
        logger.debug(f"[api_top_movies] 查询结果数量: {len(rows) if rows else 0}")
        
        aggregated = {}
        if rows:
            for row in rows:
                row_dict = dict(row)
                clean = get_clean_name(row_dict.get('ItemName'), row_dict.get('ItemType', ''))
                if clean not in aggregated: aggregated[clean] = {'ItemName': clean, 'ItemId': row_dict['ItemId'], 'PlayCount': 0, 'TotalTime': 0}
                aggregated[clean]['PlayCount'] += 1; aggregated[clean]['TotalTime'] += (row_dict['PlayDuration'] or 0)
        
        logger.debug(f"[api_top_movies] 聚合后数量: {len(aggregated)}")
        
        res = list(aggregated.values())
        res.sort(key=lambda x: x['TotalTime'] if sort_by == 'time' else x['PlayCount'], reverse=True)
        top_50 = res[:50]
        
        # 🔥 打印 resolve_poster_ids 调用前的 ItemIds
        logger.debug(f"[api_top_movies] resolve_poster_ids 调用前 ItemIds: {[x['ItemId'] for x in top_50[:5]]}")
        resolve_poster_ids(top_50) 
        logger.debug(f"[api_top_movies] resolve_poster_ids 调用后 ItemIds: {[x['ItemId'] for x in top_50[:5]]}")
        
        logger.debug(f"[api_top_movies] 最终返回: {len(top_50)} 条")
        return {"status": "success", "data": top_50}
    except Exception as e:
        logger.error(f"[api_top_movies] 异常: {e}")
        return {"status": "error", "data": []}


@router.get("/api/stats/user_details")
def api_user_details(request: Request, user_id: Optional[str] = None):
    # 🔒 安全检查
    if not check_login(request):
        return {"status": "error", "message": "请先登录"}
    
    # 🔒 权限检查：普通用户只能查看自己的数据
    admin_user = request.session.get("user", {})
    req_user = request.session.get("req_user", {})
    is_admin = admin_user.get("auth_type") == "emby" or admin_user.get("role") == "admin"
    
    # 如果不是管理员，强制只能查看自己的数据
    if not is_admin:
        if req_user:
            user_id = req_user.get("Id")
        elif admin_user:
            user_id = admin_user.get("id")
    
    try:
        where, params = build_stats_base_filter(user_id)
        client_col = get_playback_column_name()
        
        # 🔥 动态检测可用列
        available_cols = ["DateCreated", "ItemName", "ItemId", "PlayDuration", "UserId"]
        try:
            test_sql = "SELECT * FROM PlaybackActivity LIMIT 1"
            test_res = query_stats(test_sql, [])
            if test_res and len(test_res) > 0:
                first_row = test_res[0]
                if hasattr(first_row, 'keys'):
                    available_cols = list(first_row.keys())
                elif isinstance(first_row, dict):
                    available_cols = list(first_row.keys())
        except:
            pass
        
        # 构建查询字段（只使用存在的列）
        select_fields = ["DateCreated", "ItemName", "ItemId", "PlayDuration", "UserId"]
        if "ItemType" in available_cols:
            select_fields.append("ItemType")
        if "DeviceName" in available_cols:
            select_fields.append("COALESCE(DeviceName, 'Unknown') as Device")
        if client_col in available_cols or client_col.lower() in [c.lower() for c in available_cols]:
            select_fields.append(f"COALESCE({client_col}, 'Unknown') as Client")
        
        # 🚀 性能优化：合并多次查询为一次大查询
        all_data_sql = f"""
            SELECT {', '.join(select_fields)} FROM PlaybackActivity {where} 
            ORDER BY DateCreated DESC
        """
        all_rows = query_stats(all_data_sql, params)
        
        # 从内存中聚合数据
        h_data = {str(i).zfill(2): 0 for i in range(24)}
        devices_map = {}
        clients_map = {}
        logs = []
        pref = {"movie_plays": 0, "episode_plays": 0}
        agg_fav = {}
        total_plays = 0
        total_duration = 0
        
        # 用户映射（只查一次）
        u_map = get_user_map_local()
        
        # 限制处理的记录数，提高性能
        max_logs = 100
        processed = 0
        
        if all_rows:
            for row in all_rows:
                r = dict(row)
                total_plays += 1
                dur = r.get('PlayDuration') or 0
                total_duration += dur
                
                # 小时分布
                dc = r.get('DateCreated')
                if dc:
                    m = re.search(r'(\d{4})-(\d{2})-(\d{2})[T\s](\d{2}):(\d{2}):(\d{2})', str(dc))
                    if m:
                        hour = m.group(4)
                        h_data[hour] += 1
                
                # 设备分布（前10）
                device = r.get('Device') or 'Unknown'
                devices_map[device] = devices_map.get(device, 0) + 1
                
                # 客户端分布（前10）
                client = r.get('Client') or 'Unknown'
                clients_map[client] = clients_map.get(client, 0) + 1
                
                # 最近记录（前100条）
                if processed < max_logs:
                    l = {
                        'DateCreated': dc,
                        'ItemName': r.get('ItemName'),
                        'ItemId': r.get('ItemId'),
                        'ItemType': r.get('ItemType'),
                        'PlayDuration': dur,
                        'Device': r.get('Device'),
                        'UserId': r.get('UserId'),
                        'UserName': u_map.get(r.get('UserId'), "User"),
                        'smart_poster': f"/api/proxy/smart_image?item_id={r.get('ItemId')}&type=Primary"
                    }
                    if not is_admin:
                        l.pop('UserId', None)  # 🔒 非管理员不暴露原始 UserId
                    logs.append(l)
                    processed += 1
                
                # 播放偏好
                item_type = r.get('ItemType')
                if item_type == 'Movie':
                    pref['movie_plays'] += 1
                elif item_type == 'Episode':
                    pref['episode_plays'] += 1
                
                # 最爱内容聚合
                clean = get_clean_name(r.get('ItemName'), item_type or '')
                if clean not in agg_fav:
                    agg_fav[clean] = {"ItemName": clean, "ItemId": r.get("ItemId"), "c": 0, "d": 0}
                agg_fav[clean]["c"] += 1
                agg_fav[clean]["d"] += dur
        
        # 解析海报ID（批量处理最近记录和最爱）
        if logs:
            resolve_poster_ids(logs)
        
        # 设备/客户端排序取前10
        devices = [{"Device": k, "Plays": v} for k, v in sorted(devices_map.items(), key=lambda x: x[1], reverse=True)[:10]]
        clients = [{"Client": k, "Plays": v} for k, v in sorted(clients_map.items(), key=lambda x: x[1], reverse=True)[:10]]
        
        # 概览数据
        overview = {
            "total_plays": total_plays,
            "total_duration": total_duration,
            "avg_duration": round(total_duration / total_plays) if total_plays > 0 else 0,
            "account_age_days": 1
        }
        
        # 最爱内容
        top_fav = max(agg_fav.values(), key=lambda x: x['d']) if agg_fav else None
        if top_fav:
            resolve_poster_ids([top_fav])
        
        # 异步获取账号创建时间（不影响主要数据返回）
        try:
            if user_id and user_id != 'all':
                u_res = media_api.get(f"/Users/{user_id}", timeout=3)
                if u_res.status_code == 200:
                    dc = u_res.json().get("DateCreated")
                    if dc:
                        m = re.search(r'(\d{4})-(\d{2})-(\d{2})', str(dc))
                        if m:
                            fd = datetime.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                            overview['account_age_days'] = max(1, (datetime.datetime.now() - fd).days)
            else:
                u_res = media_api.get("/Users", timeout=3)
                if u_res.status_code == 200:
                    earliest_dt = None
                    for u in u_res.json():
                        dc = u.get("DateCreated")
                        if dc:
                            m = re.search(r'(\d{4})-(\d{2})-(\d{2})', str(dc))
                            if m:
                                dt = datetime.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                                if not earliest_dt or dt < earliest_dt:
                                    earliest_dt = dt
                    if earliest_dt:
                        overview['account_age_days'] = max(1, (datetime.datetime.now() - earliest_dt).days)
        except Exception: pass
                
        return {"status": "success", "data": {
            "hourly": h_data, "devices": devices, "clients": clients, 
            "logs": logs, "overview": overview, "preference": pref, "top_fav": top_fav
        }}
    except Exception as e: 
        return {"status": "error", "data": {"hourly": {}, "devices": [], "clients": [], "logs": []}}

@router.get("/api/stats/chart")
@router.get("/api/stats/trend")
def api_chart_stats(request: Request, user_id: Optional[str] = None, dimension: str = 'day'):
    # 🔒 安全检查
    if not check_login(request):
        return {"status": "error", "message": "请先登录"}
    
    # 🔒 权限检查：普通用户只能查看自己的数据
    admin_user = request.session.get("user", {})
    req_user = request.session.get("req_user", {})
    is_admin = admin_user.get("auth_type") == "emby" or admin_user.get("role") == "admin"
    
    if not is_admin:
        if req_user:
            user_id = req_user.get("Id")
        elif admin_user:
            user_id = admin_user.get("id")
    
    try:
        where, params = build_stats_base_filter(user_id)
        # 🔥 时区修复
        if dimension == 'week': 
            sql = f"SELECT strftime('%Y-%W', substr(replace(DateCreated, 'T', ' '), 1, 19)) as Label, SUM(PlayDuration) as Duration FROM PlaybackActivity {where} AND DateCreated > date('now', 'localtime', '-120 days') GROUP BY Label ORDER BY Label"
        elif dimension == 'month': 
            sql = f"SELECT substr(replace(DateCreated, 'T', ' '), 1, 7) as Label, SUM(PlayDuration) as Duration FROM PlaybackActivity {where} AND DateCreated > date('now', 'localtime', '-365 days') GROUP BY Label ORDER BY Label"
        else: 
            sql = f"SELECT substr(replace(DateCreated, 'T', ' '), 1, 10) as Label, SUM(PlayDuration) as Duration FROM PlaybackActivity {where} AND DateCreated > date('now', 'localtime', '-30 days') GROUP BY Label ORDER BY Label"
            
        results = query_stats(sql, params)
        data = {}
        if results:
            for r in results: data[r['Label']] = int(r['Duration'] or 0)
        return {"status": "success", "data": data}
    except: return {"status": "error", "data": {}}

@router.get("/api/stats/poster_data")
def api_poster_data(request: Request, user_id: Optional[str] = None, period: str = 'all'):
    # 🔒 安全检查
    if not check_login(request):
        return {"status": "error", "message": "请先登录"}

    # 🔒 权限检查：普通用户只能查看自己的数据
    admin_user = request.session.get("user", {})
    req_user = request.session.get("req_user", {})
    is_admin = admin_user.get("auth_type") == "emby" or admin_user.get("role") == "admin"

    if not is_admin:
        if req_user:
            user_id = req_user.get("Id")
        elif admin_user:
            user_id = admin_user.get("id")

    try:
        where_base, params = build_stats_base_filter(user_id)
        date_filter = ""
        # 🔥 时区修复
        if period == 'week': date_filter = " AND DateCreated > date('now', 'localtime', '-7 days')"
        elif period == 'month': date_filter = " AND DateCreated > date('now', 'localtime', '-30 days')"
            
        server_res = query_stats(f"SELECT COUNT(*) as Plays FROM PlaybackActivity {build_stats_base_filter('all')[0]} {date_filter}", build_stats_base_filter('all')[1])
        server_plays = server_res[0]['Plays'] if server_res else 0

        summary = query_stats(
            f"SELECT COUNT(*) as plays, COALESCE(SUM(PlayDuration), 0) as duration FROM PlaybackActivity {where_base + date_filter}",
            params,
            one=True,
        )
        total_plays = int(summary['plays'] if summary else 0)
        total_duration = int(summary['duration'] if summary else 0)

        daily_rows = query_stats(
            f"""SELECT substr(replace(DateCreated, 'T', ' '), 1, 10) as day,
                       COALESCE(SUM(PlayDuration), 0) as duration
                FROM PlaybackActivity {where_base + date_filter}
                GROUP BY day ORDER BY day DESC""",
            params,
        ) or []
        daily_duration = {r['day']: int(r['duration'] or 0) for r in daily_rows if r['day']}

        late_night_record = None
        late_row = query_stats(
            f"""SELECT DateCreated, ItemName, ItemType
                FROM PlaybackActivity {where_base + date_filter}
                AND CAST(substr(replace(DateCreated, 'T', ' '), 12, 2) AS INTEGER) BETWEEN 1 AND 5
                ORDER BY substr(replace(DateCreated, 'T', ' '), 12, 8) DESC
                LIMIT 1""",
            params,
            one=True,
        )
        if late_row and late_row.get('DateCreated'):
            dc = late_row.get('DateCreated', '')
            m = re.search(r'T(\d{2}):(\d{2}):(\d{2})', dc) or re.search(r' (\d{2}):(\d{2}):(\d{2})', dc)
            if m:
                late_night_record = {
                    "time": f"{m.group(1)}:{m.group(2)}",
                    "date": dc[:10][5:].replace('-', '月') + '日',
                    "name": get_clean_name(late_row.get('ItemName'), late_row.get('ItemType', ''))
                }

        top_rows = query_stats(
            f"""SELECT ItemName, ItemId, ItemType, COUNT(*) as Count, COALESCE(SUM(PlayDuration), 0) as Duration
                FROM PlaybackActivity {where_base + date_filter}
                GROUP BY ItemName
                ORDER BY Count DESC
                LIMIT 200""",
            params,
        ) or []
        aggregated = {}
        for row in top_rows:
            row_dict = dict(row)
            clean = get_clean_name(row_dict.get('ItemName'), row_dict.get('ItemType', ''))
            if clean not in aggregated:
                aggregated[clean] = {'ItemName': clean, 'ItemId': row_dict['ItemId'], 'Count': 0, 'Duration': 0}
            aggregated[clean]['Count'] += int(row_dict.get('Count') or 0)
            aggregated[clean]['Duration'] += int(row_dict.get('Duration') or 0)
                
        binge_day = None
        if daily_duration:
            max_day = max(daily_duration, key=daily_duration.get)
            max_dur = daily_duration[max_day]
            if max_dur > 3600:
                binge_day = {"date": max_day[5:].replace('-', '月') + '日', "hours": round(max_dur / 3600, 1)}
                
        genres = []
        favorite_type = None
        try:
            if user_id and user_id != 'all':
                # 🔥 从当前时间段播放的影片中获取类型（更准确）
                # 先获取这段时间播放过的 ItemId
                item_ids = list({r['ItemId'] for r in top_rows if r.get('ItemId')})[:50]  # 最多50个
                
                if item_ids:
                    genre_counts = defaultdict(int)
                    for item_id in item_ids:
                        try:
                            item_res = media_api.get(f"/Users/{user_id}/Items/{item_id}", params={"Fields": "Genres"}, timeout=2)
                            if item_res.status_code == 200:
                                item_data = item_res.json()
                                for g in item_data.get("Genres", []):
                                    genre_counts[g] += 1
                        except:
                            pass
                    
                    if genre_counts:
                        sorted_genres = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)[:3]
                        genres = [k for k, v in sorted_genres]
                        favorite_type = sorted_genres[0][0] if sorted_genres else None
        except Exception: pass

        # 🔥 计算连续观影天数
        streak_days = 0
        if daily_duration:
            sorted_days = sorted(daily_duration.keys(), reverse=True)
            if sorted_days:
                from datetime import datetime, timedelta
                today = datetime.now().strftime('%Y-%m-%d')
                yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
                
                # 从今天或昨天开始计算连续天数
                if sorted_days[0] in [today, yesterday]:
                    streak_days = 1
                    for i in range(1, len(sorted_days)):
                        prev_date = datetime.strptime(sorted_days[i-1], '%Y-%m-%d')
                        curr_date = datetime.strptime(sorted_days[i], '%Y-%m-%d')
                        if (prev_date - curr_date).days == 1:
                            streak_days += 1
                        else:
                            break

        # 🔥 构建每日统计数据
        daily_stats = [{"date": k, "duration": v} for k, v in daily_duration.items()]

        top_list = list(aggregated.values()); top_list.sort(key=lambda x: x['Count'], reverse=True)
        top_10 = top_list[:10]
        resolve_poster_ids(top_10)
        
        return {
            "status": "success", 
            "data": {
                "plays": total_plays, 
                "hours": round(total_duration / 3600), 
                "server_plays": server_plays, 
                "top_list": top_10,
                "daily_stats": daily_stats,
                "favorite_type": favorite_type,
                "streak_days": streak_days,
                "mood_data": {
                    "late_night": late_night_record,
                    "binge_day": binge_day,
                    "genres": genres
                }
            }
        }
    except: return {"status": "error", "data": {"plays": 0, "hours": 0}}

@router.get("/api/stats/top_users_list")
def api_top_users_list(request: Request, period: str = 'all'):
    # 🔒 安全检查：仅管理员可查看全站用户排名
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    try:
        where_base, params = build_stats_base_filter('all')
        date_filter = ""
        
        # 🔥 使用统一的时间计算模块
        from app.shared.time import get_period_range
        start_date, end_date, where_sql, _ = get_period_range(period)
        
        # 如果有有效的 WHERE 条件，使用它
        if where_sql:
            # 将 WHERE 替换为 AND（因为已有 where_base）
            date_filter = where_sql.replace("WHERE", "AND")
        # 否则使用原有的 SQLite 方式（向后兼容）
        elif period == 'day':
            date_filter = " AND DateCreated >= date('now', 'localtime', 'start of day')"
        elif period == 'week':
            date_filter = " AND DateCreated >= date('now', 'localtime', '-7 days')"
        elif period == 'month':
            date_filter = " AND DateCreated >= date('now', 'localtime', 'start of month')"
        elif period == 'year':
            date_filter = " AND DateCreated >= date('now', 'localtime', 'start of year')"

        sql = f"SELECT UserId, COUNT(*) as Plays, SUM(PlayDuration) as TotalTime FROM PlaybackActivity {where_base} {date_filter} GROUP BY UserId ORDER BY TotalTime DESC LIMIT 10"
        res = query_stats(sql, params)
        if not res: return {"status": "success", "data": []}
        user_map = get_user_map_local()
        hidden = get_hidden_users()
        # 确保 hidden 中的值是字符串，以便比较
        hidden_str = [str(h) for h in hidden]
        data = []
        for row in res:
            # 统一转换为字符串比较
            if str(row['UserId']) in hidden_str:
                continue
            u = dict(row)
            u['UserName'] = user_map.get(u['UserId'], f"User {str(u['UserId'])[:5]}")
            data.append(u)
            if len(data) >= 5:
                break
        return {"status": "success", "data": data}
    except Exception as e:
        print(f"[Top Users List] Error: {e}")
        return {"status": "error", "data": []}

@router.get("/api/stats/badges")
def api_badges(request: Request, user_id: Optional[str] = None):
    # 🔒 安全检查
    if not check_login(request):
        return {"status": "error", "message": "请先登录"}
    
    # 🔒 权限检查：普通用户只能查看自己的数据
    admin_user = request.session.get("user", {})
    req_user = request.session.get("req_user", {})
    is_admin = admin_user.get("auth_type") == "emby" or admin_user.get("role") == "admin"
    
    if not is_admin:
        if req_user:
            user_id = req_user.get("Id")
        elif admin_user:
            user_id = admin_user.get("id")
    
    try:
        where, params = build_stats_base_filter(user_id)
        
        # 🚀 性能优化：一次查询获取所有需要的数据
        client_col = get_playback_column_name()
        raw_data = query_stats(f"SELECT DateCreated, PlayDuration, COALESCE({client_col}, DeviceName) as Client, ItemId, ItemName, ItemType FROM PlaybackActivity {where}", params)
        if not raw_data: raw_data = []

        night_c, weekend_c, fish_c, morning_c = 0, 0, 0, 0
        dur_total = 0
        devices = set()
        items = {}
        movies, eps = 0, 0
        
        for row in raw_data:
            r = dict(row)
            dur = r.get('PlayDuration') or 0
            dur_total += dur
            
            client = r.get('Client')
            if client: devices.add(client)
            
            item_id = r.get('ItemId')
            if item_id:
                if item_id not in items: items[item_id] = {'name': r.get('ItemName'), 'c': 0}
                items[item_id]['c'] += 1
                
            it = r.get('ItemType')
            if it == 'Movie': movies += 1
            elif it == 'Episode': eps += 1
            
            dc = r.get('DateCreated')
            if dc:
                # 直接解析小时和星期，避免创建 datetime 对象
                try:
                    # 格式: 2024-01-15T14:30:00 或 2024-01-15 14:30:00
                    date_part = dc[:10] if len(dc) >= 10 else ""
                    time_part = dc[11:16] if len(dc) >= 16 else ""
                    
                    if time_part:
                        hour = int(time_part[:2])
                        
                        if 2 <= hour <= 5: night_c += 1
                        if 5 <= hour <= 8: morning_c += 1
                        
                    if date_part:
                        # 计算星期几 (0=周一, 6=周日)
                        from datetime import date as dt_date
                        parts = date_part.split('-')
                        if len(parts) == 3:
                            try:
                                d = dt_date(int(parts[0]), int(parts[1]), int(parts[2]))
                                weekday = d.weekday()
                                if weekday in (5, 6): weekend_c += 1
                                if weekday in (0, 1, 2, 3, 4) and 9 <= hour <= 17: fish_c += 1
                            except:
                                pass
                except:
                    pass

        badges = []
        if night_c >= 2: badges.append({"id": "night", "name": "深夜修仙", "icon": "fa-moon", "color": "text-indigo-500", "bg": "bg-indigo-100", "desc": "深夜是灵魂最自由的时刻"})
        if weekend_c >= 5: badges.append({"id": "weekend", "name": "周末狂欢", "icon": "fa-champagne-glasses", "color": "text-pink-500", "bg": "bg-pink-100", "desc": "工作日唯唯诺诺，周末重拳出击"})
        if dur_total > 180000: badges.append({"id": "liver", "name": "核心肝帝", "icon": "fa-fire", "color": "text-red-500", "bg": "bg-red-100", "desc": "阅片无数，肝度爆表"})
        if fish_c >= 5: badges.append({"id": "fish", "name": "带薪观影", "icon": "fa-fish", "color": "text-cyan-500", "bg": "bg-cyan-100", "desc": "工作是老板的，快乐是自己的"})
        if morning_c >= 2: badges.append({"id": "morning", "name": "晨练追剧", "icon": "fa-sun", "color": "text-amber-500", "bg": "bg-amber-100", "desc": "比你优秀的人，连看片都比你早"})
        if len(devices) >= 2: badges.append({"id": "device", "name": "全平台制霸", "icon": "fa-gamepad", "color": "text-emerald-500", "bg": "bg-emerald-100", "desc": "手机、平板、电视，哪里都能看"})
        
        if items:
            loyal = max(items.values(), key=lambda x: x['c'])
            if loyal['c'] >= 3:
                safe_name = str(loyal.get('name') or '未知').split(' - ')[0][:10]
                badges.append({"id": "loyal", "name": "N刷狂魔", "icon": "fa-repeat", "color": "text-teal-500", "bg": "bg-teal-100", "desc": f"对《{safe_name}》爱得深沉"})
                
        total = movies + eps
        if total > 10:
            if movies / total > 0.6: badges.append({"id": "movie_lover", "name": "电影鉴赏家", "icon": "fa-film", "color": "text-blue-500", "bg": "bg-blue-100", "desc": "沉浸在两小时的艺术光影世界"})
            elif eps / total > 0.6: badges.append({"id": "tv_lover", "name": "追剧狂魔", "icon": "fa-tv", "color": "text-purple-500", "bg": "bg-purple-100", "desc": "一集接一集，根本停不下来"})
            
        return {"status": "success", "data": badges}
    except Exception as e: 
        return {"status": "success", "data": []}

@router.get("/api/stats/monthly_stats")
def api_monthly_stats(request: Request, user_id: Optional[str] = None):
    # 🔒 安全检查
    if not check_login(request):
        return {"status": "error", "message": "请先登录"}

    # 🔒 权限检查：普通用户只能查看自己的数据
    admin_user = request.session.get("user", {})
    req_user = request.session.get("req_user", {})
    is_admin = admin_user.get("auth_type") == "emby" or admin_user.get("role") == "admin"

    if not is_admin:
        if req_user:
            user_id = req_user.get("Id")
        elif admin_user:
            user_id = admin_user.get("id")

    try:
        where_base, params = build_stats_base_filter(user_id)
        # 🔥 时区修复
        where = where_base + " AND DateCreated > date('now', 'localtime', '-12 months')"
        sql = f"SELECT substr(replace(DateCreated, 'T', ' '), 1, 7) as Month, SUM(PlayDuration) as Duration FROM PlaybackActivity {where} GROUP BY Month ORDER BY Month"
        results = query_stats(sql, params); data = {}
        if results: 
            for r in results: data[r['Month']] = int(r['Duration'] or 0)
        return {"status": "success", "data": data}
    except: return {"status": "error", "data": {}}

# ==========================================
# ==========================================
# 🔥 Pro 仪表盘：最近入库统计与趋势 (独立API，供charts.js调用)
# ==========================================
@router.get("/api/stats/recent_added")
def api_recent_added(request: Request = None):
    # 🔒 安全检查（内部调用时 request 为 None，跳过检查）
    if request and not check_login(request):
        return {"status": "error", "message": "请先登录"}
    """独立API入口，复用 _get_added_stats_sync 的逻辑"""
    result = _get_added_stats_sync()
    return {"status": "success", "data": result}

# 需要在 system.py 顶部确认是否有 import psutil，如果没有请加上
import psutil
import asyncio
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 🔥 仪表盘聚合 API - 核心数据快速返回
# ==========================================
_executor = ThreadPoolExecutor(max_workers=8)

# 🔥 内存缓存：用于快速响应重复请求（按访问上下文隔离，避免用户/管理员数据串用）
_DASHBOARD_PRELOAD_KEY = "admin:all"
_dashboard_cache = {}
_dashboard_cache_user_ids = {}
_DASHBOARD_CACHE_TTL = get_dashboard_cache_ttl()  # 默认5分钟
_DASHBOARD_ACTIVE_WINDOW = 600
_dashboard_last_access = {}
_dashboard_refresh_lock = asyncio.Lock()

def _normalize_dashboard_user_id(user_id):
    if user_id is None or user_id == "" or user_id == "all":
        return None
    return str(user_id)

def _get_dashboard_context(request: Request, user_id: Optional[str] = None):
    admin_user = request.session.get("user", {}) or {}
    req_user = request.session.get("req_user", {}) or {}
    is_admin = admin_user.get("auth_type") == "emby" or admin_user.get("role") == "admin"

    if is_admin:
        effective_user_id = _normalize_dashboard_user_id(user_id)
        cache_key = f"admin:{effective_user_id or 'all'}"
    else:
        effective_user_id = req_user.get("Id") if req_user else admin_user.get("id")
        effective_user_id = _normalize_dashboard_user_id(effective_user_id)
        cache_key = f"user:{effective_user_id or 'unknown'}"

    return cache_key, effective_user_id, is_admin

def _get_dashboard_cache_entry(cache_key: str):
    return _dashboard_cache.get(cache_key, {"data": None, "ts": 0})

def _get_dashboard_cached_data(cache_key: str, now: float = None):
    now = now or time.time()
    entry = _get_dashboard_cache_entry(cache_key)
    if entry.get("data") and (now - entry.get("ts", 0)) < _DASHBOARD_CACHE_TTL:
        return entry["data"]
    return None

def _set_dashboard_cache(cache_key: str, data: dict, user_id=None, ts: float = None):
    _dashboard_cache[cache_key] = {
        "data": data,
        "ts": ts or time.time()
    }
    _dashboard_cache_user_ids[cache_key] = user_id

def _mark_dashboard_access(cache_key: str, now: float = None):
    _dashboard_last_access[cache_key] = now or time.time()

async def _fetch_dashboard_core(user_id: str) -> dict:
    """核心仪表盘数据（播放统计、媒体库储量）- 快速"""
    try:
        where, params = build_stats_base_filter(user_id)
        plays = query_stats(f"SELECT COUNT(*) as c FROM PlaybackActivity {where}", params)[0]['c']
        users = query_stats(f"SELECT COUNT(DISTINCT UserId) as c FROM PlaybackActivity {where} AND DateCreated > date('now', 'localtime', '-30 days')", params)[0]['c']
        dur = query_stats(f"SELECT SUM(PlayDuration) as c FROM PlaybackActivity {where}", params)[0]['c'] or 0

        lib = {"movie": 0, "series": 0, "episode": 0}
        try:
            res = media_api.get("/Items/Counts", timeout=3)
            if res.status_code == 200:
                d = res.json()
                lib = {"movie": d.get("MovieCount", 0), "series": d.get("SeriesCount", 0), "episode": d.get("EpisodeCount", 0)}
        except Exception: pass

        return {
            "total_plays": plays,
            "active_users": users,
            "total_duration": dur,
            "library": lib
        }
    except Exception:
        return {"total_plays": 0, "active_users": 0, "total_duration": 0, "library": {}}

async def _fetch_users_list() -> list:
    """用户列表 - 快速"""
    try:
        res = media_api.get("/Users", timeout=3)
        if res.status_code == 200:
            hidden = get_hidden_users()
            return [
                {"UserId": u['Id'], "UserName": u['Name'], "IsHidden": u['Id'] in hidden}
                for u in res.json()
            ]
        logger.error(f"[用户列表] Emby API 错误: {res.status_code}")
        return []
    except Exception as e:
        logger.error(f"[用户列表] 获取失败: {e}")
        return []

async def _fetch_libraries() -> list:
    """媒体库列表 - 快速"""
    try:
        admin_id = get_admin_user_id()
        if admin_id:
            res = media_api.get(f"/Users/{admin_id}/Views", timeout=5)
            if res.status_code == 200:
                return [
                    {
                        "Id": i.get("Id"),
                        "Name": i.get("Name"),
                        "CollectionType": i.get("CollectionType", "unknown"),
                        "ImageTag": i.get("ImageTags", {}).get("Primary", "")[:8] if i.get("ImageTags", {}).get("Primary") else ""
                    }
                    for i in res.json().get("Items", [])
                ]
            logger.error(f"[媒体库列表] Emby API 错误: {res.status_code}")
        return []
    except Exception as e:
        logger.error(f"[媒体库列表] 获取失败: {e}")
        return []

async def _fetch_top_users() -> list:
    """白金观影榜 - 快速（本地数据库）"""
    try:
        where_base, params_top = build_stats_base_filter('all')
        sql = f"SELECT UserId, COUNT(*) as Plays, SUM(PlayDuration) as TotalTime FROM PlaybackActivity {where_base} GROUP BY UserId ORDER BY TotalTime DESC LIMIT 10"
        res_top = query_stats(sql, params_top)
        user_map = get_user_map_local()
        hidden = get_hidden_users()
        hidden_str = [str(h) for h in hidden]
        top_users = []
        for row in (res_top or []):
            if str(row['UserId']) in hidden_str:
                continue
            u = dict(row)
            u['UserName'] = user_map.get(u['UserId'], f"User {str(u['UserId'])[:5]}")
            top_users.append(u)
            if len(top_users) >= 5:
                break
        return top_users
    except Exception as e:
        print(f"[Dashboard Init] Top users error: {e}")
        return []

async def _fetch_trend(user_id: str) -> dict:
    """趋势图数据 - 快速（本地数据库）"""
    try:
        where_trend, params_trend = build_stats_base_filter(user_id)
        sql_trend = f"SELECT substr(replace(DateCreated, 'T', ' '), 1, 10) as Label, SUM(PlayDuration) as Duration FROM PlaybackActivity {where_trend} AND DateCreated > date('now', 'localtime', '-30 days') GROUP BY Label ORDER BY Label"
        results_trend = query_stats(sql_trend, params_trend)
        trend_data = {}
        if results_trend:
            for r in results_trend:
                trend_data[r['Label']] = int(r['Duration'] or 0)
        return trend_data
    except:
        return {}

# ==================== 🔥 缓存预热功能 ====================

# 预热状态标记
_preload_started = False
_dashboard_cache_tasks_started = False
_last_refresh_log_time = 0  # 上次打印刷新日志的时间

async def preload_dashboard_cache(silent: bool = False, cache_key: str = _DASHBOARD_PRELOAD_KEY, user_id=None):
    """
    后台预热仪表盘缓存
    在容器启动后自动执行，用户打开首页即可秒出数据
    
    Args:
        silent: 静默模式，不打印日志（用于后台定时刷新）
    """
    global _preload_started, _last_refresh_log_time
    
    # 等待 Emby API 连接就绪（避免启动时 Emby 还未准备好）
    if not _preload_started:
        await asyncio.sleep(8)
        _preload_started = True
    
    if _dashboard_refresh_lock.locked():
        return False

    async with _dashboard_refresh_lock:
        try:
            if not silent:
                print("[🔥 预热] 开始预热仪表盘缓存...")
        
            effective_user_id = _normalize_dashboard_user_id(user_id)
            results = await asyncio.gather(
                asyncio.wait_for(_fetch_dashboard_core(effective_user_id), timeout=15),
                asyncio.wait_for(_fetch_users_list(), timeout=10),
                asyncio.wait_for(_fetch_libraries(), timeout=15),
                asyncio.wait_for(_fetch_top_users(), timeout=10),
                asyncio.wait_for(_fetch_trend(effective_user_id), timeout=10),
                return_exceptions=True
            )
        
            dashboard, users, libraries, top_users, trend = results
        
            result_data = {
                "dashboard": dashboard if not isinstance(dashboard, Exception) else {"total_plays": 0, "active_users": 0, "total_duration": 0, "library": {}},
                "users": users if not isinstance(users, Exception) else [],
                "libraries": libraries if not isinstance(libraries, Exception) else [],
                "top_users": top_users if not isinstance(top_users, Exception) else [],
                "trend": trend if not isinstance(trend, Exception) else {}
            }
        
            _set_dashboard_cache(cache_key, result_data, effective_user_id)
        
            if not silent:
                print(f"[🔥 预热] 仪表盘缓存预热完成！媒体库: {len(result_data['libraries'])} 个, 用户: {len(result_data['users'])} 个")
            return True
        except Exception as e:
            if not silent:
                print(f"[🔥 预热] 预热失败: {e}")
            return False

async def start_dashboard_cache_refresh_loop():
    """
    后台定时刷新仪表盘缓存
    每分钟检查一次，只在近期有人访问且缓存过期时刷新
    """
    global _last_refresh_log_time
    
    while True:
        await asyncio.sleep(60)
        try:
            now = time.time()
            active_keys = [
                key for key, last_access in list(_dashboard_last_access.items())
                if now - last_access <= _DASHBOARD_ACTIVE_WINDOW
            ]
            for cache_key in active_keys:
                entry = _get_dashboard_cache_entry(cache_key)
                cache_age = now - entry.get("ts", 0) if entry.get("ts", 0) > 0 else 999
                if cache_age >= _DASHBOARD_CACHE_TTL:
                    await preload_dashboard_cache(
                        silent=True,
                        cache_key=cache_key,
                        user_id=_dashboard_cache_user_ids.get(cache_key),
                    )
                    # 每5分钟打印一次刷新日志（避免刷屏）
                    if now - _last_refresh_log_time >= 300:
                        _last_refresh_log_time = now
                        print("[🔥 缓存] 后台刷新完成，下次刷新: 60秒后")
        except Exception as e:
            # 刷新失败不打印日志，避免刷屏
            pass

@router.get("/api/dashboard/preload_status")
async def api_preload_status(request: Request):
    """
    获取缓存预热状态
    前端可以据此判断是否需要等待
    """
    # 🔒 管理后台聚合状态，仅管理员可访问
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    entry = _get_dashboard_cache_entry(_DASHBOARD_PRELOAD_KEY)
    data = entry.get("data")
    ts = entry.get("ts", 0)
    return {
        "status": "success",
        "data": {
            "cached": data is not None,
            "cache_age": round(time.time() - ts) if ts > 0 else 0,
            "cache_ttl": _DASHBOARD_CACHE_TTL,
            "libraries_count": len(data.get("libraries", [])) if data else 0,
            "users_count": len(data.get("users", [])) if data else 0
        }
    }


def start_dashboard_cache_tasks() -> None:
    global _dashboard_cache_tasks_started
    if _dashboard_cache_tasks_started:
        return
    _dashboard_cache_tasks_started = True
    asyncio.create_task(preload_dashboard_cache())
    asyncio.create_task(start_dashboard_cache_refresh_loop())


@router.get("/api/dashboard/init")
async def api_dashboard_init(request: Request, user_id: Optional[str] = None):
    # 🔒 管理后台首屏聚合接口，仅管理员可访问
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    """
    仪表盘首屏聚合接口 - 核心数据快速返回
    """
    cache_key, effective_user_id, _is_admin = _get_dashboard_context(request, user_id)

    def _strip_user_id(data: dict) -> dict:
        """非管理员返回时剥离 top_users 中的原始 UserId"""
        if _is_admin:
            return data
        d = copy.deepcopy(data)
        for u in d.get("top_users", []):
            u.pop("UserId", None)
        return d

    now = time.time()
    _mark_dashboard_access(cache_key, now)
    
    # 🔥 检查内存缓存（30秒内直接返回）
    cached_data = _get_dashboard_cached_data(cache_key, now)
    if cached_data:
        return {
            "status": "success",
            "data": _strip_user_id(cached_data),
            "cached": True
        }
    
    # 🔥 并发执行核心数据（快速）
    try:
        results = await asyncio.gather(
            asyncio.wait_for(_fetch_dashboard_core(effective_user_id), timeout=5),
            asyncio.wait_for(_fetch_users_list(), timeout=3),
            asyncio.wait_for(_fetch_libraries(), timeout=5),
            asyncio.wait_for(_fetch_top_users(), timeout=3),
            asyncio.wait_for(_fetch_trend(effective_user_id), timeout=3),
            return_exceptions=True
        )
        
        dashboard, users, libraries, top_users, trend = results
    except asyncio.TimeoutError as e:
        print(f"[Dashboard Init] 请求超时: {e}")
        stale_entry = _get_dashboard_cache_entry(cache_key)
        if stale_entry.get("data"):
            return {"status": "success", "data": _strip_user_id(stale_entry["data"]), "cached": True, "timeout": True}
        dashboard = {"total_plays": 0, "active_users": 0, "total_duration": 0, "library": {}}
        users = []
        libraries = []
        top_users = []
        trend = {}
    
    result_data = {
        "dashboard": dashboard if not isinstance(dashboard, Exception) else {"total_plays": 0, "active_users": 0, "total_duration": 0, "library": {}},
        "users": users if not isinstance(users, Exception) else [],
        "libraries": libraries if not isinstance(libraries, Exception) else [],
        "top_users": top_users if not isinstance(top_users, Exception) else [],
        "trend": trend if not isinstance(trend, Exception) else {}
    }
    
    # 🔥 更新内存缓存
    _set_dashboard_cache(cache_key, result_data, effective_user_id, now)
    
    return {
        "status": "success",
        "data": _strip_user_id(result_data),
        "cached": False
    }


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


@router.get("/api/system/monitor")
def api_system_monitor(request: Request):
    # 🔒 管理员专用：只检查后台登录
    if not check_admin_login(request):
        return {"status": "error", "message": "需要管理员权限"}
    try:
        # 🔥 interval=0 立即返回（非阻塞），使用上次采样值
        cpu_usage = psutil.cpu_percent(interval=0)

        # 内存使用率
        memory_info = psutil.virtual_memory()
        memory_usage = memory_info.percent

        # 根目录磁盘使用率
        disk_info = psutil.disk_usage('/')
        disk_usage = disk_info.percent

        return {
            "status": "success",
            "data": {
                "cpu": cpu_usage,
                "memory": memory_usage,
                "disk": disk_usage
            }
        }
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e, "探针读取失败")}


# ==================== 🔥 内容风云榜详情 API ====================

@router.get("/api/stats/item_detail")
def api_item_detail(request: Request, item_id: str, item_name: Optional[str] = None):
    """获取媒体详情（谁在看、播放历史）"""
    if not check_login(request):
        return {"status": "error", "message": "请先登录"}

    # 🔒 权限检查：非管理员只能查看自己的数据
    admin_user = request.session.get("user", {})
    req_user = request.session.get("req_user", {})
    is_admin = admin_user.get("auth_type") == "emby" or admin_user.get("role") == "admin"
    current_user_id = None
    if not is_admin:
        current_user_id = (req_user or admin_user).get("Id")

    try:
        # 1. 获取媒体基础信息
        item_info = None
        item_type = None
        series_name = None
        series_id = None
        try:
            res = media_api.get(f"/Users/{request.session.get('user', {}).get('Id', '')}/Items/{item_id}")
            logger.info(f"[item_detail] Emby API status: {res.status_code}")
            if res.status_code == 200:
                item_info = res.json()
                item_type = item_info.get('Type')
                logger.info(f"[item_detail] item_type: {item_type}, item_name: {item_info.get('Name')}")
                # 🔥 如果是剧集，获取剧名和剧集ID
                if item_type == 'Episode':
                    # 尝试多个可能的字段名
                    series_name = item_info.get('SeriesName') or item_info.get('Series') or item_info.get('SeriesName')
                    series_id = item_info.get('SeriesId') or item_info.get('SeriesItemId')
                    logger.info(f"[item_detail] Episode detected, series_name: {series_name}, series_id: {series_id}")
        except Exception as e:
            logger.error(f"[item_detail] 获取媒体信息失败: {e}")
        
        # 🔥 如果 Emby API 失败，从 item_name 提取剧名和季
        if not series_name and item_name:
            # 从 "年少有为 - s01e05 - 第 5 集" 提取 "年少有为 - 第 1 季"
            # 或从 "纯真年代的爱情 - 第 1 季" 保留原样
            parts = item_name.split(' - ')
            if len(parts) >= 2:
                # 第一部分是剧名
                name_part = parts[0].strip()
                # 查找季信息
                season_part = None
                for p in parts[1:]:
                    # 匹配 "第 X 季" 或 "S01" 格式
                    m = re.search(r'第\s*\d+\s*季', p)
                    if m:
                        season_part = m.group()
                        break
                    m = re.search(r'S(\d+)', p, re.I)
                    if m:
                        season_num = int(m.group(1))
                        season_part = f"第 {season_num} 季"
                        break
                if season_part:
                    series_name = f"{name_part} - {season_part}"
                else:
                    series_name = name_part
            else:
                series_name = parts[0].strip()
            logger.info(f"[item_detail] 从 item_name 提取: {series_name}")
        
        # 2. 获取播放统计
        rows = []
        
        # 🔥 如果是剧集，始终按剧名查询所有集数
        if series_name or item_name:
            search_name = series_name or item_name
            # 提取剧名（去掉集数信息）
            # 例如 "逐玉 - s01e01 - 第 1 集" -> "逐玉"
            clean_name = search_name.split(' - ')[0].strip()
            # 去掉可能的季数信息
            clean_name = re.sub(r'\s*S\d+.*', '', clean_name, flags=re.I)
            clean_name = re.sub(r'\s*第.*季.*', '', clean_name)
            clean_name = clean_name.strip()
            logger.info(f"[item_detail] 按剧名查询: '{clean_name}' (原始: '{search_name}')")
            
            if is_admin:
                sql_by_name = """
                    SELECT
                        ItemName, ItemType, PlayDuration, UserId, DateCreated
                    FROM PlaybackActivity
                    WHERE ItemName LIKE ?
                    ORDER BY DateCreated DESC
                    LIMIT 500
                """
                rows = query_stats(sql_by_name, [f"%{clean_name}%"])
            else:
                sql_by_name = """
                    SELECT
                        ItemName, ItemType, PlayDuration, UserId, DateCreated
                    FROM PlaybackActivity
                    WHERE ItemName LIKE ? AND UserId = ?
                    ORDER BY DateCreated DESC
                    LIMIT 500
                """
                rows = query_stats(sql_by_name, [f"%{clean_name}%", current_user_id])
            logger.info(f"[item_detail] 按剧名查询结果: {len(rows) if rows else 0} 条")
        else:
            # 🔥 电影等其他类型，按 ItemId 查询
            if is_admin:
                sql_by_id = """
                    SELECT
                        ItemName, ItemType, PlayDuration, UserId, DateCreated
                    FROM PlaybackActivity
                    WHERE ItemId = ?
                    ORDER BY DateCreated DESC
                    LIMIT 100
                """
                rows = query_stats(sql_by_id, [item_id])
            else:
                sql_by_id = """
                    SELECT
                        ItemName, ItemType, PlayDuration, UserId, DateCreated
                    FROM PlaybackActivity
                    WHERE ItemId = ? AND UserId = ?
                    ORDER BY DateCreated DESC
                    LIMIT 100
                """
                rows = query_stats(sql_by_id, [item_id, current_user_id])
            logger.info(f"[item_detail] 按 ItemId 查询结果: {len(rows) if rows else 0} 条")
        
        if not rows:
            return {"status": "error", "message": "无播放记录"}
        
        # 🔥 获取用户 ID 到用户名的映射
        user_map = get_user_map_local()
        
        # 3. 统计数据
        total_plays = len(rows)
        total_time = sum(r.get('PlayDuration') or 0 for r in rows)
        
        # 用户统计 - 通过 UserId 查找用户名
        user_stats = {}
        for r in rows:
            uid = r.get('UserId') or 'unknown'
            if uid not in user_stats:
                # 🔥 优先从 user_map 获取用户名
                user_name = user_map.get(uid) or r.get('UserName') or '未知用户'
                user_stats[uid] = {
                    'UserId': uid,
                    'UserName': user_name,
                    'PlayCount': 0,
                    'TotalTime': 0
                }
            user_stats[uid]['PlayCount'] += 1
            user_stats[uid]['TotalTime'] += r.get('PlayDuration') or 0
        
        # 按播放次数排序
        top_users = sorted(user_stats.values(), key=lambda x: x['PlayCount'], reverse=True)[:10]
        
        # 4. 最近播放历史
        recent_plays = []
        for r in rows[:20]:
            uid = r.get('UserId')
            # 🔥 优先从 user_map 获取用户名
            user_name = user_map.get(uid) or r.get('UserName') or '未知用户'
            recent_plays.append({
                'UserName': user_name,
                'PlayDuration': r.get('PlayDuration') or 0,
                'DateCreated': r.get('DateCreated')
            })
        
        # 5. 时间分布（按天）
        time_distribution = {}
        for r in rows:
            if r.get('DateCreated'):
                day = r['DateCreated'][:10]  # YYYY-MM-DD
                if day not in time_distribution:
                    time_distribution[day] = {'plays': 0, 'time': 0}
                time_distribution[day]['plays'] += 1
                time_distribution[day]['time'] += r.get('PlayDuration') or 0
        
        # 按日期排序，取最近30天
        sorted_days = sorted(time_distribution.items(), key=lambda x: x[0], reverse=True)[:30]
        
        return {
            "status": "success",
            "data": {
                "ItemInfo": {
                    "Id": series_id or item_id,
                    "Name": series_name or (item_info.get('Name') if item_info else rows[0]['ItemName']),
                    "Type": item_info.get('Type') if item_info else rows[0]['ItemType'],
                    "Overview": item_info.get('Overview') if item_info else None,
                    "ProductionYear": item_info.get('ProductionYear') if item_info else None,
                    "CommunityRating": item_info.get('CommunityRating') if item_info else None,
                    "Genres": item_info.get('Genres') if item_info else None,
                } if item_info else {
                    "Id": item_id,
                    "Name": series_name or rows[0]['ItemName'],
                    "Type": rows[0]['ItemType'],
                    "Overview": None,
                    "ProductionYear": None,
                    "CommunityRating": None,
                    "Genres": None
                },
                "Stats": {
                    "TotalPlays": total_plays,
                    "TotalTime": total_time,
                    "TotalTimeHours": round(total_time / 3600, 1)
                },
                "TopUsers": top_users,
                "RecentPlays": recent_plays,
                "TimeDistribution": dict(sorted_days)
            }
        }
    except Exception as e:
        logger.error(f"[api_item_detail] 异常: {e}")
        return {"status": "error", "message": safe_error_message(e)}
