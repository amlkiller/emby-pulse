"""
媒体库封面生成插件
自动为 Emby/Jellyfin 媒体库生成动态/静态封面
"""
import os
import io
import json
import logging
import base64
import time
import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import Request
from PIL import Image

from app.plugins.base import PluginBase
from app.core.config import cfg
from app.core.media_adapter import media_api

from .styles import get_style, list_all_styles, STATIC_STYLES
from .utils.image import load_image_from_bytes
from .utils.emby import (
    get_libraries, get_library_items, get_item_image,
    get_random_library_images, get_random_library_thumbs,
    get_library_info, get_library_stats
)
from .utils.font import get_font

logger = logging.getLogger("uvicorn")

# 封面输出目录
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "generated_covers")

# 预览缓存：存储预览生成的图片，应用时复用
_preview_cache: Dict[str, Dict[str, Any]] = {}


class CoverGeneratorPlugin(PluginBase):
    id = "cover_generator"
    name = "媒体库封面生成"
    description = "自动生成媒体库封面，4种精心设计的风格"
    icon = "fa-wand-magic-sparkles"
    icon_color = "from-purple-500 to-pink-500"
    version = "1.0.0"
    author = "EmbyPulse"

    def __init__(self):
        super().__init__()
        self._setup_routes()
        self._ensure_dir()

    def _ensure_dir(self):
        """确保输出目录存在"""
        os.makedirs(OUTPUT_DIR, exist_ok=True)

    def _setup_routes(self):
        """注册插件 API 路由"""

        @self.router.get("/styles")
        async def get_styles(request: Request):
            """获取所有风格列表"""
            return {"status": "success", "data": list_all_styles()}

        @self.router.get("/libraries")
        async def get_libraries_list(request: Request):
            """获取媒体库列表"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            
            libraries = get_libraries()
            
            # 添加统计信息
            for lib in libraries:
                try:
                    stats = get_library_stats(lib["id"])
                    lib["item_count"] = stats.get("total", 0)
                except:
                    lib["item_count"] = lib.get("item_count", 0)
            
            return {"status": "success", "data": libraries}

        @self.router.api_route("/library/{library_id}/preview", methods=["GET", "POST"])
        async def preview_library(request: Request, library_id: str, style: str = "style2", count: int = 9):
            """预览媒体库封面"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            
            # 支持 GET 和 POST
            bg_mode = "auto"
            bg_preset = 0
            bg_custom = None
            custom_title = ""
            custom_subtitle = ""
            seed = None  # 随机种子，用于固定图片选择
            title_color_mode = "white"
            title_color_custom = [255, 255, 255]
            font_size_mode = "medium"  # 字体大小模板：large/medium/small
            
            if request.method == "POST":
                try:
                    data = await request.json()
                    style = data.get("style", style)
                    count = data.get("count", count)
                    bg_mode = data.get("bg_mode", "auto")
                    bg_preset = data.get("bg_preset", 0)
                    bg_custom = data.get("bg_custom", None)
                    custom_title = data.get("title", "")
                    custom_subtitle = data.get("subtitle", "")
                    seed = data.get("seed")  # 获取种子
                    title_color_mode = data.get("title_color_mode", "white")
                    title_color_custom = data.get("title_color_custom", [255, 255, 255])
                    font_size_mode = data.get("font_size_mode", "medium")
                except:
                    pass
            
            try:
                # 获取媒体库信息
                lib_info = get_library_info(library_id)
                if not lib_info:
                    return {"status": "error", "message": "媒体库不存在"}
                
                # 生成或使用种子，创建独立的随机数生成器
                import random
                if seed is None:
                    seed = int(time.time() * 1000)
                rng = random.Random(seed)  # 🔥 使用独立的随机数生成器
                
                # 获取图片 - 斜线分割风格使用横版封面
                if style == "style2":
                    images_data = get_random_library_thumbs(library_id, count=1, rng=rng)  # 斜线分割只需1张
                else:
                    images_data = get_random_library_images(library_id, count=count, rng=rng)
                
                if not images_data:
                    return {"status": "error", "message": "无法获取媒体图片"}
                
                # 加载图片
                images = []
                for data in images_data:
                    img = load_image_from_bytes(data)
                    if img:
                        images.append(img)
                
                if not images:
                    return {"status": "error", "message": "图片加载失败"}
                
                # 确定标题和副标题
                title = custom_title if custom_title else lib_info["name"]
                
                # 获取更准确的统计数
                stats = get_library_stats(library_id)
                item_count = stats.get('total', 0) or lib_info.get('item_count', 0)
                
                if custom_subtitle:
                    subtitle = custom_subtitle
                else:
                    subtitle = f"共 {item_count} 部作品" if item_count > 0 else ""
                
                # 获取风格
                style_gen = get_style(style, {
                    "title": title,
                    "subtitle": subtitle,
                    "width": 1920,
                    "height": 1080,
                    "bg_mode": bg_mode,
                    "bg_preset": bg_preset,
                    "bg_custom": bg_custom,
                    "title_color_mode": title_color_mode,
                    "title_color_custom": title_color_custom,
                    "font_size_mode": font_size_mode
                })
                
                # 生成封面
                cover = style_gen.generate(images)
                
                # 转换为 base64
                buffer = io.BytesIO()
                cover.save(buffer, format="JPEG", quality=90)
                buffer.seek(0)
                img_base64 = base64.b64encode(buffer.read()).decode()
                
                # 缓存预览结果
                cache_key = f"{library_id}_{style}_{seed}"
                _preview_cache[cache_key] = {
                    "images": images_data,
                    "title": title,
                    "subtitle": subtitle,
                    "style": style,
                    "bg_mode": bg_mode,
                    "bg_preset": bg_preset,
                    "bg_custom": bg_custom,
                    "title_color_mode": title_color_mode,
                    "title_color_custom": title_color_custom,
                    "font_size_mode": font_size_mode,
                    "timestamp": time.time()
                }
                
                return {
                    "status": "success",
                    "data": {
                        "image": f"data:image/jpeg;base64,{img_base64}",
                        "library_name": lib_info["name"],
                        "style": style,
                        "seed": seed,
                        "cache_key": cache_key
                    }
                }
            except Exception as e:
                logger.error(f"[封面生成] 预览失败: {e}")
                return {"status": "error", "message": str(e)}

        @self.router.post("/generate")
        async def generate_cover(request: Request):
            """生成并应用封面到媒体库"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            
            try:
                data = await request.json()
                library_id = data.get("library_id")
                style = data.get("style", "style2")
                title = data.get("title", "")
                subtitle = data.get("subtitle", "")
                image_count = data.get("image_count", 9)
                cache_key = data.get("cache_key")  # 使用预览缓存
                seed = data.get("seed")  # 随机种子
                
                if not library_id:
                    return {"status": "error", "message": "缺少媒体库ID"}
                
                # 获取媒体库信息
                lib_info = get_library_info(library_id)
                if not lib_info:
                    return {"status": "error", "message": "媒体库不存在"}
                
                # 优先使用缓存的图片
                if cache_key and cache_key in _preview_cache:
                    cached = _preview_cache[cache_key]
                    images_data = cached["images"]
                    if not title:
                        title = cached.get("title", lib_info["name"])
                    if not subtitle:
                        subtitle = cached.get("subtitle", "")
                    style = cached.get("style", style)
                    # 🔥 从缓存恢复背景配置
                    if "bg_mode" not in data or not data.get("bg_mode"):
                        data["bg_mode"] = cached.get("bg_mode", "auto")
                    if "bg_preset" not in data or data.get("bg_preset") is None:
                        data["bg_preset"] = cached.get("bg_preset", 0)
                    if "bg_custom" not in data or not data.get("bg_custom"):
                        data["bg_custom"] = cached.get("bg_custom", None)
                    # 🔥 从缓存恢复标题颜色配置
                    if "title_color_mode" not in data or not data.get("title_color_mode"):
                        data["title_color_mode"] = cached.get("title_color_mode", "white")
                    if "title_color_custom" not in data or not data.get("title_color_custom"):
                        data["title_color_custom"] = cached.get("title_color_custom", [255, 255, 255])
                    # 🔥 从缓存恢复字体大小配置
                    if "font_size_mode" not in data or not data.get("font_size_mode"):
                        data["font_size_mode"] = cached.get("font_size_mode", "medium")
                else:
                    # 自动填充标题
                    if not title:
                        title = lib_info["name"]
                    if not subtitle:
                        stats = get_library_stats(library_id)
                        total = stats.get('total', 0)
                        subtitle = f"共 {total} 部作品" if total > 0 else ""
                    
                    # 使用种子固定随机选择，创建独立的随机数生成器
                    import random
                    if seed is None:
                        seed = int(time.time() * 1000)
                    rng = random.Random(seed)  # 🔥 使用独立的随机数生成器
                    
                    # 获取图片 - 斜线分割风格使用横版封面
                    if style == "style2":
                        images_data = get_random_library_thumbs(library_id, count=1, rng=rng)  # 斜线分割只需1张
                    else:
                        images_data = get_random_library_images(library_id, count=image_count, rng=rng)
                
                if not images_data:
                    return {"status": "error", "message": "无法获取媒体图片"}
                
                # 加载图片
                images = []
                for img_data in images_data:
                    img = load_image_from_bytes(img_data)
                    if img:
                        images.append(img)
                
                if not images:
                    return {"status": "error", "message": "图片加载失败"}
                
                # 获取风格
                style_gen = get_style(style, {
                    "title": title,
                    "subtitle": subtitle,
                    "width": 1920,
                    "height": 1080,
                    "bg_mode": data.get("bg_mode", "auto"),
                    "bg_preset": data.get("bg_preset", 0),
                    "bg_custom": data.get("bg_custom", None),
                    "title_color_mode": data.get("title_color_mode", "white"),
                    "title_color_custom": data.get("title_color_custom", [255, 255, 255]),
                    "font_size_mode": data.get("font_size_mode", "medium")
                })
                
                # 生成封面
                cover = style_gen.generate(images)
                
                # 保存
                timestamp = int(time.time() * 1000)
                output_filename = f"{library_id}_{timestamp}.jpg"
                output_path = os.path.join(OUTPUT_DIR, output_filename)
                cover.save(output_path, format="JPEG", quality=95)
                
                # 上传到 Emby
                with open(output_path, "rb") as f:
                    cover_data = f.read()
                
                image_b64 = base64.b64encode(cover_data).decode()
                upload_res = media_api.post(
                    f"/Items/{library_id}/Images/Primary",
                    data=image_b64,
                    headers={"Content-Type": "image/jpeg"},
                    timeout=60
                )
                
                if upload_res.status_code in [200, 204]:
                    self.log(f"✅ 成功生成并应用封面: {lib_info['name']} (风格: {style})")
                    return {
                        "status": "success",
                        "message": f"封面已应用到 {lib_info['name']}",
                        "data": {
                            "library_name": lib_info["name"],
                            "style": style,
                            "output_file": output_filename
                        }
                    }
                else:
                    logger.error(f"[封面生成] 上传失败: {upload_res.status_code}")
                    return {"status": "error", "message": f"上传封面失败: {upload_res.status_code}"}
                    
            except Exception as e:
                logger.error(f"[封面生成] 生成失败: {e}")
                return {"status": "error", "message": str(e)}


        @self.router.post("/batch_generate")
        async def batch_generate_covers(request: Request):
            """批量生成多个媒体库封面"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            
            data = await request.json()
            library_ids = data.get("library_ids", [])
            style = data.get("style", "style2")
            image_count = data.get("image_count", 9)
            
            if not library_ids:
                return {"status": "error", "message": "未选择媒体库"}
            
            results = []
            success_count = 0
            fail_count = 0
            
            for library_id in library_ids:
                try:
                    lib_info = get_library_info(library_id)
                    if not lib_info:
                        results.append({
                            "library_id": library_id,
                            "success": False,
                            "message": "媒体库不存在"
                        })
                        fail_count += 1
                        continue
                    
                    # 获取图片
                    images_data = get_random_library_images(library_id, count=image_count)
                    images = [load_image_from_bytes(d) for d in images_data if load_image_from_bytes(d)]
                    
                    if not images:
                        results.append({
                            "library_id": library_id,
                            "library_name": lib_info["name"],
                            "success": False,
                            "message": "无法获取图片"
                        })
                        fail_count += 1
                        continue
                    
                    # 生成封面
                    stats = get_library_stats(library_id)
                    style_gen = get_style(style, {
                        "title": lib_info["name"],
                        "subtitle": f"共 {stats['total']} 部作品",
                        "width": 1920,
                        "height": 1080
                    })
                    
                    cover = style_gen.generate(images)
                    
                    # 上传
                    buffer = io.BytesIO()
                    cover.save(buffer, format="JPEG", quality=95)
                    buffer.seek(0)
                    image_b64 = base64.b64encode(buffer.read()).decode()
                    
                    upload_res = media_api.post(
                        f"/Items/{library_id}/Images/Primary",
                        data=image_b64,
                        headers={"Content-Type": "image/jpeg"},
                        timeout=60
                    )
                    
                    if upload_res.status_code in [200, 204]:
                        results.append({
                            "library_id": library_id,
                            "library_name": lib_info["name"],
                            "success": True
                        })
                        success_count += 1
                    else:
                        results.append({
                            "library_id": library_id,
                            "library_name": lib_info["name"],
                            "success": False,
                            "message": f"上传失败: {upload_res.status_code}"
                        })
                        fail_count += 1
                        
                except Exception as e:
                    results.append({
                        "library_id": library_id,
                        "success": False,
                        "message": str(e)
                    })
                    fail_count += 1
            
            self.log(f"批量生成封面完成: 成功 {success_count}，失败 {fail_count}")
            return {
                "status": "success",
                "data": {
                    "success_count": success_count,
                    "fail_count": fail_count,
                    "results": results
                },
                "message": f"成功 {success_count} 个，失败 {fail_count} 个"
            }

        @self.router.get("/history")
        async def get_history(request: Request):
            """获取生成历史"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            
            try:
                files = []
                if os.path.exists(OUTPUT_DIR):
                    for f in sorted(os.listdir(OUTPUT_DIR), reverse=True)[:50]:
                        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                            filepath = os.path.join(OUTPUT_DIR, f)
                            stat = os.stat(filepath)
                            
                            # 解析文件名
                            parts = f.split('_')
                            library_id = parts[0] if parts else 'unknown'
                            
                            files.append({
                                "filename": f,
                                "library_id": library_id,
                                "size": stat.st_size,
                                "created_at": datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M"),
                                "url": f"/api/plugins/cover_generator/file/{f}",
                                "is_animated": f.lower().endswith('.gif')
                            })
                
                return {"status": "success", "data": files}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        @self.router.get("/file/{filename}")
        async def get_file(filename: str):
            """获取生成的封面文件"""
            from fastapi.responses import FileResponse
            
            if ".." in filename or "/" in filename or "\\" in filename:
                return {"status": "error", "message": "无效文件名"}
            
            filepath = os.path.join(OUTPUT_DIR, filename)
            if not os.path.exists(filepath):
                return {"status": "error", "message": "文件不存在"}
            
            return FileResponse(filepath)

    def on_enable(self):
        self._ensure_dir()
        logger.info("🔌 [封面生成] 插件已启用")

    def on_disable(self):
        logger.info("🔌 [封面生成] 插件已禁用")

    def get_config_schema(self):
        return [
            {"key": "default_style", "label": "默认风格", "type": "select", 
             "options": [{"value": s["id"], "label": s["name"]} for s in list_all_styles()],
             "default": "style2", "hint": "生成封面时默认使用的风格"},
            {"key": "image_count", "label": "图片数量", "type": "number", "default": 9,
             "hint": "从媒体库抓取的图片数量（九宫格建议9张）"},
            {"key": "auto_update", "label": "自动更新", "type": "toggle", "default": False,
             "hint": "媒体库内容变更时自动更新封面"},
            {"key": "notify_enabled", "label": "完成通知", "type": "toggle", "default": True,
             "hint": "生成完成后发送通知"},
        ]

    def get_page_url(self):
        return "/plugins/cover_generator"

    def _is_pro(self):
        """检查 Pro 授权"""
        return True

















