from fastapi import APIRouter, Response, Request, Depends, HTTPException
from app.routers.auth import is_admin_user  # 🔒 引入管理员权限检查
from app.core.security import require_login  # 🔒 统一登录依赖
from app.core.config import cfg
from app.core.media_adapter import media_api  # 🔥 引入核心适配器
from app.utils.proxy_helper import get_safe_proxies  # 🔒 SSRF 安全代理读取
import requests
import urllib.parse
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import re
import os
import hashlib
import time

# 初始化日志
logger = logging.getLogger("uvicorn")
router = APIRouter()

# 🔥 保留一个专门用于外部请求 (如 TMDB) 的 Session
ext_session = requests.Session()
retries = Retry(total=2, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
ext_session.mount('http://', HTTPAdapter(max_retries=retries, pool_connections=100, pool_maxsize=100))
ext_session.mount('https://', HTTPAdapter(max_retries=retries, pool_connections=100, pool_maxsize=100))

# 图片 ID 映射缓存（限制大小，避免内存泄漏）
smart_image_cache = {}
SMART_IMAGE_CACHE_MAX_SIZE = 5000  # 最多缓存 5000 个映射

def _cleanup_smart_image_cache():
    """清理图片缓存，保留最近的条目"""
    global smart_image_cache
    if len(smart_image_cache) > SMART_IMAGE_CACHE_MAX_SIZE:
        # 保留最近的一半
        items = list(smart_image_cache.items())
        smart_image_cache = dict(items[-SMART_IMAGE_CACHE_MAX_SIZE // 2:])
        logger.debug(f"[图片缓存] 已清理，当前大小: {len(smart_image_cache)}")

# 🔥 图片缓存配置
IMAGE_CACHE_DIR = "/workspace/data/image_cache"
IMAGE_CACHE_MAX_AGE = 86400 * 7  # 7天过期
IMAGE_CACHE_MAX_SIZE = 500 * 1024 * 1024  # 最大 500MB

def ensure_cache_dir():
    """确保缓存目录存在"""
    if not os.path.exists(IMAGE_CACHE_DIR):
        os.makedirs(IMAGE_CACHE_DIR, exist_ok=True)

def get_cache_path(item_id: str, img_type: str, v: str = None) -> str:
    """获取缓存文件路径"""
    # 使用 item_id + img_type + v 生成唯一文件名
    key = f"{item_id}_{img_type}_{v or 'default'}"
    filename = hashlib.md5(key.encode()).hexdigest() + ".jpg"
    return os.path.join(IMAGE_CACHE_DIR, filename)

def get_cached_image(cache_path: str) -> tuple:
    """从缓存读取图片，返回 (content, content_type) 或 None"""
    try:
        if os.path.exists(cache_path):
            # 检查是否过期
            file_age = time.time() - os.path.getmtime(cache_path)
            if file_age > IMAGE_CACHE_MAX_AGE:
                try:
                    os.remove(cache_path)
                except:
                    pass
                return None
            
            with open(cache_path, 'rb') as f:
                content = f.read()
            
            # 写入元数据文件获取 content_type
            meta_path = cache_path + ".meta"
            content_type = "image/jpeg"
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, 'r') as f:
                        content_type = f.read().strip()
                except:
                    pass
            
            return (content, content_type)
    except Exception as e:
        logger.debug(f"读取图片缓存失败: {e}")
    return None

def save_cached_image(cache_path: str, content: bytes, content_type: str):
    """保存图片到缓存"""
    try:
        ensure_cache_dir()
        with open(cache_path, 'wb') as f:
            f.write(content)
        # 保存 content_type
        meta_path = cache_path + ".meta"
        with open(meta_path, 'w') as f:
            f.write(content_type)
    except Exception as e:
        logger.debug(f"保存图片缓存失败: {e}")

def cleanup_old_cache():
    """清理过期的缓存文件"""
    try:
        if not os.path.exists(IMAGE_CACHE_DIR):
            return
        
        # 检查总大小
        total_size = 0
        files = []
        for f in os.listdir(IMAGE_CACHE_DIR):
            if f.endswith('.jpg') or f.endswith('.meta'):
                path = os.path.join(IMAGE_CACHE_DIR, f)
                size = os.path.getsize(path)
                total_size += size
                files.append((path, os.path.getmtime(path), size))
        
        # 如果超过最大大小，删除最旧的文件
        if total_size > IMAGE_CACHE_MAX_SIZE:
            files.sort(key=lambda x: x[1])  # 按修改时间排序
            deleted_size = 0
            for path, mtime, size in files:
                if total_size - deleted_size <= IMAGE_CACHE_MAX_SIZE * 0.8:
                    break
                try:
                    os.remove(path)
                    deleted_size += size
                except:
                    pass
    except Exception as e:
        logger.debug(f"清理图片缓存失败: {e}")

def extract_season_number(name: str):
    """从名称中提取季号，例如 '唐朝诡事录 - 第 2 季' -> 2"""
    m = re.search(r'第\s*(\d+)\s*季', name)
    if m: return int(m.group(1))
    m2 = re.search(r'S0*(\d+)', name, re.I)
    if m2: return int(m2.group(1))
    return None

def get_real_image_id_robust(item_id: str):
    """智能 ID 转换（解决剧集封面变单集截图的问题）"""
    try:
        # 🚀 替换为 media_api
        res_a = media_api.get(f"/Items/{item_id}", params={"Fields": "SeriesId,ParentId,SeasonId"}, timeout=3)
        if res_a.status_code == 200:
            data = res_a.json()
            if data.get("Type") == "Episode":
                if data.get("SeasonId"): 
                    season_id = data["SeasonId"]
                    s_res = media_api.get(f"/Items/{season_id}", timeout=2)
                    if s_res.status_code == 200 and s_res.json().get("ImageTags", {}).get("Primary"):
                        return season_id
                if data.get("SeriesId"): return data['SeriesId']
                
            if data.get("SeriesId"): return data['SeriesId']
            if data.get("Type") == "Episode" and data.get("ParentId"): return data['ParentId']
    except Exception: pass

    try:
        res_b = media_api.get(f"/Items/{item_id}/Ancestors", timeout=3)
        if res_b.status_code == 200:
            for ancestor in res_b.json():
                if ancestor.get("Type") == "Series": return ancestor['Id']
                if ancestor.get("Type") == "Season" and not ancestor.get("SeriesId"): return ancestor['Id']
    except Exception: pass

    try:
        res_c = media_api.get("/Items", params={"Ids": item_id, "Fields": "SeriesId", "Recursive": "true"}, timeout=3)
        if res_c.status_code == 200:
            items = res_c.json().get("Items", [])
            if items and items[0].get("SeriesId"): return items[0]['SeriesId']
    except Exception: pass

    return item_id

# 🔒 合法的 Emby 图片类型白名单（防止 img_type 路径逃逸到非图片端点）
ALLOWED_IMG_TYPES = {"Primary", "Backdrop", "Thumb", "Banner", "Logo", "Art", "Disc", "Box", "Menu"}

@router.get("/api/proxy/image/{item_id}/{img_type}")
def proxy_image(item_id: str, img_type: str, request: Request, v: str = None, nocache: bool = False, _user: dict = Depends(require_login)):
    """
    图片代理接口
    - v: 版本参数，当图片更新时改变此参数可强制刷新缓存
    - nocache: 是否跳过后端缓存，直接请求新图片
    - 缓存策略：后端缓存7天 + 浏览器缓存1年
    """
    # 🔒 img_type 白名单校验，防止路径逃逸至 Emby 其他端点（兼容大小写）
    img_type = img_type.capitalize()
    if img_type not in ALLOWED_IMG_TYPES:
        return Response(status_code=400)
    # 🔒 item_id 严格字符集校验（GUID/UUID/数字）
    if not item_id or not all(c.isalnum() or c == '-' for c in item_id) or len(item_id) > 64:
        return Response(status_code=400)
    # 防盗链：Referer 检查（记录但不阻断）
    referer = request.headers.get("referer", "")

    # 🔥 先尝试从后端缓存读取（除非指定 nocache）
    cache_path = get_cache_path(item_id, img_type, v)
    if not nocache:
        cached = get_cached_image(cache_path)
        if cached:
            content, content_type = cached
            cache_headers = {
                "Cache-Control": "public, max-age=31536000, immutable",
                "CDN-Cache-Control": "public, max-age=31536000",
                "X-Cache": "HIT"
            }
            if v:
                cache_headers["ETag"] = f'"{v}"'
            return Response(content=content, media_type=content_type, headers=cache_headers)
    
    try:
        target_id = get_real_image_id_robust(item_id) if img_type.lower() == 'primary' else item_id

        # 🚀 替换为 media_api，并透传 stream=True
        params = {"maxHeight": 600, "maxWidth": 400, "quality": 90}
        resp = media_api.get(f"/Items/{target_id}/Images/{img_type}", params=params, timeout=10, stream=True)

        if resp.status_code == 200:
            content = resp.content
            content_type = resp.headers.get("Content-Type", "image/jpeg")
            
            # 🔥 保存到后端缓存
            save_cached_image(cache_path, content, content_type)
            
            # 🔥 长期缓存：1年（31536000秒），配合 v 参数实现版本控制
            cache_headers = {
                "Cache-Control": "public, max-age=31536000, immutable",
                "CDN-Cache-Control": "public, max-age=31536000",
                "X-Cache": "MISS"
            }
            # 如果有版本参数，添加 ETag 支持
            if v:
                cache_headers["ETag"] = f'"{v}"'
            return Response(content=content, media_type=content_type, headers=cache_headers)

        if resp.status_code == 404 and target_id != item_id:
            fallback_resp = media_api.get(f"/Items/{item_id}/Images/{img_type}", params=params, timeout=10, stream=True)
            if fallback_resp.status_code == 200:
                content = fallback_resp.content
                content_type = fallback_resp.headers.get("Content-Type", "image/jpeg")
                
                # 🔥 保存到后端缓存
                save_cached_image(cache_path, content, content_type)
                
                cache_headers = {
                    "Cache-Control": "public, max-age=31536000, immutable",
                    "CDN-Cache-Control": "public, max-age=31536000",
                    "X-Cache": "MISS"
                }
                if v:
                    cache_headers["ETag"] = f'"{v}"'
                return Response(content=content, media_type=content_type, headers=cache_headers)
    except Exception: pass
    return Response(status_code=404)

@router.get("/api/proxy/smart_image")
def proxy_smart_image(request: Request, item_id: str, name: str = "", year: str = "", type: str = "Primary", _user: dict = Depends(require_login)):
    # 参数验证
    if not item_id or item_id == "undefined" or item_id == "null":
        return Response(status_code=404)
    # 1. 缓存拦截 (外部链接仍使用 ext_session)
    cached_result = smart_image_cache.get(item_id)
    if cached_result and str(cached_result).startswith('http'):
        try:
            proxies = get_safe_proxies()
            resp = ext_session.get(cached_result, proxies=proxies, timeout=10, stream=True)
            if resp.status_code == 200:
                return Response(content=resp.content, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})
        except Exception as e:
            logger.error(f"从缓存获取 TMDB 图片失败: {e}")
            pass 

    target_id = cached_result if cached_result and not str(cached_result).startswith('http') else item_id
    img_type = type.capitalize()
    params = {"maxWidth": 1920, "quality": 80} if img_type.lower() == 'backdrop' else {"maxHeight": 800, "maxWidth": 600, "quality": 90}
    
    if img_type.lower() == 'primary' and target_id == item_id:
        target_id = get_real_image_id_robust(target_id)
        
    # 2. 第 1 级防御：正常请求媒体库 (使用 media_api)
    try:
        resp = media_api.get(f"/Items/{target_id}/Images/{img_type}", params=params, timeout=5, stream=True)
        if resp.status_code == 200:
            return Response(content=resp.content, media_type=resp.headers.get("Content-Type", "image/jpeg"), headers={"Cache-Control": "public, max-age=86400"})
    except requests.exceptions.RequestException as e: 
        logger.debug(f"媒体库图片请求超时或断开: {e}")

    # 3. 第 2 级防御：洗版名字搜索兜底 (使用 media_api)
    clean_name = name.split(' - ')[0].strip() if name else ""
    if clean_name:
        try:
            s_resp = media_api.get("/Items", params={"SearchTerm": clean_name, "IncludeItemTypes": "Movie,Series,Episode", "Recursive": "true"}, timeout=5)
            if s_resp.status_code == 200:
                items = s_resp.json().get("Items", [])
                if items:
                    new_id = items[0]["Id"]
                    if items[0]["Type"] in ["Episode", "Season", "Series"]:
                        new_id = get_real_image_id_robust(new_id)
                    smart_image_cache[item_id] = new_id 
                    _cleanup_smart_image_cache()
                    
                    n_resp = media_api.get(f"/Items/{new_id}/Images/{img_type}", params=params, timeout=5, stream=True)
                    if n_resp.status_code == 200:
                        return Response(content=n_resp.content, media_type=n_resp.headers.get("Content-Type", "image/jpeg"), headers={"Cache-Control": "public, max-age=86400"})
        except requests.exceptions.RequestException: pass

    # 4. 第 3 级防御：TMDB 终极兜底 (外部请求，保留 ext_session)
    tmdb_key = cfg.get("tmdb_api_key")
    season_num = extract_season_number(name)

    if clean_name and tmdb_key:
        try:
            proxies = get_safe_proxies()

            tmdb_url = f"https://api.themoviedb.org/3/search/multi?api_key={tmdb_key}&language=zh-CN&query={urllib.parse.quote(clean_name)}"
            t_resp = ext_session.get(tmdb_url, proxies=proxies, timeout=5)
            
            if t_resp.status_code == 200:
                results = t_resp.json().get("results", [])
                for res in results:
                    if res.get("media_type") == "tv" and season_num is not None and img_type.lower() == 'primary':
                        tv_id = res.get("id")
                        season_url = f"https://api.themoviedb.org/3/tv/{tv_id}/season/{season_num}?api_key={tmdb_key}&language=zh-CN"
                        s_resp = ext_session.get(season_url, proxies=proxies, timeout=5)
                        if s_resp.status_code == 200:
                            s_data = s_resp.json()
                            if s_data.get("poster_path"):
                                final_url = f"https://image.tmdb.org/t/p/w500{s_data['poster_path']}"
                                smart_image_cache[item_id] = final_url
                                _cleanup_smart_image_cache()
                                final_resp = ext_session.get(final_url, proxies=proxies, timeout=8, stream=True)
                                if final_resp.status_code == 200:
                                    return Response(content=final_resp.content, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})

                    if res.get("media_type") in ["movie", "tv"]:
                        img_path = res.get("backdrop_path") if img_type.lower() == 'backdrop' else res.get("poster_path")
                        if img_path:
                            tmdb_img_url = f"https://image.tmdb.org/t/p/w500{img_path}"
                            smart_image_cache[item_id] = tmdb_img_url 
                            
                            # 🔥 检查缓存大小
                            _cleanup_smart_image_cache()
                            
                            final_resp = ext_session.get(tmdb_img_url, proxies=proxies, timeout=8, stream=True)
                            if final_resp.status_code == 200:
                                return Response(content=final_resp.content, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})
                        break
        except requests.exceptions.RequestException as e:
            logger.error(f"TMDB 兜底网络异常 [{clean_name}]: {e}")
            
    return Response(status_code=404)

