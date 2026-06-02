"""
剧集封面自动更新插件
当剧集有新季入库时，自动将主封面更新为最新季的海报
"""
import logging
import threading
import time
import datetime
import base64
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi import Request
from app.plugins.base import PluginBase
from app.domains.users.auth import is_admin_user  # 🔒 管理员鉴权
from app.core.event_bus import bus
from app.infra.clients.media_server_client import media_api
from app.plugins.season_poster_updater.season_poster_dao import (
    clear_plugin_logs,
    clear_season_poster_cache,
    clear_season_poster_logs,
    count_updated_series,
    ensure_season_poster_tables,
    get_cached_season_poster,
    list_season_poster_logs,
    save_cached_season_poster,
    save_season_poster_log,
)

logger = logging.getLogger("uvicorn")


class SeasonPosterUpdaterPlugin(PluginBase):
    id = "season_poster_updater"
    name = "剧集封面自动更新"
    description = "当剧集有新季入库时，自动将主封面更新为最新季的海报"
    icon = "fa-photo-film"
    icon_color = "from-teal-500 to-cyan-500"
    version = "1.0.0"
    author = "EmbyPulse"

    def __init__(self):
        super().__init__()
        self._subscribed = False
        self._setup_routes()
        self._ensure_db()

    def _ensure_db(self):
        """确保数据库表存在"""
        try:
            ensure_season_poster_tables()
        except Exception as e:
            logger.error(f"[{self.name}] 创建数据库表失败: {e}")

    def _setup_routes(self):
        """注册插件 API 路由"""

        @self.router.get("/status")
        async def get_status(request: Request):
            """获取插件状态"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            
            config = self._get_config()
            return {
                "status": "success",
                "data": {
                    "enabled": self.enabled,
                    "libraries": config.get("libraries", []),
                    "auto_update": config.get("auto_update", True),
                    "last_scan": config.get("last_scan", ""),
                    "total_updated": self._get_total_updated()
                }
            }

        @self.router.get("/libraries")
        async def get_libraries(request: Request):
            """获取媒体库列表"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            
            try:
                res = media_api.get("/Library/VirtualFolders", timeout=10)
                if res.status_code != 200:
                    return {"status": "error", "message": "获取媒体库失败"}
                
                config = self._get_config()
                # 处理 libraries 配置（可能是数组或逗号分隔字符串）
                selected_libraries = config.get("libraries", [])
                if isinstance(selected_libraries, str) and selected_libraries:
                    selected_libraries = [lib.strip() for lib in selected_libraries.split(',') if lib.strip()]
                
                libraries = []
                for lib in res.json():
                    lib_id = lib.get("ItemId") or lib.get("Id")
                    lib_name = lib.get("Name", "未命名")
                    collection_type = lib.get("CollectionType", "unknown")
                    
                    # 只显示剧集类型的媒体库
                    if collection_type in ["tvshows", "tv", "series"]:
                        # 获取剧集数量
                        item_count = 0
                        try:
                            count_res = media_api.get("/Items", params={
                                "ParentId": lib_id,
                                "IncludeItemTypes": "Series",
                                "Recursive": "true",
                                "Limit": 0
                            }, timeout=10)
                            if count_res.status_code == 200:
                                item_count = count_res.json().get("TotalRecordCount", 0)
                        except:
                            pass
                        
                        libraries.append({
                            "id": lib_id,
                            "name": lib_name,
                            "selected": lib_id in selected_libraries,
                            "item_count": item_count
                        })
                
                return {"status": "success", "data": libraries}
            except Exception as e:
                logger.error(f"[{self.name}] 获取媒体库失败: {e}")
                return {"status": "error", "message": str(e)}

        @self.router.post("/config")
        async def update_config(request: Request):
            """更新插件配置"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            
            try:
                from app.plugins import save_plugin_config
                data = await request.json()
                save_plugin_config(self.id, data)
                # 刷新配置缓存
                self._refresh_config_cache()
                return {"status": "success", "message": "配置已保存"}
            except Exception as e:
                logger.error(f"[{self.name}] 保存配置失败: {e}")
                return {"status": "error", "message": str(e)}

        @self.router.post("/scan")
        async def manual_scan(request: Request):
            """手动扫描所有剧集"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            
            try:
                result = await self._scan_all_series(force=False)
                return {"status": "success", "data": result}
            except Exception as e:
                logger.error(f"[{self.name}] 手动扫描失败: {e}")
                return {"status": "error", "message": str(e)}

        @self.router.post("/force_scan")
        async def force_scan(request: Request):
            """强制扫描所有剧集（忽略缓存）"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            
            try:
                result = await self._scan_all_series(force=True)
                return {"status": "success", "data": result}
            except Exception as e:
                logger.error(f"[{self.name}] 强制扫描失败: {e}")
                return {"status": "error", "message": str(e)}

        @self.router.get("/logs")
        async def get_logs(request: Request):
            """获取更新日志"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            
            try:
                rows = list_season_poster_logs(100)
                logs = []
                for row in rows:
                    logs.append({
                        "time": row["time"],
                        "series_name": row["series_name"],
                        "season_number": row["season_number"],
                        "old_poster": row["old_poster"],
                        "new_poster": row["new_poster"],
                        "success": bool(row["success"]),
                        "message": row["message"]
                    })
                
                return {"status": "success", "data": logs}
            except Exception as e:
                logger.error(f"[{self.name}] 获取日志失败: {e}")
                return {"status": "error", "message": str(e)}

        @self.router.post("/clear_logs")
        async def clear_logs(request: Request):
            """清空日志"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            
            try:
                clear_season_poster_logs()
                clear_plugin_logs(self.id)
                return {"status": "success", "message": "日志已清空"}
            except Exception as e:
                logger.error(f"[{self.name}] 清空日志失败: {e}")
                return {"status": "error", "message": str(e)}

    def on_enable(self):
        """启用插件"""
        self._ensure_db()
        # 订阅 webhook 事件
        if not self._subscribed:
            bus.subscribe("webhook.received", self._on_webhook_event)
            self._subscribed = True
        self.log("剧集封面自动更新插件已启用", notify=False)
        logger.info(f"🔌 [{self.name}] 插件已启用，已订阅 webhook 事件")

    def on_disable(self):
        """禁用插件"""
        if self._subscribed:
            bus.unsubscribe("webhook.received", self._on_webhook_event)
            self._subscribed = False
        self.log("剧集封面自动更新插件已禁用", notify=False)
        logger.info(f"🔌 [{self.name}] 插件已禁用")

    def get_config_schema(self):
        """配置项定义 - 全部在面板设置，不显示配置弹窗"""
        return []

    def _on_webhook_event(self, event: str, data: dict):
        """处理 Webhook 事件"""
        try:
            if not self._enabled:
                return
            # 只处理入库相关事件
            if event not in ["library.new", "item.added", "library.updated"]:
                return
            
            config = self._get_config()
            if not config.get("auto_update", True):
                return
            
            # 检查是否为剧集
            item = data.get("Item", {})
            item_type = item.get("Type", "").lower()
            
            # 如果是季或剧集，触发更新检查
            if item_type in ["season", "series", "episode"]:
                logger.info(f"[{self.name}] 检测到入库事件: {item.get('Name')} ({item_type})")
                # 异步处理，避免阻塞 webhook
                threading.Thread(target=self._process_series_update, args=(item,), daemon=True).start()
        except Exception as e:
            logger.error(f"[{self.name}] 处理 Webhook 事件失败: {e}")

    def _process_series_update(self, item: dict):
        """处理剧集更新"""
        try:
            # 获取剧集 ID
            series_id = item.get("SeriesId") or item.get("Id")
            if not series_id:
                return
            
            # 检查媒体库限制
            config = self._get_config()
            selected_libraries = config.get("libraries", [])
            # 处理 libraries 配置（可能是数组或逗号分隔字符串）
            if isinstance(selected_libraries, str) and selected_libraries:
                selected_libraries = [lib.strip() for lib in selected_libraries.split(',') if lib.strip()]
            
            if selected_libraries:
                # 获取剧集所属媒体库
                series_info = self._get_series_info(series_id)
                if not series_info:
                    return
                
                library_id = series_info.get("library_id")
                if library_id not in selected_libraries:
                    logger.debug(f"[{self.name}] 剧集不在选中的媒体库中: {series_info.get('name')}")
                    return
            
            # 执行封面更新
            self._update_series_poster(series_id)
        except Exception as e:
            logger.error(f"[{self.name}] 处理剧集更新失败: {e}")

    async def _scan_all_series(self, force: bool = False) -> dict:
        """扫描所有剧集 - 使用并发处理
        
        Args:
            force: 是否强制更新（忽略缓存）
        """
        config = self._get_config()
        selected_libraries = config.get("libraries", [])
        # 处理 libraries 配置（可能是数组或逗号分隔字符串）
        if isinstance(selected_libraries, str) and selected_libraries:
            selected_libraries = [lib.strip() for lib in selected_libraries.split(',') if lib.strip()]
        
        if not selected_libraries:
            return {"updated": 0, "skipped": 0, "errors": 0, "message": "未选择媒体库"}
        
        # 收集所有剧集
        all_series = []
        for library_id in selected_libraries:
            try:
                res = media_api.get("/Items", params={
                    "ParentId": library_id,
                    "IncludeItemTypes": "Series",
                    "Recursive": "true",
                    "Fields": "Overview"
                }, timeout=30)
                
                if res.status_code != 200:
                    logger.error(f"[{self.name}] 获取媒体库 {library_id} 剧集失败")
                    continue
                
                series_list = res.json().get("Items", [])
                logger.info(f"[{self.name}] 媒体库 {library_id} 共有 {len(series_list)} 部剧集")
                all_series.extend(series_list)
                
            except Exception as e:
                logger.error(f"[{self.name}] 扫描媒体库 {library_id} 失败: {e}")
        
        if not all_series:
            return {"updated": 0, "skipped": 0, "errors": 0, "message": "未找到剧集"}
        
        logger.info(f"[{self.name}] 开始并发处理 {len(all_series)} 部剧集{'(强制模式)' if force else ''}...")
        
        # 并发处理
        updated = 0
        skipped = 0
        errors = 0
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(self._update_series_poster, s.get("Id"), force): s for s in all_series}
            
            for future in as_completed(futures):
                series = futures[future]
                series_name = series.get("Name", "未知")
                
                try:
                    result = future.result()
                    if result == "updated":
                        updated += 1
                    elif result == "skipped":
                        skipped += 1
                    else:
                        errors += 1
                except Exception as e:
                    errors += 1
                    logger.error(f"[{self.name}] 处理 {series_name} 失败: {e}")
        
        # 更新最后扫描时间
        from app.plugins import save_plugin_config
        config["last_scan"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_plugin_config(self.id, config)
        
        return {
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
            "message": f"扫描完成：更新 {updated} 部，跳过 {skipped} 部，失败 {errors} 部"
        }

    def _update_series_poster(self, series_id: str, force: bool = False) -> str:
        """更新剧集主封面
        
        Args:
            series_id: 剧集ID
            force: 是否强制更新（忽略缓存）
        """
        try:
            # 获取剧集的所有季
            res = media_api.get("/Items", params={
                "ParentId": series_id,
                "IncludeItemTypes": "Season",
                "Recursive": "true",
                "SortBy": "SortName",
                "SortOrder": "Ascending"
            }, timeout=10)
            
            if res.status_code != 200:
                logger.error(f"[{self.name}] 获取剧集季列表失败: {series_id}")
                return "error"
            
            seasons = res.json().get("Items", [])
            if not seasons:
                logger.debug(f"[{self.name}] 剧集没有季: {series_id}")
                return "skipped"
            
            season_count = len(seasons)
            
            # 只有一季的剧集跳过
            if season_count < 2:
                logger.debug(f"[{self.name}] 剧集只有一季，跳过: {series_id}")
                return "skipped"
            
            # 从季信息中获取剧集名称
            series_name = ""
            for season in seasons:
                # 优先使用 SeriesName
                if season.get("SeriesName"):
                    series_name = season.get("SeriesName")
                    break
                # 备用：从季名称提取（如 "Season 1" -> 剧集名）
                season_name = season.get("Name", "")
                if season_name and not season_name.lower().startswith("season"):
                    series_name = season_name
                    break
            
            # 如果还是没有，尝试查询剧集信息
            if not series_name:
                try:
                    series_res = media_api.get("/Users/UserItems", params={"Ids": series_id}, timeout=5)
                    if series_res.status_code == 200:
                        items = series_res.json().get("Items", [])
                        if items:
                            series_name = items[0].get("Name", "")
                except Exception as e:
                    logger.debug(f"[{self.name}] 查询剧集信息失败: {e}")
            
            # 最后备用：使用 series_id
            if not series_name:
                series_name = f"剧集{series_id[:8]}"
                logger.debug(f"[{self.name}] 无法获取剧集名称，使用ID: {series_name}")
            
            # 找到最新的季（有海报的）
            latest_season = None
            latest_season_number = 0
            
            for season in reversed(seasons):  # 从后往前找最新的
                season_number = season.get("IndexNumber", 0)
                season_id = season.get("Id")
                
                # 检查季是否有海报
                poster_res = media_api.get(f"/Items/{season_id}/Images/Primary", timeout=5)
                if poster_res.status_code == 200:
                    latest_season = season
                    latest_season_number = season_number
                    break
            
            if not latest_season:
                logger.debug(f"[{self.name}] 剧集没有季海报: {series_name}")
                return "skipped"
            
            # 检查缓存（非强制更新时）
            if not force:
                cached = self._get_cached_series(series_id)
                if cached:
                    cached_season_count = cached.get("season_count", 0)
                    cached_last_season = cached.get("last_season_number", 0)
                    
                    # 季数未变且最新季号相同 -> 跳过
                    if cached_season_count == season_count and cached_last_season == latest_season_number:
                        logger.debug(f"[{self.name}] 剧集已处理且无新季，跳过: {series_name}")
                        return "skipped"
            
            # 检查是否需要更新（当前主封面是否已经是最新季的）
            current_poster_res = media_api.get(f"/Items/{series_id}/Images/Primary", timeout=5)
            if current_poster_res.status_code != 200:
                logger.debug(f"[{self.name}] 剧集没有主封面: {series_name}")
                return "skipped"
            
            # 获取最新季海报
            season_poster_res = media_api.get(f"/Items/{latest_season['Id']}/Images/Primary", timeout=10)
            if season_poster_res.status_code != 200:
                logger.error(f"[{self.name}] 获取季海报失败: {series_name} S{latest_season_number}")
                return "error"
            
            season_poster_data = season_poster_res.content
            
            # 上传为剧集主封面
            content_type = season_poster_res.headers.get('Content-Type', 'image/jpeg')
            image_b64 = base64.b64encode(season_poster_data).decode('utf-8')
            
            upload_res = media_api.post(
                f"/Items/{series_id}/Images/Primary",
                data=image_b64,
                headers={"Content-Type": content_type},
                timeout=30
            )
            
            if upload_res.status_code in [200, 204]:
                # 记录日志
                self._save_log(
                    series_id=series_id,
                    series_name=series_name,
                    season_number=latest_season_number,
                    old_poster="",
                    new_poster=f"Season {latest_season_number}",
                    success=True,
                    message=f"已更新为第 {latest_season_number} 季海报"
                )
                
                # 保存缓存
                self._save_cached_series(
                    series_id=series_id,
                    series_name=series_name,
                    season_count=season_count,
                    last_season_number=latest_season_number
                )
                
                self.log(f"✅ {series_name} → 第 {latest_season_number} 季", notify=False)
                return "updated"
            else:
                logger.error(f"[{self.name}] 上传海报失败: {series_name}, status={upload_res.status_code}")
                self._save_log(
                    series_id=series_id,
                    series_name=series_name,
                    season_number=latest_season_number,
                    old_poster="",
                    new_poster="",
                    success=False,
                    message=f"上传失败: HTTP {upload_res.status_code}"
                )
                return "error"
                
        except Exception as e:
            logger.error(f"[{self.name}] 更新剧集封面失败: {e}")
            return "error"

    def _get_series_info(self, series_id: str) -> dict:
        """获取剧集信息"""
        try:
            res = media_api.get(f"/Users/UserItems/{series_id}", timeout=5)
            if res.status_code != 200:
                return None
            
            data = res.json()
            return {
                "id": series_id,
                "name": data.get("Name", "未知"),
                "library_id": data.get("ParentId")
            }
        except:
            return None

    def _save_log(self, series_id: str, series_name: str, season_number: int, 
                  old_poster: str, new_poster: str, success: bool, message: str):
        """保存更新日志"""
        try:
            save_season_poster_log(
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                series_id,
                series_name,
                season_number,
                old_poster,
                new_poster,
                success,
                message,
            )
        except Exception as e:
            logger.error(f"[{self.name}] 保存日志失败: {e}")

    def _get_total_updated(self) -> int:
        """获取已更新的剧集数量"""
        try:
            return count_updated_series()
        except:
            return 0

    def _get_cached_series(self, series_id: str) -> dict:
        """获取已缓存的剧集信息"""
        try:
            row = get_cached_season_poster(series_id)
            if row:
                return {
                    "series_name": row["series_name"],
                    "season_count": row["season_count"],
                    "last_season_number": row["last_season_number"],
                    "last_updated": row["last_updated"]
                }
            return None
        except:
            return None

    def _save_cached_series(self, series_id: str, series_name: str, season_count: int, last_season_number: int):
        """保存剧集缓存信息"""
        try:
            save_cached_season_poster(
                series_id,
                series_name,
                season_count,
                last_season_number,
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
        except Exception as e:
            logger.error(f"[{self.name}] 保存缓存失败: {e}")

    def _clear_cache(self):
        """清空缓存（用于强制重新扫描）"""
        try:
            clear_season_poster_cache()
        except Exception as e:
            logger.error(f"[{self.name}] 清空缓存失败: {e}")
