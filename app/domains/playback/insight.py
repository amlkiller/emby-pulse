from fastapi import APIRouter, Request
from app.routers.auth import is_admin_user  # 🔒 引入管理员权限检查
from pydantic import BaseModel
from app.infra.clients.media_server_client import media_api
from app.dao.insight_dao import (
    delete_insight_ignores,
    list_insight_ignore_item_ids,
    list_insight_ignores,
    save_insight_ignore,
    save_insight_ignores,
)
import logging
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.core.security_utils import safe_error_message

logger = logging.getLogger("uvicorn")
router = APIRouter()

# --- 🚀 永久常驻缓存 (24小时生命周期) ---
GLOBAL_CACHE = { "quality_stats": None, "last_scan_time": 0 }
CACHE_EXPIRE_SECONDS = 86400 

# 🔥 限制缓存数据大小，避免内存泄漏
MAX_CACHED_MOVIES = 10000  # 每个分类最多缓存 10000 部

def _trim_stats_cache(stats):
    """裁剪缓存数据，避免内存占用过大"""
    if not stats or "movies" not in stats:
        return stats
    for key in stats["movies"]:
        if len(stats["movies"][key]) > MAX_CACHED_MOVIES:
            stats["movies"][key] = stats["movies"][key][:MAX_CACHED_MOVIES]
    return stats 
class IgnoreModel(BaseModel):
    item_id: str
    item_name: str

class BatchIgnoreModel(BaseModel):
    items: list[IgnoreModel]

class BatchUnignoreModel(BaseModel):
    item_ids: list[str]

# --- 单条忽略 ---
@router.post("/api/insight/ignore")
def ignore_item(data: IgnoreModel, request: Request):
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    try:
        save_insight_ignore(data.item_id, data.item_name)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

# --- 🔥 新增：批量原子忽略 (彻底解决并发锁死问题) ---
@router.post("/api/insight/ignore_batch")
def ignore_items_batch(data: BatchIgnoreModel, request: Request):
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    try:
        save_insight_ignores(data.items)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

# --- 批量恢复 ---
@router.post("/api/insight/unignore_batch")
def unignore_items_batch(data: BatchUnignoreModel, request: Request):
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    try:
        delete_insight_ignores(data.item_ids)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

@router.get("/api/insight/ignores")
def get_ignored_items(request: Request):
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    rows = list_insight_ignores()
    return {"status": "success", "data": [dict(r) for r in rows] if rows else []}

def _fetch_items_page(start_index, limit, retry=2):
    """获取单页电影数据（带重试）"""
    params = {
        "Recursive": "true",
        "IncludeItemTypes": "Movie",
        "Fields": "MediaSources,Path,MediaStreams,ProviderIds,DateCreated",
        "StartIndex": start_index,
        "Limit": limit,
    }
    
    for attempt in range(retry + 1):
        try:
            # 🔥 增加超时时间，避免 Emby 响应慢
            response = media_api.get("/Items", params=params, timeout=60)
            if response.status_code == 200:
                return response.json().get("Items", [])
        except Exception as e:
            if attempt < retry:
                logger.debug(f"[质量盘点] 重试请求 (StartIndex={start_index}, 第{attempt+1}次)")
                time.sleep(2)  # 重试前等待 2 秒
            else:
                logger.warning(f"[质量盘点] 分页请求失败 (StartIndex={start_index}): {e}")
    return []

def _process_item(item):
    """处理单个电影项，返回分类结果"""
    item_id = item.get("Id")
    media_sources = item.get("MediaSources")
    if not media_sources or not isinstance(media_sources, list):
        return None
    
    video_stream = next((s for s in media_sources[0].get("MediaStreams", []) if s.get("Type") == "Video"), None)
    if not video_stream:
        return None

    width = video_stream.get('Width', 0)
    height = video_stream.get('Height', 0)
    
    if width == 0 or height == 0:
        return None

    movie_obj = {
        "Id": item_id,
        "Name": item.get("Name"),
        "Year": item.get("ProductionYear"),
        "Resolution": f"{width}x{height}",
        "Path": item.get("Path", "未知路径")
    }

    result = {"movie": movie_obj, "categories": []}

    # 分辨率分类
    if width >= 3800:
        result["categories"].append("4k")
    elif width >= 1900:
        result["categories"].append("1080p")
    elif width >= 1200:
        result["categories"].append("720p")
    else:
        result["categories"].append("sd")

    # 编码分类
    codec = video_stream.get("Codec", "").lower()
    if "hevc" in codec or "h265" in codec:
        result["categories"].append("hevc")
    elif "h264" in codec or "avc" in codec:
        result["categories"].append("h264")
    elif "av1" in codec:
        result["categories"].append("av1")
    else:
        result["categories"].append("other_codec")

    # HDR 分类
    video_range = video_stream.get("VideoRange", "").lower()
    display_title = video_stream.get("DisplayTitle", "").lower()
    
    if "dolby" in display_title or "dv" in display_title or "dolby" in video_range:
        result["categories"].append("dolby_vision")
    elif "hdr" in video_range or "hdr" in display_title or "pq" in video_range:
        result["categories"].append("hdr10")
    else:
        result["categories"].append("sdr")

    return result