@router.get("/api/proxy/user_image/{user_id}")
def proxy_user_image(request: Request, user_id: str, tag: str = None, _user: dict = Depends(require_login)):
    """
    用户头像代理接口
    - tag: 图片版本标签，用于缓存控制
    - 缓存策略：长期缓存（1年）
    - 如果用户没有头像，返回默认头像（本地静态资源，避免泄露 IP 到第三方）
    """
    # 参数验证
    if not user_id or user_id == "undefined" or user_id == "null":
        return Response(status_code=404)
    try:
        params = {"width": 200, "height": 200, "mode": "Crop", "quality": 90}
        if tag: params["tag"] = tag
        # 🚀 替换为 media_api，缩短超时时间
        resp = media_api.get(f"/Users/{user_id}/Images/Primary", params=params, timeout=2, stream=True)
        if resp.status_code == 200:
            cache_headers = {
                "Cache-Control": "public, max-age=31536000, immutable",
                "CDN-Cache-Control": "public, max-age=31536000",
            }
            if tag:
                cache_headers["ETag"] = f'"{tag}"'
            return Response(content=resp.content, media_type=resp.headers.get("Content-Type", "image/jpeg"), headers=cache_headers)
        # 404 表示用户没有头像，返回默认头像（本地）
        elif resp.status_code == 404:
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url="/static/img/logo-app.png", status_code=302)
    except Exception:
        # 超时或连接失败，返回默认头像
        pass
    # 🔥 用户没有头像或请求失败时，返回本地默认头像，避免第三方泄露用户 IP
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/img/logo-app.png", status_code=302)

