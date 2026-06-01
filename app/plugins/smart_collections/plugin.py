"""
Emby 智能合集插件 (Pro 专享)
支持自定义合集管理、多种数据源、手动关联
"""
import time
import json
import logging
import threading
import datetime
from typing import Optional, List, Dict, Any
from fastapi import Request
from app.plugins.base import PluginBase
from app.domains.users.auth import is_admin_user  # 🔒 管理员鉴权
from app.infra.clients.media_server_client import media_api
from app.infra.config.media_server_settings import get_media_server_host
from app.dao.smart_collection_dao import (
    add_smart_collection_log,
    create_smart_collection,
    delete_smart_collection,
    ensure_smart_collection_tables,
    get_smart_collection,
    list_enabled_smart_collections,
    list_smart_collection_items,
    list_smart_collection_logs,
    list_smart_collections,
    replace_smart_collection_items,
    set_smart_collection_sync_state,
    update_smart_collection,
)
from app.infra.clients.tmdb_client import tmdb_client

logger = logging.getLogger("uvicorn")


def ensure_tables():
    """确保数据库表存在"""
    try:
        ensure_smart_collection_tables()
    except Exception as e:
        logger.error(f"[智能合集] 创建数据库表失败: {e}")


# 初始化表
ensure_tables()


class SmartCollectionsPlugin(PluginBase):
    """智能合集插件"""
    
    id = "smart_collections"
    name = "智能合集"
    description = "自定义合集管理，支持热播榜单、高分经典等多种类型（Pro 专享）"
    icon = "fa-layer-group"
    icon_color = "from-purple-500 to-pink-500"
    version = "2.0.0"
    author = "EmbyPulse"
    pro_only = True
    
    def __init__(self):
        super().__init__()
        self._sync_thread = None
        self._running = False
        self._setup_routes()
    
    def on_enable(self):
        self._running = True
        self._sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
        self._sync_thread.start()
        logger.info("🔌 [智能合集] 插件已启用")
    
    def on_disable(self):
        self._running = False
        logger.info("🔌 [智能合集] 插件已禁用")
    
    def get_config_schema(self):
        return [
            {"key": "sync_interval", "label": "同步间隔（小时）", "type": "number", "placeholder": "6", "hint": "每隔多少小时自动同步一次，默认6小时", "default": "6"},
            {"key": "auto_sync", "label": "启用自动同步", "type": "toggle", "hint": "自动同步已启用的合集", "default": True},
        ]
    
    # ==========================================
    # API 路由
    # ==========================================
    
    def _setup_routes(self):
        """注册 API 路由"""
        
        @self.router.get("/collections")
        def list_collections(request: Request):
            """获取所有合集"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            return self.get_all_collections()
        
        @self.router.get("/collection/{collection_id}")
        def get_collection(request: Request, collection_id: int):
            """获取单个合集详情"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            return self.get_collection_by_id(collection_id)
        
        @self.router.post("/collection")
        async def create_collection(request: Request):
            """创建合集"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            data = await request.json()
            return self.create_collection_item(data)
        
        @self.router.put("/collection/{collection_id}")
        async def update_collection(request: Request, collection_id: int):
            """更新合集"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            data = await request.json()
            return self.update_collection_item(collection_id, data)
        
        @self.router.delete("/collection/{collection_id}")
        def delete_collection(request: Request, collection_id: int):
            """删除合集"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            return self.delete_collection_item(collection_id)
        
        @self.router.post("/collection/{collection_id}/sync")
        def sync_collection(request: Request, collection_id: int):
            """手动同步合集"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            return self.sync_single_collection(collection_id)
        
        @self.router.post("/sync_all")
        def sync_all(request: Request):
            """同步所有合集"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            return self.sync_all_collections()
        
        @self.router.get("/logs")
        def get_logs(request: Request, limit: int = 50):
            """获取同步日志"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            return self.get_sync_logs(limit)
        
        @self.router.get("/source_types")
        def get_source_types(request: Request):
            """获取可用的数据源类型"""
            return {
                "status": "success",
                "data": [
                    {"value": "tmdb_movie_trending", "label": "📈 TMDB - 电影热播榜", "media_type": "movie"},
                    {"value": "tmdb_movie_top_rated", "label": "⭐ TMDB - 电影高分榜", "media_type": "movie"},
                    {"value": "tmdb_tv_trending", "label": "📈 TMDB - 剧集热播榜", "media_type": "tv"},
                    {"value": "tmdb_tv_top_rated", "label": "⭐ TMDB - 剧集高分榜", "media_type": "tv"},
                    {"value": "tmdb_anime_trending", "label": "📈 TMDB - 动漫热播榜", "media_type": "anime"},
                    {"value": "tmdb_anime_top_rated", "label": "⭐ TMDB - 动漫高分榜", "media_type": "anime"},
                    {"value": "emby_continuing", "label": "📺 Emby - 正在热播", "media_type": "tv"},
                    {"value": "emby_recent_added", "label": "🆕 Emby - 最近添加", "media_type": "all"},
                    {"value": "custom", "label": "📝 自定义列表", "media_type": "all"},
                    {"value": "tmdb_movie_top250", "label": "🏆 TMDB - 电影 Top250", "media_type": "movie"},
                    {"value": "tmdb_tv_top250", "label": "🏆 TMDB - 电视剧 Top250", "media_type": "tv"},
                ]
            }
        
        @self.router.get("/emby_items")
        def search_emby_items(request: Request, q: str = "", limit: int = 20):
            """搜索 Emby 媒体库项目"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            return self.search_items(q, limit)
    
    # ==========================================
    # 数据库操作
    # ==========================================
    
    def get_all_collections(self) -> dict:
        """获取所有合集"""
        try:
            rows = list_smart_collections()
            collections = []
            for row in rows:
                collections.append({
                    "id": row["id"],
                    "name": row["name"],
                    "icon": row["icon"],
                    "icon_color": row["icon_color"],
                    "source_type": row["source_type"],
                    "source_config": json.loads(row["source_config"] or "{}"),
                    "min_rating": row["min_rating"],
                    "update_mode": row["update_mode"],
                    "is_enabled": row["is_enabled"],
                    "last_sync": row["last_sync"],
                    "last_count": row["last_count"],
                    "item_count": row["item_count"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                })
            
            return {"status": "success", "data": collections}
        except Exception as e:
            logger.error(f"[智能合集] 获取合集列表失败: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_collection_by_id(self, collection_id: int) -> dict:
        """获取单个合集详情"""
        try:
            row = get_smart_collection(collection_id)
            if not row:
                return {"status": "error", "message": "合集不存在"}
            items = list_smart_collection_items(collection_id)
            
            collection = {
                "id": row["id"],
                "name": row["name"],
                "icon": row["icon"],
                "icon_color": row["icon_color"],
                "source_type": row["source_type"],
                "source_config": json.loads(row["source_config"] or "{}"),
                "min_rating": row["min_rating"],
                "update_mode": row["update_mode"],
                "is_enabled": row["is_enabled"],
                "last_sync": row["last_sync"],
                "last_count": row["last_count"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "items": [{"item_id": i["item_id"], "tmdb_id": i["tmdb_id"], "title": i["title"]} for i in items],
            }
            
            logger.info(f"[智能合集] 返回合集详情，min_rating={row['min_rating']}")
            
            return {"status": "success", "data": collection}
        except Exception as e:
            logger.error(f"[智能合集] 获取合集详情失败: {e}")
            return {"status": "error", "message": str(e)}
    
    def create_collection_item(self, data: dict) -> dict:
        """创建合集"""
        try:
            logger.info(f"[智能合集] 创建合集，收到数据: {data}")
            
            name = data.get("name", "").strip()
            if not name:
                return {"status": "error", "message": "合集名称不能为空"}
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"[智能合集] min_rating 值: {float(data.get('min_rating') if data.get('min_rating') is not None else 7.0)}")
            collection_id = create_smart_collection(data, now)
            self._add_sync_log(collection_id, "create", "success", f"创建合集: {name}")
            
            return {"status": "success", "data": {"id": collection_id}, "message": "合集创建成功"}
        except Exception as e:
            if "UNIQUE constraint failed" in str(e):
                return {"status": "error", "message": "合集名称已存在"}
            logger.error(f"[智能合集] 创建合集失败: {e}")
            return {"status": "error", "message": str(e)}
    
    def update_collection_item(self, collection_id: int, data: dict) -> dict:
        """更新合集"""
        try:
            logger.info(f"[智能合集] 更新合集 {collection_id}，收到数据: {data}")
            
            row = get_smart_collection(collection_id)
            if not row:
                return {"status": "error", "message": "合集不存在"}
            
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            min_rating = float(data.get("min_rating") if data.get("min_rating") is not None else 7.0)
            logger.info(f"[智能合集] min_rating 值: {min_rating}")
            update_smart_collection(collection_id, data, now)
            
            return {"status": "success", "message": "合集更新成功"}
        except Exception as e:
            logger.error(f"[智能合集] 更新合集失败: {e}")
            return {"status": "error", "message": str(e)}
    
    def delete_collection_item(self, collection_id: int) -> dict:
        """删除合集"""
        try:
            name = delete_smart_collection(collection_id)
            if not name:
                return {"status": "error", "message": "合集不存在"}
            
            # 删除 Emby 中的合集
            self._delete_emby_collection(name)
            
            self._add_sync_log(collection_id, "delete", "success", f"删除合集: {name}")
            
            return {"status": "success", "message": "合集已删除"}
        except Exception as e:
            logger.error(f"[智能合集] 删除合集失败: {e}")
            return {"status": "error", "message": str(e)}
    
    def search_items(self, query: str, limit: int = 20) -> dict:
        """搜索 Emby 媒体库项目"""
        try:
            admin_id = self._get_admin_id()
            if not admin_id:
                return {"status": "error", "message": "无法获取管理员ID"}
            
            params = {
                "SearchTerm": query,
                "Recursive": "true",
                "Limit": limit,
                "Fields": "ProviderIds,CommunityRating",
            }
            
            res = media_api.get(f"/Users/{admin_id}/Items", params=params, timeout=10)
            if res.status_code != 200:
                return {"status": "error", "message": "搜索失败"}
            
            items = []
            for item in res.json().get("Items", []):
                items.append({
                    "id": item["Id"],
                    "name": item["Name"],
                    "type": item.get("Type", ""),
                    "year": item.get("ProductionYear"),
                    "rating": item.get("CommunityRating"),
                    "tmdb_id": item.get("ProviderIds", {}).get("Tmdb"),
                    "poster": f"{get_media_server_host()}/Items/{item['Id']}/Images/Primary?maxHeight=200" if get_media_server_host() else None,
                })
            
            return {"status": "success", "data": items}
        except Exception as e:
            logger.error(f"[智能合集] 搜索失败: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_sync_logs(self, limit: int = 50) -> dict:
        """获取同步日志"""
        try:
            rows = list_smart_collection_logs(limit)
            logs = []
            for row in rows:
                logs.append({
                    "id": row["id"],
                    "collection_id": row["collection_id"],
                    "collection_name": row["collection_name"],
                    "action": row["action"],
                    "status": row["status"],
                    "message": row["message"],
                    "count": row["count"],
                    "created_at": row["created_at"],
                })
            
            return {"status": "success", "data": logs}
        except Exception as e:
            logger.error(f"[智能合集] 获取日志失败: {e}")
            return {"status": "error", "message": str(e)}
    
    def _add_sync_log(self, collection_id: int, action: str, status: str, message: str, count: int = 0):
        """添加同步日志"""
        try:
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            add_smart_collection_log(collection_id, action, status, message, count, now)
        except Exception as e:
            logger.error(f"[智能合集] 添加日志失败: {e}")
    
    # ==========================================
    # 同步逻辑
    # ==========================================
    
    def _get_config(self):
        from app.plugins import get_plugin_config
        return get_plugin_config(self.id)
    
    def _is_pro(self):
        return True
    
    def _sync_loop(self):
        """后台定时同步线程"""
        time.sleep(30)
        while self._running and self._enabled:
            if not self._is_pro():
                time.sleep(3600)
                continue
            
            config = self._get_config()
            if config.get("auto_sync", True):
                try:
                    self.sync_all_collections()
                except Exception as e:
                    logger.error(f"[智能合集] 自动同步失败: {e}")
            
            interval = max(1, int(config.get("sync_interval") or 6)) * 3600
            for _ in range(interval // 10):
                if not self._running or not self._enabled:
                    return
                time.sleep(10)
    
    def sync_all_collections(self) -> dict:
        """同步所有启用的合集"""
        if not self._is_pro():
            return {"status": "error", "message": "Pro 专享功能"}
        
        try:
            rows = list_enabled_smart_collections()
            
            total = 0
            for row in rows:
                result = self._sync_collection_from_row(row)
                total += result
            
            return {"status": "success", "message": f"同步完成，共更新 {total} 个项目"}
        except Exception as e:
            logger.error(f"[智能合集] 同步失败: {e}")
            return {"status": "error", "message": str(e)}
    
    def sync_single_collection(self, collection_id: int) -> dict:
        """同步单个合集"""
        if not self._is_pro():
            return {"status": "error", "message": "Pro 专享功能"}
        
        try:
            row = get_smart_collection(collection_id)
            if not row:
                return {"status": "error", "message": "合集不存在"}
            
            count = self._sync_collection_from_row(row)
            return {"status": "success", "message": f"同步完成，更新 {count} 个项目", "data": {"count": count}}
        except Exception as e:
            logger.error(f"[智能合集] 同步失败: {e}")
            return {"status": "error", "message": str(e)}
    
    def _sync_collection_from_row(self, row) -> int:
        """根据数据库行同步合集"""
        collection_id = row["id"]
        name = row["name"]
        source_type = row["source_type"]
        min_rating = row["min_rating"]
        update_mode = row["update_mode"]
        
        try:
            # 获取匹配的项目
            item_ids = self._fetch_source_items(source_type, min_rating, row)
            
            if not item_ids:
                self._add_sync_log(collection_id, "sync", "warning", f"{name}: 无匹配项")
                return 0
            
            # 更新 Emby 合集
            logger.info(f"[智能合集] {name}: 准备{'替换' if update_mode == 'replace' else '更新'} {len(item_ids)} 个项目")
            if update_mode == "replace":
                self._replace_emby_collection(name, item_ids)
            else:
                self._update_emby_collection(name, item_ids)
            
            # 更新数据库
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            set_smart_collection_sync_state(collection_id, now, len(item_ids))
            replace_smart_collection_items(collection_id, item_ids, now)
            
            self._add_sync_log(collection_id, "sync", "success", f"{name}: 匹配 {len(item_ids)} 个项目", len(item_ids))
            return len(item_ids)
        except Exception as e:
            logger.error(f"[智能合集] 同步 {name} 失败: {e}")
            self._add_sync_log(collection_id, "sync", "error", f"{name}: {str(e)}")
            return 0
    
    def _fetch_source_items(self, source_type: str, min_rating: float, row) -> List[str]:
        """从数据源获取项目 ID 列表"""
        admin_id = self._get_admin_id()
        if not admin_id:
            return []
        
        from app.utils.proxy_helper import get_safe_proxies
        proxies = get_safe_proxies()
        
        # 构建 TMDB ID → Emby Item ID 映射
        emby_tmdb_map = self._build_emby_tmdb_map(admin_id)
        
        # 根据数据源类型获取项目
        if source_type == "emby_continuing":
            return self._fetch_continuing_items(admin_id, min_rating)
        elif source_type == "emby_recent_added":
            return self._fetch_recent_added(admin_id, min_rating)
        elif source_type == "custom":
            # 自定义列表
            source_config = json.loads(row["source_config"] or "{}")
            return source_config.get("item_ids", [])
        elif source_type.startswith("tmdb_"):
            return self._fetch_tmdb_items(source_type, proxies, min_rating, emby_tmdb_map)
        
        return []
    
    def _fetch_tmdb_items(self, source_type: str, proxies: dict, min_rating: float, emby_tmdb_map: dict) -> List[str]:
        """从 TMDB 获取项目"""
        # TMDB Top250 需要分页获取
        if source_type == "tmdb_movie_top250":
            return self._fetch_tmdb_top250("movie", proxies, min_rating, emby_tmdb_map)
        elif source_type == "tmdb_tv_top250":
            return self._fetch_tmdb_top250("tv", proxies, min_rating, emby_tmdb_map)

        try:
            if source_type == "tmdb_movie_trending":
                res = tmdb_client.get_trending(media_type="movie", proxies=proxies, timeout=15)
            elif source_type == "tmdb_movie_top_rated":
                res = tmdb_client.get_top_rated("movie", proxies=proxies, timeout=15)
            elif source_type == "tmdb_tv_trending":
                res = tmdb_client.get_trending(media_type="tv", proxies=proxies, timeout=15)
            elif source_type == "tmdb_tv_top_rated":
                res = tmdb_client.get_top_rated("tv", proxies=proxies, timeout=15)
            elif source_type == "tmdb_anime_trending":
                res = tmdb_client.discover_tv(proxies=proxies, timeout=15, with_genres="16", sort_by="popularity.desc")
            elif source_type == "tmdb_anime_top_rated":
                res = tmdb_client.discover_tv(proxies=proxies, timeout=15, with_genres="16", sort_by="vote_average.desc", vote_count_gte=100)
            else:
                return []

            if res.status_code != 200:
                return []
            
            results = res.json().get("results", [])
            matched_ids = []
            
            for item in results:
                tmdb_id = str(item.get("id", ""))
                rating = item.get("vote_average") or 0
                # min_rating <= 0 时不过滤评分（包含未开分的）
                if tmdb_id in emby_tmdb_map and (min_rating <= 0 or rating >= min_rating):
                    matched_ids.append(emby_tmdb_map[tmdb_id])
            
            return matched_ids
        except Exception as e:
            logger.error(f"[智能合集] TMDB 请求失败: {e}")
            return []
    
    def _fetch_tmdb_top250(self, media_type: str, proxies: dict, min_rating: float, emby_tmdb_map: dict) -> List[str]:
        """获取 TMDB Top250 榜单（分页获取前250名）"""
        matched_ids = []
        
        try:
            # TMDB 每页最多 20 条，需要获取 13 页才能拿到 250 条
            for page in range(1, 14):
                try:
                    res = tmdb_client.get_top_rated(media_type, proxies=proxies, timeout=15, page=page)
                    if res.status_code != 200:
                        continue
                    
                    results = res.json().get("results", [])
                    if not results:
                        break
                    
                    for item in results:
                        tmdb_id = str(item.get("id", ""))
                        rating = item.get("vote_average") or 0
                        
                        # min_rating <= 0 时不过滤评分
                        if tmdb_id in emby_tmdb_map and (min_rating <= 0 or rating >= min_rating):
                            matched_ids.append(emby_tmdb_map[tmdb_id])
                        
                        # 最多 250 条
                        if len(matched_ids) >= 250:
                            break
                    
                    if len(matched_ids) >= 250:
                        break
                        
                except Exception as e:
                    logger.error(f"[智能合集] TMDB Top250 第 {page} 页请求失败: {e}")
                    continue
            
            logger.info(f"[智能合集] TMDB {media_type} Top250 匹配到 {len(matched_ids)} 个项目")
            return matched_ids[:250]
            
        except Exception as e:
            logger.error(f"[智能合集] TMDB Top250 请求失败: {e}")
            return []
    
    def _fetch_continuing_items(self, admin_id: str, min_rating: float) -> List[str]:
        """获取正在热播的剧集
        
        逻辑：和追剧日历一样，直接查询 Emby 中 Status == "Continuing" 的剧集
        """
        try:
            # 直接查询 Emby 中连载中的剧集（和追剧日历逻辑一致）
            res = media_api.get(f"/Users/{admin_id}/Items", params={
                "IncludeItemTypes": "Series",
                "Recursive": "true",
                "Fields": "ProviderIds,Status,Genres,CommunityRating,RecursiveItemCount",
                "IsVirtual": "false",
                "Limit": 5000
            }, timeout=30)
            
            if res.status_code != 200:
                logger.error(f"[智能合集] 获取剧集列表失败: {res.status_code}")
                return []
            
            items = res.json().get("Items", [])
            logger.info(f"[智能合集] Emby 中共有 {len(items)} 部剧集")
            
            matched_ids = []
            continuing_count = 0
            no_tmdb_count = 0
            anime_count = 0
            short_count = 0
            rating_count = 0
            
            for item in items:
                try:
                    # 只保留连载中的剧集
                    status = item.get("Status", "")
                    if status != "Continuing":
                        continue
                    
                    continuing_count += 1
                    name = item.get("Name", "未知")
                    
                    # 必须有 TMDB ID
                    tmdb_id = item.get("ProviderIds", {}).get("Tmdb")
                    if not tmdb_id:
                        no_tmdb_count += 1
                        continue
                    
                    # 过滤动画
                    genres = item.get("Genres", [])
                    if "Animation" in genres or "动画" in genres:
                        anime_count += 1
                        logger.debug(f"[智能合集] 跳过动画: {name}")
                        continue
                    
                    # 过滤短剧
                    ep_count = item.get("RecursiveItemCount") or 0
                    if ep_count <= 3:
                        short_count += 1
                        logger.debug(f"[智能合集] 跳过短剧: {name} ({ep_count}集)")
                        continue
                    
                    # 过滤评分
                    rating = item.get("CommunityRating") or 0
                    if min_rating > 0 and rating < min_rating:
                        rating_count += 1
                        logger.debug(f"[智能合集] 跳过评分不足: {name} (评分{rating})")
                        continue
                    
                    matched_ids.append(item["Id"])
                    logger.debug(f"[智能合集] 匹配: {name}")
                        
                except Exception as e:
                    continue
            
            logger.info(f"[智能合集] 统计: 连载中={continuing_count}, 无TMDB={no_tmdb_count}, 动画={anime_count}, 短剧={short_count}, 评分不足={rating_count}, 最终匹配={len(matched_ids)}")
            return matched_ids
            
        except Exception as e:
            logger.error(f"[智能合集] 获取热播剧集失败: {e}")
            return []
    
    def _fetch_recent_added(self, admin_id: str, min_rating: float) -> List[str]:
        """获取最近添加的项目"""
        try:
            res = media_api.get(f"/Users/{admin_id}/Items/Latest", params={
                "Limit": 50,
                "Fields": "CommunityRating",
            }, timeout=10)
            
            if res.status_code != 200:
                return []
            
            items = res.json()
            matched_ids = []
            
            for item in items:
                rating = item.get("CommunityRating") or 0
                # min_rating <= 0 时不过滤评分（包含未开分的）
                if min_rating <= 0 or rating >= min_rating:
                    matched_ids.append(item["Id"])
            
            return matched_ids
        except Exception as e:
            logger.error(f"[智能合集] 获取最近添加失败: {e}")
            return []
    
    # ==========================================
    # Emby API 操作
    # ==========================================
    
    def _get_admin_id(self) -> Optional[str]:
        """获取管理员 ID"""
        try:
            res = media_api.get("/Users", timeout=5)
            if res.status_code == 200:
                for u in res.json():
                    if u.get("Policy", {}).get("IsAdministrator"):
                        return u['Id']
                users = res.json()
                if users:
                    return users[0]['Id']
        except:
            pass
        return None
    
    def _build_emby_tmdb_map(self, admin_id: str) -> dict:
        """构建 TMDB ID → Emby Item ID 映射"""
        tmdb_map = {}
        try:
            for item_type in ["Movie", "Series"]:
                res = media_api.get(f"/Users/{admin_id}/Items", params={
                    "IncludeItemTypes": item_type, "Recursive": "true",
                    "Fields": "ProviderIds", "Limit": 10000
                }, timeout=30)
                if res.status_code == 200:
                    for item in res.json().get("Items", []):
                        tmdb_id = item.get("ProviderIds", {}).get("Tmdb")
                        if tmdb_id:
                            tmdb_map[str(tmdb_id)] = item["Id"]
        except Exception as e:
            logger.error(f"[智能合集] 构建映射失败: {e}")
        return tmdb_map
    
    def _update_emby_collection(self, name: str, item_ids: List[str]):
        """增量更新 Emby 合集"""
        try:
            admin_id = self._get_admin_id()
            if not admin_id:
                logger.error(f"[智能合集] 更新合集 {name} 失败: 无法获取管理员ID")
                return
            
            # 创建合集时直接传入项目 ID
            collection_id = self._find_or_create_collection(name, admin_id, item_ids)
            if not collection_id:
                logger.error(f"[智能合集] 更新合集 {name} 失败: 无法创建合集")
                return
            
            # 获取现有项目
            existing = media_api.get(f"/Users/{admin_id}/Items", params={
                "ParentId": collection_id, "Limit": 500
            }, timeout=10)
            
            existing_ids = set()
            if existing.status_code == 200:
                existing_ids = {i["Id"] for i in existing.json().get("Items", [])}
            
            # 只添加新项目
            new_ids = [iid for iid in item_ids if iid not in existing_ids]
            if new_ids:
                logger.info(f"[智能合集] 合集 {name}: 添加 {len(new_ids)} 个新项目")
                res = media_api.post(f"/Collections/{collection_id}/Items", params={
                    "Ids": ",".join(new_ids)
                }, timeout=10)
                logger.info(f"[智能合集] 添加项目响应: {res.status_code}")
            else:
                logger.info(f"[智能合集] 合集 {name}: 无新项目需要添加")
        except Exception as e:
            logger.error(f"[智能合集] 更新合集失败: {e}")
    
    def _replace_emby_collection(self, name: str, item_ids: List[str]):
        """全量替换 Emby 合集"""
        try:
            admin_id = self._get_admin_id()
            if not admin_id:
                logger.error(f"[智能合集] 替换合集 {name} 失败: 无法获取管理员ID")
                return
            
            # 创建合集时直接传入项目 ID
            collection_id = self._find_or_create_collection(name, admin_id, item_ids)
            if not collection_id:
                logger.error(f"[智能合集] 替换合集 {name} 失败: 无法创建合集")
                return
            
            # 移除所有旧项目
            existing = media_api.get(f"/Users/{admin_id}/Items", params={
                "ParentId": collection_id, "Limit": 500
            }, timeout=10)
            
            if existing.status_code == 200:
                old_ids = [i["Id"] for i in existing.json().get("Items", [])]
                if old_ids:
                    logger.info(f"[智能合集] 合集 {name}: 移除 {len(old_ids)} 个旧项目")
                    media_api.delete(f"/Collections/{collection_id}/Items", params={
                        "Ids": ",".join(old_ids)
                    }, timeout=10)
            
            # 添加新项目
            if item_ids:
                logger.info(f"[智能合集] 合集 {name}: 添加 {len(item_ids)} 个新项目")
                res = media_api.post(f"/Collections/{collection_id}/Items", params={
                    "Ids": ",".join(item_ids)
                }, timeout=10)
                logger.info(f"[智能合集] 添加项目响应: {res.status_code}")
        except Exception as e:
            logger.error(f"[智能合集] 替换合集失败: {e}")
    
    def _find_or_create_collection(self, name: str, admin_id: str, initial_ids: List[str] = None) -> Optional[str]:
        """查找或创建合集"""
        try:
            # 搜索现有合集
            search_res = media_api.get(f"/Users/{admin_id}/Items", params={
                "SearchTerm": name, "IncludeItemTypes": "BoxSet",
                "Recursive": "true", "Limit": 5
            }, timeout=10)
            
            if search_res.status_code == 200:
                for item in search_res.json().get("Items", []):
                    if item.get("Name") == name:
                        logger.info(f"[智能合集] 找到现有合集: {name} (ID: {item['Id']})")
                        return item["Id"]
            
            # 创建新合集
            logger.info(f"[智能合集] 创建新合集: {name}")
            params = {"Name": name}
            if initial_ids:
                params["Ids"] = ",".join(initial_ids)
            
            create_res = media_api.post("/Collections", params=params, timeout=10)
            
            logger.info(f"[智能合集] 创建合集响应: {create_res.status_code}")
            if create_res.status_code in [200, 201]:
                collection_id = create_res.json().get("Id")
                logger.info(f"[智能合集] 合集创建成功: {name} (ID: {collection_id})")
                return collection_id
            else:
                logger.error(f"[智能合集] 创建合集失败: {create_res.status_code} - {create_res.text[:200]}")
        except Exception as e:
            logger.error(f"[智能合集] 创建合集失败: {e}")
        return None
    
    def _delete_emby_collection(self, name: str):
        """删除 Emby 合集"""
        try:
            admin_id = self._get_admin_id()
            if not admin_id:
                return
            
            search_res = media_api.get(f"/Users/{admin_id}/Items", params={
                "SearchTerm": name, "IncludeItemTypes": "BoxSet",
                "Recursive": "true", "Limit": 5
            }, timeout=10)
            
            if search_res.status_code == 200:
                for item in search_res.json().get("Items", []):
                    if item.get("Name") == name:
                        media_api.delete(f"/Items/{item['Id']}", timeout=10)
                        break
        except Exception as e:
            logger.error(f"[智能合集] 删除合集失败: {e}")


# 创建插件实例
plugin = SmartCollectionsPlugin()