@router.get("/api/insight/quality")
def scan_library_quality(request: Request):
    """ 质量盘点核心引擎（分页并发获取 + 24小时缓存） """
    user = request.session.get("user")
    if not user: return {"status": "error", "message": "Unauthorized"}
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    
    force_refresh = request.query_params.get("force_refresh") == "true"
    current_time = time.time()
    
    # 核心提速逻辑：动态剔除忽略名单
    def get_filtered_stats(stats):
        ignore_rows = list_insight_ignore_item_ids()
        ignore_set = {r['item_id'] for r in ignore_rows} if ignore_rows else set()
        
        if not ignore_set: return stats
        
        new_stats = {
            "total_count": stats["total_count"], 
            "scan_time_str": stats["scan_time_str"],
            "movies": {}
        }
        for k, v in stats["movies"].items():
            new_stats["movies"][k] = [m for m in v if m["Id"] not in ignore_set]
        return new_stats

    if not force_refresh and GLOBAL_CACHE["quality_stats"] and (current_time - GLOBAL_CACHE["last_scan_time"] < CACHE_EXPIRE_SECONDS):
        return {"status": "success", "data": get_filtered_stats(GLOBAL_CACHE["quality_stats"])}

    if not media_api.host or not media_api.api_key: return {"status": "error", "message": "Emby 未配置"}

    try:
        # 第一步：获取总数
        count_resp = media_api.get(
            "/Items",
            params={"Recursive": "true", "IncludeItemTypes": "Movie", "Limit": 0},
            timeout=10,
        )
        
        if count_resp.status_code != 200:
            return {"status": "error", "message": "获取电影总数失败"}
        
        total_count = count_resp.json().get("TotalRecordCount", 0)
        if total_count == 0:
            return {"status": "success", "data": {"total_count": 0, "scan_time_str": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "movies": {}}}

        # 第二步：分页并发获取（小并发，避免压力过大）
        PAGE_SIZE = 400  # 每页 400 部
        page_count = (total_count + PAGE_SIZE - 1) // PAGE_SIZE
        all_items = []
        
        # 🔥 小并发（最多 2 个），平衡速度和稳定性
        max_workers = min(2, page_count)
        
        if page_count <= 2:
            # 页数少时直接顺序获取
            for page in range(page_count):
                start_index = page * PAGE_SIZE
                items = _fetch_items_page(start_index, PAGE_SIZE)
                all_items.extend(items)
        else:
            # 页数多时用小并发
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = []
                for page in range(page_count):
                    start_index = page * PAGE_SIZE
                    futures.append(executor.submit(_fetch_items_page, start_index, PAGE_SIZE))
                
                completed = 0
                for future in as_completed(futures, timeout=300):
                    try:
                        items = future.result(timeout=60)
                        all_items.extend(items)
                        completed += 1
                        if completed % 3 == 0:
                            logger.info(f"[质量盘点] 已获取 {len(all_items)}/{total_count} 部电影")
                    except Exception as e:
                        logger.warning(f"[质量盘点] 分页获取失败: {e}")

        logger.info(f"[质量盘点] 获取到 {len(all_items)}/{total_count} 部电影")

        # 第三步：处理分类
        stats = {
            "total_count": len(all_items),
            "scan_time_str": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "movies": {
                "4k": [], "1080p": [], "720p": [], "sd": [],
                "hevc": [], "h264": [], "av1": [], "other_codec": [],
                "dolby_vision": [], "hdr10": [], "sdr": []
            }
        }

        for item in all_items:
            result = _process_item(item)
            if result:
                for cat in result["categories"]:
                    if cat in stats["movies"]:
                        stats["movies"][cat].append(result["movie"])

        GLOBAL_CACHE["quality_stats"] = _trim_stats_cache(stats)
        GLOBAL_CACHE["last_scan_time"] = current_time
        
        return {"status": "success", "data": get_filtered_stats(stats)}
    except Exception as e:
        logger.error(f"质量盘点错误: {str(e)}")
        return {"status": "error"}