@router.post("/api/proxy/clear_cache")
def clear_image_cache(request: Request, item_ids: list = None):
    """
    清除图片缓存
    - item_ids: 指定要清除的媒体库 ID 列表，为空则清除所有
    """
    # 🔒 安全：需要登录
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request):
        return {"status": "error", "message": "未授权"}
    
    try:
        ensure_cache_dir()
        deleted_count = 0
        
        if item_ids:
            # 清除指定媒体库的缓存
            for item_id in item_ids:
                for f in os.listdir(IMAGE_CACHE_DIR):
                    # 缓存文件名是 md5(item_id_img_type_v)，需要匹配 item_id
                    # 简单处理：删除所有包含该 item_id hash 前缀的文件
                    for img_type in ['primary', 'backdrop', 'thumb', 'banner']:
                        for v in ['default', '']:
                            cache_path = get_cache_path(item_id, img_type, v)
                            if os.path.exists(cache_path):
                                os.remove(cache_path)
                                deleted_count += 1
                            meta_path = cache_path + ".meta"
                            if os.path.exists(meta_path):
                                os.remove(meta_path)
        else:
            # 清除所有缓存
            for f in os.listdir(IMAGE_CACHE_DIR):
                if f.endswith('.jpg') or f.endswith('.meta'):
                    path = os.path.join(IMAGE_CACHE_DIR, f)
                    os.remove(path)
                    deleted_count += 1
        
        logger.info(f"[图片缓存] 已清除 {deleted_count} 个缓存文件")
        return {"status": "success", "deleted_count": deleted_count}
    except Exception as e:
        logger.error(f"清除图片缓存失败: {e}")
        return {"status": "error", "message": str(e)}