"""
媒体库封面管理插件 (Pro 专享)
批量上传封面图片，智能匹配并应用到媒体库
"""
import os
import json
import logging
import base64
import time
import re
from datetime import datetime
from io import BytesIO
from fastapi import Request, UploadFile, File, Form
from typing import List, Optional
from app.plugins.base import PluginBase
from app.core.config import cfg
from app.core.media_adapter import media_api
from app.routers.auth import is_admin_user

logger = logging.getLogger("uvicorn")

# 封面存储目录
COVER_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "library_covers")


class LibraryCoverPlugin(PluginBase):
    id = "library_cover"
    name = "媒体库封面管理"
    description = "批量上传封面图片，智能匹配并应用到媒体库（Pro 专享）"
    icon = "fa-images"
    icon_color = "from-pink-500 to-rose-500"
    version = "1.0.0"
    author = "EmbyPulse"

    def __init__(self):
        super().__init__()
        self._setup_routes()
        self._ensure_dir()

    def _ensure_dir(self):
        """确保封面存储目录存在"""
        os.makedirs(COVER_DIR, exist_ok=True)
        # 确保映射文件存在
        mapping_file = os.path.join(COVER_DIR, "mappings.json")
        if not os.path.exists(mapping_file):
            with open(mapping_file, "w", encoding="utf-8") as f:
                json.dump({}, f)

    def _setup_routes(self):
        """注册插件 API 路由"""

        @self.router.get("/libraries")
        async def get_libraries(request: Request):
            """获取媒体库列表及当前封面"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            
            try:
                res = media_api.get("/Library/VirtualFolders", timeout=10)
                if res.status_code != 200:
                    return {"status": "error", "message": "获取媒体库失败"}
                
                libraries = []
                for lib in res.json():
                    lib_id = lib.get("ItemId") or lib.get("Id")
                    lib_name = lib.get("Name", "未命名")
                    
                    # 获取当前封面 - 使用代理 API 避免跨域
                    cover_url = None
                    if lib_id:
                        # 先检查是否有封面
                        cover_res = media_api.get(f"/Items/{lib_id}/Images/Primary", timeout=5)
                        if cover_res.status_code == 200:
                            # 使用代理 API，避免浏览器跨域问题
                            cover_url = f"/api/plugins/library_cover/emby_image/{lib_id}"
                    
                    libraries.append({
                        "id": lib_id,
                        "name": lib_name,
                        "cover_url": cover_url,
                        "collection_type": lib.get("CollectionType", "unknown"),
                        "item_count": lib.get("ItemCount", 0)
                    })
                
                return {"status": "success", "data": libraries}
            except Exception as e:
                logger.error(f"[媒体库封面] 获取媒体库失败: {e}")
                return {"status": "error", "message": str(e)}

        @self.router.get("/emby_image/{item_id}")
        async def get_emby_image(item_id: str):
            """代理获取 Emby 图片，避免浏览器跨域"""
            try:
                res = media_api.get(f"/Items/{item_id}/Images/Primary", timeout=10)
                if res.status_code == 200:
                    from fastapi.responses import Response
                    content_type = res.headers.get('Content-Type', 'image/jpeg')
                    return Response(content=res.content, media_type=content_type)
                else:
                    return {"status": "error", "message": "图片不存在"}
            except Exception as e:
                logger.error(f"[媒体库封面] 获取图片失败: {e}")
                return {"status": "error", "message": str(e)}

        @self.router.post("/upload")
        async def upload_cover(request: Request, file: UploadFile = File(...)):
            """上传单张封面图片"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            
            try:
                # 读取文件内容
                content = await file.read()
                if len(content) > 10 * 1024 * 1024:  # 10MB 限制
                    return {"status": "error", "message": "图片不能超过 10MB"}
                
                # 生成文件名
                original_name = file.filename or "cover.jpg"
                timestamp = int(time.time() * 1000)
                safe_name = re.sub(r'[^\w\-_\.]', '_', original_name)
                filename = f"{timestamp}_{safe_name}"
                filepath = os.path.join(COVER_DIR, filename)
                
                # 保存文件
                with open(filepath, "wb") as f:
                    f.write(content)
                
                # 获取图片尺寸（简单判断）
                width, height = 0, 0
                try:
                    from PIL import Image
                    import io
                    img = Image.open(io.BytesIO(content))
                    width, height = img.size
                except:
                    pass
                
                return {
                    "status": "success",
                    "data": {
                        "filename": filename,
                        "original_name": original_name,
                        "size": len(content),
                        "width": width,
                        "height": height,
                        "url": f"/api/plugins/library_cover/file/{filename}"
                    }
                }
            except Exception as e:
                logger.error(f"[媒体库封面] 上传失败: {e}")
                return {"status": "error", "message": str(e)}

        @self.router.post("/batch_upload")
        async def batch_upload_covers(request: Request, files: List[UploadFile] = File(...)):
            """批量上传封面图片"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            
            results = []
            for file in files:
                try:
                    content = await file.read()
                    if len(content) > 10 * 1024 * 1024:
                        results.append({
                            "filename": file.filename,
                            "status": "error",
                            "message": "图片超过 10MB"
                        })
                        continue
                    
                    timestamp = int(time.time() * 1000)
                    safe_name = re.sub(r'[^\w\-_\.]', '_', file.filename or "cover.jpg")
                    filename = f"{timestamp}_{safe_name}"
                    filepath = os.path.join(COVER_DIR, filename)
                    
                    with open(filepath, "wb") as f:
                        f.write(content)
                    
                    # 获取图片尺寸
                    width, height = 0, 0
                    try:
                        from PIL import Image
                        import io
                        img = Image.open(io.BytesIO(content))
                        width, height = img.size
                    except:
                        pass
                    
                    results.append({
                        "filename": filename,
                        "original_name": file.filename,
                        "status": "success",
                        "size": len(content),
                        "width": width,
                        "height": height,
                        "url": f"/api/plugins/library_cover/file/{filename}"
                    })
                except Exception as e:
                    results.append({
                        "filename": file.filename,
                        "status": "error",
                        "message": str(e)
                    })
            
            return {"status": "success", "data": results}

        @self.router.get("/files")
        async def list_uploaded_files(request: Request):
            """获取已上传的封面列表"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            
            try:
                files = []
                if os.path.exists(COVER_DIR):
                    for f in sorted(os.listdir(COVER_DIR), reverse=True):
                        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')):
                            filepath = os.path.join(COVER_DIR, f)
                            stat = os.stat(filepath)
                            
                            # 获取图片尺寸
                            width, height = 0, 0
                            try:
                                from PIL import Image
                                img = Image.open(filepath)
                                width, height = img.size
                            except:
                                pass
                            
                            files.append({
                                "filename": f,
                                "size": stat.st_size,
                                "width": width,
                                "height": height,
                                "created_at": datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M"),
                                "url": f"/api/plugins/library_cover/file/{f}"
                            })
                
                return {"status": "success", "data": files}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        @self.router.get("/file/{filename}")
        async def get_cover_file(filename: str):
            """获取封面文件"""
            from fastapi.responses import FileResponse
            
            # 安全检查
            if ".." in filename or "/" in filename or "\\" in filename:
                return {"status": "error", "message": "无效文件名"}
            
            filepath = os.path.join(COVER_DIR, filename)
            if not os.path.exists(filepath):
                return {"status": "error", "message": "文件不存在"}
            
            return FileResponse(filepath)

        @self.router.delete("/file/{filename}")
        async def delete_cover_file(filename: str, request: Request):
            """删除封面文件"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            
            # 安全检查
            if ".." in filename or "/" in filename or "\\" in filename:
                return {"status": "error", "message": "无效文件名"}
            
            filepath = os.path.join(COVER_DIR, filename)
            if os.path.exists(filepath):
                os.remove(filepath)
            
            return {"status": "success", "message": "删除成功"}

        @self.router.post("/clear")
        async def clear_covers(request: Request):
            """清空所有已上传的封面"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            
            try:
                if os.path.exists(COVER_DIR):
                    for f in os.listdir(COVER_DIR):
                        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')):
                            os.remove(os.path.join(COVER_DIR, f))
                return {"status": "success", "message": "已清空"}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        @self.router.post("/reset")
        async def reset_cover(request: Request):
            """恢复媒体库默认封面（删除自定义封面）"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            
            try:
                data = await request.json()
                library_id = data.get("library_id")
                library_name = data.get("library_name")
                
                if not library_id:
                    return {"status": "error", "message": "缺少媒体库ID"}
                
                # 检查 Pro 授权
                if not self._is_pro():
                    return {"status": "error", "message": "此功能需要 Pro 授权", "need_pro": True}
                
                # 删除封面
                try:
                    del_res = media_api.delete(f"/Items/{library_id}/Images/Primary", timeout=10)
                    logger.info(f"[媒体库封面] 删除封面: {library_id}, status={del_res.status_code}")
                    
                    if del_res.status_code in [200, 204]:
                        self.log(f"✅ 已恢复默认封面: {library_name or library_id}")
                        return {"status": "success", "message": f"已恢复 {library_name or library_id} 的默认封面"}
                    else:
                        return {"status": "error", "message": f"删除封面失败: {del_res.status_code}"}
                except Exception as e:
                    logger.error(f"[媒体库封面] 删除封面失败: {e}")
                    return {"status": "error", "message": str(e)}
                    
            except Exception as e:
                logger.error(f"[媒体库封面] 恢复默认封面失败: {e}")
                return {"status": "error", "message": str(e)}

        @self.router.post("/apply")
        async def apply_cover(request: Request):
            """应用封面到媒体库"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            
            try:
                data = await request.json()
                library_id = data.get("library_id")
                library_name = data.get("library_name")
                cover_filename = data.get("cover_filename")
                
                if not library_id or not cover_filename:
                    return {"status": "error", "message": "缺少参数"}
                
                # 检查 Pro 授权
                if not self._is_pro():
                    return {"status": "error", "message": "此功能需要 Pro 授权", "need_pro": True}
                
                cover_path = os.path.join(COVER_DIR, cover_filename)
                if not os.path.exists(cover_path):
                    return {"status": "error", "message": "封面文件不存在"}
                
                # 读取图片
                with open(cover_path, "rb") as f:
                    image_data = f.read()
                
                # 确定图片类型和扩展名
                content_type = "image/jpeg"
                ext = "jpg"
                if cover_filename.lower().endswith(".png"):
                    content_type = "image/png"
                    ext = "png"
                elif cover_filename.lower().endswith(".webp"):
                    content_type = "image/webp"
                    ext = "webp"
                elif cover_filename.lower().endswith(".gif"):
                    content_type = "image/gif"
                    ext = "gif"
                
                # Emby/Jellyfin 上传媒体库封面
                # 方式1: 通过 Items/{id}/Images/Primary 上传
                applied = False
                try:
                    logger.info(f"[媒体库封面] 尝试上传封面到 {library_name} (id={library_id}), 大小={len(image_data)}bytes, ext={ext}")
                    
                    # 方式1: 使用 POST /Items/{id}/Images/Primary 格式
                    # Emby 需要 Base64 编码的数据作为请求体，Content-Type 需要是图片类型
                    # 参考 MoviePilot 的 medialibcovers 插件实现
                    image_b64 = base64.b64encode(image_data).decode('utf-8')
                    res = media_api.post(
                        f"/Items/{library_id}/Images/Primary",
                        data=image_b64,
                        headers={"Content-Type": content_type},
                        timeout=30
                    )
                    
                    logger.info(f"[媒体库封面] Base64 上传响应: {library_name} status={res.status_code}")
                    if res.status_code not in [200, 204]:
                        logger.warning(f"[媒体库封面] 响应内容: {res.text[:500] if res.text else '(empty)'}")
                    
                    if res.status_code in [200, 204]:
                        self.log(f"✅ 成功应用封面到媒体库: {library_name or library_id}")
                        applied = True
                        
                except Exception as e:
                    logger.warning(f"[媒体库封面] Items API 上传失败: {e}")
                
                # 方式2: 通过 VirtualFolders API 更新
                try:
                    # 获取媒体库信息
                    vf_res = media_api.get("/Library/VirtualFolders", timeout=10)
                    if vf_res.status_code == 200:
                        vf_data = vf_res.json()
                        for vf in vf_data:
                            if vf.get("ItemId") == library_id or vf.get("Id") == library_id:
                                # 更新媒体库选项
                                options = vf.get("LibraryOptions", {}) or {}
                                # 设置封面图片路径
                                options["PrimaryImagePath"] = cover_path
                                
                                update_data = {
                                    "Id": library_id,
                                    "Name": vf.get("Name"),
                                    "LibraryOptions": options
                                }
                                
                                update_res = media_api.post(
                                    "/Library/VirtualFolders/LibraryOptions",
                                    json=update_data,
                                    timeout=30
                                )
                                
                                if update_res.status_code in [200, 204]:
                                    self.log(f"✅ 成功应用封面到媒体库(方式2): {library_name or library_id}")
                                    return {"status": "success", "message": f"封面已应用到 {library_name or library_id}"}
                                break
                except Exception as e:
                    logger.error(f"[媒体库封面] VirtualFolders API 失败: {e}")
                
                logger.error(f"[媒体库封面] 所有上传方式都失败")
                return {"status": "error", "message": "上传封面失败，请检查媒体服务器 API"}
                
            except Exception as e:
                logger.error(f"[媒体库封面] 应用失败: {e}")
                return {"status": "error", "message": str(e)}

        @self.router.post("/batch_apply")
        async def batch_apply_covers(request: Request):
            """批量应用封面到多个媒体库"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            
            try:
                data = await request.json()
                mappings = data.get("mappings", [])  # [{library_id, library_name, cover_filename}, ...]
                
                if not mappings:
                    return {"status": "error", "message": "无映射数据"}
                
                # 检查 Pro 授权
                if not self._is_pro():
                    return {"status": "error", "message": "此功能需要 Pro 授权", "need_pro": True}
                
                success_count = 0
                fail_count = 0
                results = []
                
                for mapping in mappings:
                    library_id = mapping.get("library_id")
                    library_name = mapping.get("library_name", library_id)
                    cover_filename = mapping.get("cover_filename")
                    
                    if not library_id or not cover_filename:
                        fail_count += 1
                        results.append({"library_name": library_name, "success": False, "message": "缺少参数"})
                        continue
                    
                    cover_path = os.path.join(COVER_DIR, cover_filename)
                    if not os.path.exists(cover_path):
                        fail_count += 1
                        results.append({"library_name": library_name, "success": False, "message": "封面文件不存在"})
                        continue
                    
                    try:
                        with open(cover_path, "rb") as f:
                            image_data = f.read()
                        
                        # 确定图片类型和扩展名
                        content_type = "image/jpeg"
                        ext = "jpg"
                        if cover_filename.lower().endswith(".png"):
                            content_type = "image/png"
                            ext = "png"
                        elif cover_filename.lower().endswith(".webp"):
                            content_type = "image/webp"
                            ext = "webp"
                        elif cover_filename.lower().endswith(".gif"):
                            content_type = "image/gif"
                            ext = "gif"
                        
                        # 尝试方式1: 使用 Base64 编码上传
                        applied = False
                        try:
                            logger.info(f"[媒体库封面] 上传封面到 {library_name} (id={library_id}), 大小={len(image_data)}bytes, ext={ext}")
                            
                            # Emby 需要 Base64 编码的数据作为请求体，Content-Type 需要是图片类型
                            # 参考 MoviePilot 的 medialibcovers 插件实现
                            image_b64 = base64.b64encode(image_data).decode('utf-8')
                            res = media_api.post(
                                f"/Items/{library_id}/Images/Primary",
                                data=image_b64,
                                headers={"Content-Type": content_type},
                                timeout=30
                            )
                            logger.info(f"[媒体库封面] Base64 上传响应: {library_name} status={res.status_code}")
                            if res.status_code not in [200, 204]:
                                logger.warning(f"[媒体库封面] 响应内容: {res.text[:500] if res.text else '(empty)'}")
                            
                            if res.status_code in [200, 204]:
                                applied = True
                        except Exception as e:
                            logger.warning(f"[媒体库封面] 上传异常 {library_name}: {e}")
                        
                        # 如果方式1失败，尝试方式2: 刷新媒体库让 Emby 重新识别
                        if not applied:
                            try:
                                # 触发媒体库刷新
                                media_api.post(f"/Library/Refresh", params={"recursive": "false"}, timeout=10)
                            except:
                                pass
                        
                        if applied:
                            success_count += 1
                            results.append({"library_name": library_name, "success": True})
                            logger.info(f"[媒体库封面] ✅ 成功应用: {library_name}")
                        else:
                            fail_count += 1
                            results.append({"library_name": library_name, "success": False, "message": "上传失败"})
                            logger.warning(f"[媒体库封面] ❌ 应用失败: {library_name}")
                            
                    except Exception as e:
                        fail_count += 1
                        results.append({"library_name": library_name, "success": False, "message": str(e)})
                        logger.error(f"[媒体库封面] 异常: {library_name} - {e}")
                
                self.log(f"批量应用封面完成: 成功 {success_count}，失败 {fail_count}")
                return {
                    "status": "success",
                    "data": {
                        "success_count": success_count,
                        "fail_count": fail_count,
                        "results": results
                    },
                    "message": f"成功应用 {success_count} 个封面，失败 {fail_count} 个"
                }
            except Exception as e:
                logger.error(f"[媒体库封面] 批量应用失败: {e}")
                return {"status": "error", "message": str(e)}

        @self.router.post("/auto_match")
        async def auto_match_covers(request: Request):
            """根据文件名智能匹配封面到媒体库"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            
            try:
                # 获取媒体库列表
                res = media_api.get("/Library/VirtualFolders", timeout=10)
                if res.status_code != 200:
                    return {"status": "error", "message": "获取媒体库失败"}
                
                libraries = []
                for lib in res.json():
                    lib_id = lib.get("ItemId") or lib.get("Id")
                    lib_name = lib.get("Name", "")
                    if lib_id and lib_name:
                        libraries.append({"id": lib_id, "name": lib_name})
                
                # 获取已上传的封面
                covers = []
                if os.path.exists(COVER_DIR):
                    for f in os.listdir(COVER_DIR):
                        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')):
                            covers.append(f)
                
                # 智能匹配
                from pypinyin import lazy_pinyin
                mappings = []
                matched_covers = set()
                
                for cover in covers:
                    # 提取文件名（不含扩展名）
                    cover_name = os.path.splitext(cover)[0]
                    # 去掉时间戳前缀
                    if '_' in cover_name and cover_name.split('_')[0].isdigit():
                        cover_name = '_'.join(cover_name.split('_')[1:])
                    
                    cover_name_lower = cover_name.lower()
                    cover_name_pinyin = ''.join(lazy_pinyin(cover_name)).lower()
                    
                    best_match = None
                    best_score = 0
                    
                    for lib in libraries:
                        lib_name_lower = lib["name"].lower()
                        lib_name_pinyin = ''.join(lazy_pinyin(lib["name"])).lower()
                        
                        # 计算匹配分数
                        score = 0
                        
                        # 精确匹配
                        if cover_name_lower == lib_name_lower:
                            score = 100
                        # 包含匹配
                        elif cover_name_lower in lib_name_lower or lib_name_lower in cover_name_lower:
                            score = 80
                        # 拼音匹配
                        elif cover_name_pinyin and lib_name_pinyin:
                            if cover_name_pinyin == lib_name_pinyin:
                                score = 90
                            elif cover_name_pinyin in lib_name_pinyin or lib_name_pinyin in cover_name_pinyin:
                                score = 70
                        
                        # 使用别名配置
                        config = self._get_config()
                        aliases_str = config.get("aliases", "")
                        for line in aliases_str.split('\n'):
                            if '=' in line:
                                parts = line.split('=', 1)
                                if len(parts) == 2:
                                    alias_names = [n.strip() for n in parts[1].split(',')]
                                    target_name = parts[0].strip().lower()
                                    if cover_name_lower in alias_names or cover_name_pinyin in [''.join(lazy_pinyin(n)).lower() for n in alias_names]:
                                        if target_name == lib_name_lower or target_name == lib_name_pinyin:
                                            score = 95
                        
                        if score > best_score:
                            best_score = score
                            best_match = lib
                    
                    if best_match and best_score >= 50:
                        mappings.append({
                            "library_id": best_match["id"],
                            "library_name": best_match["name"],
                            "cover_filename": cover,
                            "cover_url": f"/api/plugins/library_cover/file/{cover}",
                            "match_score": best_score
                        })
                        matched_covers.add(cover)
                
                # 未匹配的封面
                unmatched_covers = [c for c in covers if c not in matched_covers]
                
                return {
                    "status": "success",
                    "data": {
                        "mappings": mappings,
                        "unmatched_covers": unmatched_covers,
                        "libraries": libraries
                    }
                }
            except Exception as e:
                logger.error(f"[媒体库封面] 自动匹配失败: {e}")
                return {"status": "error", "message": str(e)}

        @self.router.get("/mappings")
        async def get_mappings(request: Request):
            """获取已保存的映射关系"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            
            try:
                mapping_file = os.path.join(COVER_DIR, "mappings.json")
                if os.path.exists(mapping_file):
                    with open(mapping_file, "r", encoding="utf-8") as f:
                        mappings = json.load(f)
                else:
                    mappings = {}
                return {"status": "success", "data": mappings}
            except Exception as e:
                logger.error(f"[媒体库封面] 读取映射失败: {e}")
                return {"status": "error", "message": str(e)}

        @self.router.post("/mappings")
        async def save_mappings(request: Request):
            """保存映射关系"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            
            try:
                data = await request.json()
                mappings = data.get("mappings", {})
                
                mapping_file = os.path.join(COVER_DIR, "mappings.json")
                with open(mapping_file, "w", encoding="utf-8") as f:
                    json.dump(mappings, f, ensure_ascii=False, indent=2)
                
                return {"status": "success", "message": "映射已保存"}
            except Exception as e:
                logger.error(f"[媒体库封面] 保存映射失败: {e}")
                return {"status": "error", "message": str(e)}

        @self.router.post("/mappings/clear")
        async def clear_mappings(request: Request):
            """清空映射关系"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            
            try:
                mapping_file = os.path.join(COVER_DIR, "mappings.json")
                with open(mapping_file, "w", encoding="utf-8") as f:
                    json.dump({}, f)
                return {"status": "success", "message": "映射已清空"}
            except Exception as e:
                logger.error(f"[媒体库封面] 清空映射失败: {e}")
                return {"status": "error", "message": str(e)}

    def on_enable(self):
        self._ensure_dir()
        logger.info("🔌 [媒体库封面] 插件已启用")

    def on_disable(self):
        logger.info("🔌 [媒体库封面] 插件已禁用")

    def get_config_schema(self):
        return [
            {"key": "auto_match", "label": "自动匹配", "type": "toggle", "hint": "上传后自动根据文件名匹配媒体库"},
            {"key": "aliases", "label": "别名配置", "type": "textarea", 
             "placeholder": "电影=Movie,影片\n动漫=动画,Anime,animation\n剧集=TV,电视剧",
             "hint": "每行一个映射，格式：库名=别名1,别名2,别名3"},
            {"key": "notify_enabled", "label": "启用通知", "type": "toggle", "hint": "开启后，插件运行状态会发送到全局通知"},
        ]

    def get_page_url(self):
        return "/plugins/library_cover"

    def _is_pro(self):
        """检查 Pro 授权"""
        try:
            import sqlite3
            from app.core.database import SYSTEM_DB_PATH
            conn = sqlite3.connect(SYSTEM_DB_PATH)
            row = conn.execute("SELECT status FROM sys_license LIMIT 1").fetchone()
            conn.close()
            return row and row[0] == 'pro'
        except:
            return False
