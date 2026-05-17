"""Emby API 交互工具"""
import logging
import random
from typing import List, Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.core.media_adapter import media_api

logger = logging.getLogger("uvicorn")


def get_libraries() -> List[Dict[str, Any]]:
    """获取所有媒体库"""
    try:
        res = media_api.get("/Library/VirtualFolders", timeout=10)
        if res.status_code == 200:
            libraries = []
            for lib in res.json():
                lib_id = lib.get("ItemId") or lib.get("Id")
                lib_name = lib.get("Name", "未命名")
                libraries.append({
                    "id": lib_id,
                    "name": lib_name,
                    "collection_type": lib.get("CollectionType", "unknown"),
                    "item_count": lib.get("ItemCount", 0)
                })
            return libraries
        return []
    except Exception as e:
        logger.error(f"获取媒体库失败: {e}")
        return []


def get_library_items(library_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """获取媒体库内的媒体项"""
    try:
        params = {
            "ParentId": library_id,
            "Recursive": "true",
            "Fields": "PrimaryImageAspectRatio,BasicSyncInfo,ProductionYear",
            "ImageTypeLimit": "1",
            "EnableImageTypes": "Primary,Thumb",
            "Limit": limit
        }
        res = media_api.get("/Items", params=params, timeout=10)
        if res.status_code == 200:
            data = res.json()
            items = data.get("Items", [])
            return [
                {
                    "id": item.get("Id"),
                    "name": item.get("Name"),
                    "type": item.get("Type"),
                    "year": item.get("ProductionYear"),
                    "has_image": item.get("ImageTags", {}).get("Primary") is not None
                }
                for item in items
            ]
        return []
    except Exception as e:
        logger.error(f"获取媒体项失败: {e}")
        return []


def get_series_items(library_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """获取媒体库内的剧集（Series），而非集（Episode）"""
    try:
        params = {
            "ParentId": library_id,
            "Recursive": "true",
            "IncludeItemTypes": "Series,Movie",
            "Fields": "PrimaryImageAspectRatio,BasicSyncInfo,ProductionYear",
            "ImageTypeLimit": "1",
            "EnableImageTypes": "Primary",
            "Limit": limit
        }
        res = media_api.get("/Items", params=params, timeout=10)
        if res.status_code == 200:
            data = res.json()
            items = data.get("Items", [])
            return [
                {
                    "id": item.get("Id"),
                    "name": item.get("Name"),
                    "type": item.get("Type"),
                    "year": item.get("ProductionYear"),
                    "has_image": item.get("ImageTags", {}).get("Primary") is not None
                }
                for item in items
            ]
        return []
    except Exception as e:
        logger.error(f"获取媒体项失败: {e}")
        return []


def get_item_image(item_id: str, image_type: str = "Primary", max_width: int = 1920) -> Optional[bytes]:
    """获取媒体项图片"""
    try:
        params = {"maxWidth": max_width}
        res = media_api.get(
            f"/Items/{item_id}/Images/{image_type}",
            params=params,
            timeout=10
        )
        if res.status_code == 200:
            return res.content
        return None
    except Exception as e:
        logger.error(f"获取图片失败 {item_id}: {e}")
        return None


def get_random_library_images(library_id: str, count: int = 9, 
                              image_type: str = "Primary",
                              rng: random.Random = None) -> List[bytes]:
    """随机获取媒体库图片（优先获取剧集封面，而非集封面）
    
    Args:
        library_id: 媒体库ID
        count: 需要的图片数量
        image_type: 图片类型
        rng: 随机数生成器（用于固定随机选择）
    """
    if rng is None:
        rng = random
    
    items = get_series_items(library_id, limit=100)
    
    items_with_images = [item for item in items if item.get("has_image")]
    
    if not items_with_images:
        items = get_library_items(library_id, limit=100)
        items_with_images = [item for item in items if item.get("has_image")]
    
    if not items_with_images:
        return []
    
    selected = rng.sample(items_with_images, min(count, len(items_with_images)))
    
    # 按选择顺序获取图片（非并发，保证顺序一致）
    images = []
    for item in selected:
        result = get_item_image(item["id"], image_type)
        if result:
            images.append(result)
    
    return images


def get_series_items_with_images(library_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """获取媒体库内的剧集/电影，包含图片信息"""
    try:
        params = {
            "ParentId": library_id,
            "Recursive": "true",
            "IncludeItemTypes": "Series,Movie",
            "Fields": "PrimaryImageAspectRatio,BasicSyncInfo,ProductionYear,ImageTags,ProviderIds,Overview",
            "ImageTypeLimit": "1",
            "EnableImageTypes": "Primary,Thumb,Banner",
            "Limit": limit
        }
        res = media_api.get("/Items", params=params, timeout=10)
        if res.status_code != 200:
            logger.error(f"获取媒体项失败: HTTP {res.status_code}")
            return []
        
        try:
            data = res.json()
        except Exception as e:
            logger.error(f"解析媒体项 JSON 失败: {e}")
            return []
        
        items = data.get("Items", [])
        return [
            {
                "id": item.get("Id"),
                "name": item.get("Name"),
                "type": item.get("Type"),
                "year": item.get("ProductionYear"),
                "image_tags": item.get("ImageTags", {}),
                "provider_ids": item.get("ProviderIds", {}),
                "overview": item.get("Overview", "")
            }
            for item in items
        ]
    except Exception as e:
        logger.error(f"获取媒体项失败: {e}")
        return []


def get_tmdb_backdrop(tmdb_id: str, media_type: str = "movie", rng: random.Random = None) -> Optional[bytes]:
    """从 TMDB 获取背景图（横版）- 仅在有代理时使用
    
    Args:
        tmdb_id: TMDB ID
        media_type: movie 或 tv
        rng: 随机数生成器（用于固定随机选择）
    """
    if rng is None:
        rng = random
    
    try:
        import requests
        from app.core.config import cfg
        
        proxy_url = cfg.get("proxy_url", "")
        if not proxy_url:
            return None
        
        proxies = {"http": proxy_url, "https": proxy_url}
        api_key = cfg.get("tmdb_api_key") or "b0754d4e5c3d4e5a8f9c1e2d3f4a5b6c"
        
        url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}/images?api_key={api_key}"
        res = requests.get(url, timeout=2, proxies=proxies)
        if res.status_code != 200:
            return None
        
        try:
            data = res.json()
        except:
            return None
        
        backdrops = data.get("backdrops", [])
        if not backdrops:
            return None
        
        backdrop = rng.choice(backdrops)  # 🔥 使用传入的随机数生成器
        file_path = backdrop.get("file_path")
        if not file_path:
            return None
        
        img_url = f"https://image.tmdb.org/t/p/w1280{file_path}"
        img_res = requests.get(img_url, timeout=3, proxies=proxies)
        if img_res.status_code == 200:
            return img_res.content
        return None
    except Exception:
        return None


def get_random_library_thumbs(library_id: str, count: int = 9, 
                              rng: random.Random = None) -> List[bytes]:
    """随机获取媒体库横版封面，用于横版布局风格
    
    Args:
        library_id: 媒体库ID
        count: 需要的图片数量
        rng: 随机数生成器（用于固定随机选择）
    """
    if rng is None:
        rng = random
    
    items = get_series_items_with_images(library_id, limit=100)
    
    if not items:
        return []
    
    rng.shuffle(items)
    
    def fetch_image_for_item(item):
        """获取单个项目的横版图片"""
        image_tags = item.get("image_tags", {})
        item_id = item.get("id")
        provider_ids = item.get("provider_ids", {})
        media_type = "tv" if item.get("type") == "Series" else "movie"
        
        # 1. 优先尝试 Thumb
        if image_tags.get("Thumb"):
            img_data = get_item_image(item_id, "Thumb", max_width=1920)
            if img_data:
                return img_data
        
        # 2. 尝试 Banner
        if image_tags.get("Banner"):
            img_data = get_item_image(item_id, "Banner", max_width=1920)
            if img_data:
                return img_data
        
        # 3. 尝试从 TMDB 获取背景图
        tmdb_id = provider_ids.get("Tmdb") or provider_ids.get("TMDB")
        if tmdb_id:
            img_data = get_tmdb_backdrop(tmdb_id, media_type, rng=rng)  # 🔥 传递 rng
            if img_data:
                return img_data
        
        # 4. 最后降级：裁剪 Primary 为横版
        if image_tags.get("Primary"):
            img_data = get_item_image(item_id, "Primary", max_width=1920)
            if img_data:
                try:
                    from PIL import Image
                    import io
                    img = Image.open(io.BytesIO(img_data))
                    target_w, target_h = 1920, 1080
                    new_h = int(img.width * 9 / 16)
                    if new_h <= img.height:
                        top = (img.height - new_h) // 2
                        img = img.crop((0, top, img.width, top + new_h))
                        img = img.resize((target_w, target_h), Image.LANCZOS)
                        buf = io.BytesIO()
                        img.save(buf, format='JPEG', quality=90)
                        return buf.getvalue()
                except:
                    pass
        return None
    
    # 按顺序获取图片（非并发，保证顺序一致）
    images = []
    for item in items[:count*3]:
        if len(images) >= count:
            break
        result = fetch_image_for_item(item)
        if result:
            images.append(result)
    
    return images


def get_library_info(library_id: str) -> Optional[Dict[str, Any]]:
    """获取媒体库详情"""
    try:
        res = media_api.get(f"/Library/VirtualFolders", timeout=10)
        if res.status_code == 200:
            for lib in res.json():
                if lib.get("ItemId") == library_id or lib.get("Id") == library_id:
                    return {
                        "id": library_id,
                        "name": lib.get("Name", "未命名"),
                        "collection_type": lib.get("CollectionType", "unknown"),
                        "item_count": lib.get("ItemCount", 0)
                    }
        return None
    except Exception as e:
        logger.error(f"获取媒体库信息失败: {e}")
        return None


def get_library_stats(library_id: str) -> Dict[str, Any]:
    """获取媒体库统计信息"""
    try:
        # 使用 get_series_items 统计，只统计 Series 和 Movie
        items = get_series_items(library_id, limit=1000)
        
        # 统计类型
        type_counts = {}
        years = []
        
        for item in items:
            item_type = item.get("type", "Unknown")
            type_counts[item_type] = type_counts.get(item_type, 0) + 1
            if item.get("year"):
                years.append(item["year"])
        
        
        return {
            "total": len(items),
            "types": type_counts,
            "years": sorted(set(years), reverse=True)[:10]
        }
    except Exception as e:
        logger.error(f"获取统计信息失败: {e}")
        return {"total": 0, "types": {}, "years": []}
