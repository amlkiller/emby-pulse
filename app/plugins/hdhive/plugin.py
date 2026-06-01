"""
影巢 (HDHive) 资源插件
搜索影巢资源、解锁下载链接、账户状态、每日签到
"""
import time
import json
import logging
import threading
import datetime
from fastapi import Request
from app.plugins.base import PluginBase
from app.domains.users.auth import is_admin_user  # 🔒 管理员鉴权
from app.core.event_bus import bus
from app.infra.clients.hdhive_client import hdhive_client
from app.infra.clients.tmdb_client import tmdb_client

logger = logging.getLogger("uvicorn")


class HDHivePlugin(PluginBase):
    id = "hdhive"
    name = "影巢资源中心"
    description = "搜索影巢资源、解锁下载链接、账户管理、每日自动签到"
    icon = "fa-clapperboard"
    icon_color = "from-emerald-500 to-teal-500"
    version = "1.1.0"
    author = "EmbyPulse"

    def __init__(self):
        super().__init__()
        self._checkin_thread = None
        self._running = False
        self._subscribed = False
        self._setup_routes()

    def on_enable(self):
        self._running = True
        if not self._subscribed:
            bus.subscribe("bot.admin_message", self._on_admin_message)
            self._subscribed = True
        self._checkin_thread = threading.Thread(target=self._checkin_loop, daemon=True)
        self._checkin_thread.start()
        logger.info("🔌 [影巢] 插件已启用")

    def on_disable(self):
        self._running = False
        logger.info("🔌 [影巢] 插件已禁用")

    def get_config_schema(self):
        return [
            {"key": "api_key", "label": "影巢 API Key", "type": "password",
             "placeholder": "从 hdhive.com 个人设置中获取",
             "hint": "登录影巢后在个人设置 > API 管理中创建"},
            {"key": "auto_checkin", "label": "自动签到", "type": "multiselect", "options": [
                {"value": "enabled", "label": "✅ 每日自动签到（需 Premium）"},
                {"value": "gambler", "label": "🎲 赌狗签到模式（高风险高回报）"},
            ]},
            {"key": "checkin_time", "label": "签到时间", "type": "text",
             "placeholder": "08:00", "hint": "自动签到时间（北京时间，格式 HH:MM，如 08:30）"},
            {"key": "notify_enabled", "label": "启用通知", "type": "toggle", "hint": "开启后，插件运行状态会发送到全局通知"},
        ]

    def _get_config(self):
        from app.plugins import get_plugin_config
        return get_plugin_config(self.id)

    def _proxies(self):
        from app.utils.proxy_helper import get_safe_proxies
        return get_safe_proxies()

    def search_by_tmdb(self, tmdb_id, res_type, page=1, page_size=10):
        """Public sync search API for other backend modules."""
        return self._search_by_tmdb(tmdb_id, res_type, self._proxies(), page, page_size)

    def _log(self, msg, level="info"):
        """记录日志（兼容旧代码）- 同时写入数据库和控制台"""
        # 调用基类的 log 方法，写入数据库并发送通知
        self.log(msg, level=level, notify=False)

    # ==========================================
    # API 路由（注册到 FastAPI）
    # ==========================================
    def _setup_routes(self):
        """注册插件 API 路由"""

        @self.router.get("/account")
        def get_account(request: Request):
            if not request.session.get("user"):
                return {"status": "error"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            return self.get_account_info()

        @self.router.post("/checkin")
        async def do_checkin(request: Request):
            """API: 每日签到"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            try:
                data = await request.json()
                is_gambler = data.get("is_gambler", False)
            except:
                is_gambler = False
            return self.checkin(is_gambler=is_gambler)

        @self.router.post("/search")
        async def api_search(request: Request):
            """API: 搜索影巢资源（仅115网盘）"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            return await self.api_search_resources_async(request)

        @self.router.post("/unlock")
        async def api_unlock(request: Request):
            """API: 解锁并转存资源"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            return await self.api_unlock_and_transfer_async(request)
        
        @self.router.post("/transfer")
        async def api_transfer(request: Request):
            """API: 解锁资源并转存到指定文件夹"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            return await self.api_transfer_to_folder_async(request)

        @self.router.get("/usage")
        def get_usage(request: Request):
            """API: 获取用量统计"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            return self.get_usage_stats()

        @self.router.get("/usage/today")
        def get_usage_today(request: Request):
            """API: 获取今日用量"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            return self.get_usage_today()

        @self.router.get("/vip/quota")
        def get_vip_quota(request: Request):
            """API: 获取永V每周免费额度"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            return self.get_vip_weekly_quota()

    # ==========================================
    # 后端 API 方法 (异步版本)
    # ==========================================
    async def api_search_resources_async(self, request: Request):
        """后端 API：搜索影巢资源（返回 TMDB 信息 + 115 资源列表）"""
        try:
            data = await request.json()
            keyword = data.get("keyword", "").strip()
            tmdb_id = data.get("tmdb_id")
            res_type = data.get("type", "tv")  # movie or tv
            page = data.get("page", 1)  # 分页页码
            page_size = data.get("page_size", 10)  # 每页数量
        except:
            return {"status": "error", "message": "参数错误"}

        if not keyword and not tmdb_id:
            return {"status": "error", "message": "请提供关键词或TMDB ID"}

        proxies = self._proxies()

        # 如果有 TMDB ID，直接查影巢
        if tmdb_id:
            result = self._search_by_tmdb(tmdb_id, res_type, proxies, page, page_size)
            # 添加 TMDB 信息
            if result.get("status") == "success":
                result["tmdb_info"] = {"id": tmdb_id, "type": res_type}
            return result

        # 否则用关键词搜索 TMDB
        if not tmdb_client.api_key:
            return {"status": "error", "message": "未配置 TMDB API Key"}

        try:
            # 搜索 TMDB
            movie_res = tmdb_client.search_movie(keyword, proxies=proxies, timeout=15, page=1)
            tv_res = tmdb_client.search_tv(keyword, proxies=proxies, timeout=15, page=1)

            # 收集所有 TMDB 结果（全部）
            tmdb_results = []
            if movie_res.status_code == 200:
                movie_data = movie_res.json()
                for item in movie_data.get("results", []):
                    tmdb_results.append({
                        "id": item.get("id"),
                        "type": "movie",
                        "title": item.get("title", ""),
                        "year": (item.get("release_date") or "")[:4],
                        "overview": item.get("overview", ""),
                        "poster": item.get("poster_path"),
                        "backdrop": item.get("backdrop_path")
                    })

            if tv_res.status_code == 200:
                tv_data = tv_res.json()
                for item in tv_data.get("results", []):
                    tmdb_results.append({
                        "id": item.get("id"),
                        "type": "tv",
                        "title": item.get("name", ""),
                        "year": (item.get("first_air_date") or "")[:4],
                        "overview": item.get("overview", ""),
                        "poster": item.get("poster_path"),
                        "backdrop": item.get("backdrop_path")
                    })

            if not tmdb_results:
                return {"status": "error", "message": "未找到相关资源"}

            # 如果只有一个结果，直接查询影巢
            if len(tmdb_results) == 1:
                first = tmdb_results[0]
                result = self._search_by_tmdb(first["id"], first["type"], proxies, page, page_size)
                if result.get("status") == "success":
                    result["tmdb_info"] = first
                return result

            # 多个结果，返回列表让前端选择
            return {
                "status": "multiple_tmdb",
                "message": "找到多个相关影片，请选择",
                "tmdb_list": tmdb_results
            }

        except Exception as e:
            logger.error(f"[影巢API] 搜索失败: {e}")
            return {"status": "error", "message": f"搜索失败: {str(e)}"}

    def _search_by_tmdb(self, tmdb_id, res_type, proxies, page=1, page_size=10):
        """根据 TMDB ID 查询影巢 115 资源
        
        Args:
            tmdb_id: TMDB ID
            res_type: 资源类型 (movie/tv)
            proxies: 代理配置
            page: 页码（从1开始）
            page_size: 每页数量
        """
        try:
            resp = hdhive_client.search_resources(self._get_config().get("api_key", ""), res_type, tmdb_id, proxies=proxies, timeout=15)

            if resp.status_code != 200:
                return {"status": "error", "message": f"影巢API错误: HTTP {resp.status_code}"}

            data = resp.json()
            if not data.get("success"):
                return {"status": "error", "message": data.get("message", "查询失败")}

            # 兼容 data 返回格式
            data_obj = data.get("data", {})
            if isinstance(data_obj, list):
                resources = data_obj
                slug = resources[0].get("slug", "") if resources else ""
            else:
                resources = data_obj.get("resources", []) if isinstance(data_obj, dict) else []
                slug = data_obj.get("slug", "") if isinstance(data_obj, dict) else ""

            # 过滤 115 网盘资源 - 直接使用 pan_type 判断
            logger.info(f"[影巢API] 开始检查 {len(resources)} 个资源的网盘类型")
            resources_115 = []
            for r in resources:
                pan_type = r.get("pan_type", "")
                res_slug = r.get("slug", "")
                logger.info(f"[影巢API] 检查资源: {r.get('title', '未知')}, pan_type={pan_type}, slug={res_slug[:16]}...")

                # 直接使用 pan_type 判断网盘类型
                if pan_type == "115":
                    r["drive_type"] = "115"
                    r["slug"] = res_slug or slug
                    r["website"] = "115"
                    resources_115.append(r)
                    logger.info(f"[影巢API] ✅ 找到115资源: {r.get('title', '未知')}, 当前共 {len(resources_115)} 个")
                else:
                    logger.info(f"[影巢API] ⏭️ 跳过非115资源(pan_type={pan_type})")

            if not resources_115:
                logger.warning(f"[影巢API] 未找到115网盘资源，共检查 {len(resources)} 个资源")
                return {"status": "error", "message": "未找到115网盘资源"}

            # 分页处理
            total = len(resources_115)
            total_pages = (total + page_size - 1) // page_size
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            page_resources = resources_115[start_idx:end_idx]

            # 返回分页数据
            logger.info(f"[影巢API] 返回第 {page}/{total_pages} 页，共 {len(page_resources)} 个资源，总计 {total} 个")
            return {
                "status": "success", 
                "data": page_resources,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": total_pages,
                    "has_more": page < total_pages
                }
            }

        except Exception as e:
            logger.error(f"[影巢API] 查询失败: {e}")
            return {"status": "error", "message": str(e)}

    async def api_unlock_and_transfer_async(self, request: Request):
        """后端 API：解锁资源并触发115转存"""
        try:
            data = await request.json()
            slug = data.get("slug", "").strip()
        except:
            return {"status": "error", "message": "参数错误"}

        if not slug:
            return {"status": "error", "message": "缺少 slug"}

        # 调用解锁 API（不自动转存）
        result = self.unlock(slug, auto_transfer=False)
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

        # 触发115转存
        try:
            from app.plugins import get_plugin
            cloud115 = get_plugin("cloud115")
            if cloud115 and cloud115.enabled:
                # 发布到事件总线触发转存
                bus.publish("bot.admin_message", full_link, "sys_notify", "all")
                self._log(f"Gaps调用：已触发115转存: {title}")
                return {"status": "success", "message": f"已触发115转存: {title}", "title": title}
        except Exception as e:
            logger.error(f"[影巢API] 触发115转存失败: {e}")

        # 没有115插件，返回链接
        return {"status": "success", "message": "解锁成功", "url": url, "access_code": access_code, "title": title}

    async def api_transfer_to_folder_async(self, request: Request):
        """后端 API：解锁资源并转存到指定文件夹"""
        try:
            data = await request.json()
            slug = data.get("slug", "").strip()
            folder_id = data.get("folder_id")  # 可选，None 表示默认目录
        except:
            return {"status": "error", "message": "参数错误"}

        if not slug:
            return {"status": "error", "message": "缺少 slug"}

        # 调用解锁 API
        result = self.unlock(slug, auto_transfer=False)
        if result.get("status") != "success":
            return result

        unlock_data = result.get("data", {})
        url = unlock_data.get("url", "")
        access_code = unlock_data.get("access_code", "")
        title = unlock_data.get("title", "未知资源")
        points_cost = unlock_data.get("points_cost", 0)
        already_owned = unlock_data.get("already_owned", False)

        if not url:
            return {"status": "error", "message": "解锁成功但未获取到链接"}

        # 拼接完整链接
        full_link = url
        if access_code:
            sep = "&" if "?" in url else "?"
            full_link = f"{url}{sep}password={access_code}"

        # 调用 cloud115 插件转存（直接调用方法，不走HTTP）
        try:
            from app.plugins import get_plugin
            cloud115 = get_plugin("cloud115")
            if cloud115 and cloud115.enabled:
                self._log(f"调用115插件转存: link={full_link[:50]}..., folder_id={folder_id}")
                transfer_result = cloud115._do_transfer_sync(full_link, folder_id or "0", "转存", cloud115._get_config().get("cookie", ""))
                self._log(f"115转存结果: {transfer_result}")
                
                if transfer_result.get("status") == "success":
                    cost_msg = "（免费）" if points_cost == 0 else f"（{'已拥有' if already_owned else f'消耗 {points_cost} 积分'}）"
                    self._log(f"转存成功: {title} -> {folder_id or '默认目录'}")
                    return {"status": "success", "message": f"转存成功 {cost_msg}", "title": title}
                else:
                    logger.error(f"[影巢API] 转存返回错误: {transfer_result.get('message')}")
                    return {"status": "error", "message": transfer_result.get("message", "转存失败")}
            else:
                logger.error("[影巢API] 115插件未启用")
                return {"status": "error", "message": "115插件未启用，请先配置115转存插件"}
        except Exception as e:
            logger.error(f"[影巢API] 转存异常: {e}")
            # 降级：通过事件总线通知
            try:
                bus.publish("bot.admin_message", full_link, "sys_notify", "all")
                self._log(f"降级通知：已发送转存链接到机器人: {title}")
                return {"status": "success", "message": f"已发送转存链接到机器人: {title}", "title": title}
            except:
                return {"status": "error", "message": f"转存失败: {str(e)}"}

    # ==========================================
    # 核心功能
    # ==========================================
    def unlock(self, slug, auto_transfer=True):
        """解锁资源获取下载链接，可选自动触发115转存"""
        if not slug:
            return {"status": "error", "message": "缺少资源 slug"}
        try:
            res = hdhive_client.unlock_resource(self._get_config().get("api_key", ""), slug, proxies=self._proxies(), timeout=15)
            if res.status_code == 200:
                data = res.json()
                if data.get("success"):
                    result = data.get("data", {})
                    self._log(f"解锁资源: {result.get('title', slug)}")

                    # 用 check/resource 接口检测网盘类型
                    url = result.get("url", "")
                    drive_type = ""
                    if url:
                        try:
                            check_res = hdhive_client.check_resource(self._get_config().get("api_key", ""), url, proxies=self._proxies(), timeout=10)
                            if check_res.status_code == 200:
                                check_data = check_res.json()
                                if check_data.get("success"):
                                    drive_type = check_data.get("data", {}).get("website", "")
                                    result["drive_type"] = drive_type
                                    self._log(f"网盘类型: {drive_type}")
                        except:
                            pass

                    # 只有115网盘才自动转存
                    if auto_transfer and url and drive_type == "115":
                        access_code = result.get("access_code", "")
                        full_link = url
                        if access_code:
                            sep = "&" if "?" in url else "?"
                            full_link = f"{url}{sep}password={access_code}"
                        try:
                            from app.plugins import get_plugin
                            cloud115 = get_plugin("cloud115")
                            if cloud115 and cloud115.enabled:
                                bus.publish("bot.admin_message", full_link, "sys_notify", "all")
                                self._log(f"已触发115转存: {result.get('title', '')}")
                        except:
                            pass
                    elif auto_transfer and url and drive_type and drive_type != "115":
                        self._log(f"非115网盘({drive_type})，跳过自动转存")

                    return {"status": "success", "data": result}
                return {"status": "error", "message": data.get("message", "解锁失败")}
            return {"status": "error", "message": f"HTTP {res.status_code}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_account_info(self):
        """获取影巢账户信息"""
        try:
            api_key = self._get_config().get("api_key", "")
            if not api_key:
                return {"status": "error", "message": "未配置 API Key"}
            # 先检查连通性
            ping = hdhive_client.ping(api_key, proxies=self._proxies(), timeout=10)
            logger.info(f"[影巢] ping响应: HTTP {ping.status_code}, body={ping.text[:200]}")
            if ping.status_code != 200:
                return {"status": "error", "message": "API Key 无效或网络异常"}
            ping_data = ping.json()

            # 获取配额
            quota = hdhive_client.get_quota(api_key, proxies=self._proxies(), timeout=10)
            quota_data = quota.json().get("data", {}) if quota.status_code == 200 else {}

            # 尝试获取用户信息（Premium）
            user_info = {}
            try:
                me = hdhive_client.get_me(api_key, proxies=self._proxies(), timeout=10)
                if me.status_code == 200:
                    user_info = me.json().get("data", {})
            except Exception: pass

            return {"status": "success", "data": {
                "ping": ping_data.get("data", {}),
                "quota": quota_data,
                "user": user_info
            }}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def checkin(self, is_gambler=False):
        """每日签到
        
        Args:
            is_gambler: 是否使用赌狗模式（高风险高回报）
            
        Returns:
            dict: 签到结果，包含积分变化等信息
        """
        try:
            api_key = self._get_config().get("api_key", "")
            if not api_key:
                return {"status": "error", "message": "未配置 API Key"}
            res = hdhive_client.checkin(api_key, is_gambler=is_gambler, proxies=self._proxies(), timeout=15)
            if res.status_code == 200:
                data = res.json()
                if data.get("success"):
                    checkin_data = data.get("data", {})
                    message = checkin_data.get("message") or data.get("message", "签到成功")
                    checked_in = checkin_data.get("checked_in", False)
                    
                    # 尝试从 message 中提取积分
                    import re
                    points_match = re.search(r'获得\s*(\d+)\s*积分', message)
                    points_earned = int(points_match.group(1)) if points_match else 0
                    
                    # 获取用户当前积分信息
                    user_meta = {}
                    total_points = 0
                    signin_days = 0
                    try:
                        me_res = hdhive_client.get_me(api_key, proxies=self._proxies(), timeout=10)
                        if me_res.status_code == 200:
                            me_data = me_res.json()
                            if me_data.get("success"):
                                user_meta = me_data.get("data", {}).get("user_meta", {})
                                total_points = user_meta.get("points", 0)
                                signin_days = user_meta.get("signin_days_total", 0)
                    except Exception as e:
                        logger.warning(f"[影巢] 获取用户信息失败: {e}")
                    
                    self._log(f"签到成功: {message}")
                    
                    return {
                        "status": "success",
                        "data": {
                            "checked_in": checked_in,
                            "message": message,
                            "points_earned": points_earned,
                            "total_points": total_points,
                            "signin_days": signin_days,
                            "is_gambler": is_gambler
                        },
                        "message": message
                    }
                return {"status": "error", "message": data.get("message", "签到失败")}
            elif res.status_code == 403:
                return {"status": "error", "message": "需要 Premium 会员"}
            return {"status": "error", "message": f"HTTP {res.status_code}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_usage_stats(self, start_date=None, end_date=None):
        """获取用量统计"""
        try:
            api_key = self._get_config().get("api_key", "")
            if not api_key:
                return {"status": "error", "message": "未配置 API Key"}
            
            params = {}
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date
            
            res = hdhive_client.get_usage(api_key, params=params, proxies=self._proxies(), timeout=10)
            if res.status_code == 200:
                data = res.json()
                if data.get("success"):
                    return {"status": "success", "data": data.get("data", {})}
                return {"status": "error", "message": data.get("message", "获取失败")}
            return {"status": "error", "message": f"HTTP {res.status_code}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_usage_today(self):
        """获取今日用量"""
        try:
            api_key = self._get_config().get("api_key", "")
            if not api_key:
                return {"status": "error", "message": "未配置 API Key"}
            
            res = hdhive_client.get_usage_today(api_key, proxies=self._proxies(), timeout=10)
            if res.status_code == 200:
                data = res.json()
                if data.get("success"):
                    return {"status": "success", "data": data.get("data", {})}
                return {"status": "error", "message": data.get("message", "获取失败")}
            return {"status": "error", "message": f"HTTP {res.status_code}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_vip_weekly_quota(self):
        """获取永V每周免费解锁额度"""
        try:
            api_key = self._get_config().get("api_key", "")
            if not api_key:
                return {"status": "error", "message": "未配置 API Key"}
            
            res = hdhive_client.get_vip_weekly_quota(api_key, proxies=self._proxies(), timeout=10)
            if res.status_code == 200:
                data = res.json()
                if data.get("success"):
                    return {"status": "success", "data": data.get("data", {})}
                return {"status": "error", "message": data.get("message", "获取失败")}
            elif res.status_code == 403:
                return {"status": "error", "message": "需要 Premium 会员", "need_premium": True}
            return {"status": "error", "message": f"HTTP {res.status_code}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ==========================================
    # 自动签到线程
    # ==========================================
    # ==========================================
    # 管理员消息监听（影巢链接自动解锁转存 + 搜索命令）
    # ==========================================
    def _on_admin_message(self, text, chat_id, platform):
        """检测影巢链接，自动解锁并转存到115；处理搜索命令"""
        if not self._enabled:
            return
        import re

        # 检测搜索命令：/搜索 关键词 或 搜索 关键词
        search_match = re.search(r'^(?:/\w+\s+)?搜索\s+(.+)$', text.strip(), re.IGNORECASE)
        if search_match:
            keyword = search_match.group(1).strip()
            if keyword:
                threading.Thread(target=self._search_and_show, args=(keyword, chat_id, platform), daemon=True).start()
                return

        # 检测影巢链接
        links = re.findall(r'https?://hdhive\.com/resource/\S+', text)
        if not links:
            return
        logger.info(f"[影巢] 检测到 {len(links)} 个影巢链接")
        for link in links:
            threading.Thread(target=self._process_hdhive_link, args=(link, chat_id, platform), daemon=True).start()

    def _search_and_show(self, keyword, chat_id, platform, tmdb_page=1):
        """搜索资源：TMDB 搜索 → 用户选择 → 查询影巢 115 资源
        
        Args:
            keyword: 搜索关键词
            chat_id: 聊天ID
            platform: 平台
            tmdb_page: TMDB 搜索页码（从1开始）
        """
        if tmdb_page == 1:
            self._notify(chat_id, f"🔍 <b>[影巢搜索]</b> 正在搜索: {keyword}...", platform)

        # 1. TMDB 搜索（电影+剧集）
        if not tmdb_client.api_key:
            self._notify(chat_id, "❌ [影巢搜索] 未配置 TMDB API Key", platform)
            return

        # 获取代理配置
        from app.utils.proxy_helper import get_safe_proxies
        proxies = get_safe_proxies()

        try:
            # 并行搜索电影和剧集（带分页）
            movie_res = tmdb_client.search_movie(keyword, proxies=proxies, timeout=15, page=tmdb_page)
            tv_res = tmdb_client.search_tv(keyword, proxies=proxies, timeout=15, page=tmdb_page)

            tmdb_results = []
            movie_total_pages = 1
            tv_total_pages = 1
            movie_total_results = 0
            tv_total_results = 0

            # 处理电影结果 - 取所有结果（TMDB 默认每页20个）
            if movie_res.status_code == 200:
                movie_data = movie_res.json()
                movie_total_pages = movie_data.get("total_pages", 1)
                movie_total_results = movie_data.get("total_results", 0)
                for item in movie_data.get("results", []):
                    tmdb_results.append({
                        "type": "movie",
                        "tmdb_id": item.get("id"),
                        "title": item.get("title", ""),
                        "year": item.get("release_date", "")[:4] if item.get("release_date") else "",
                    })

            # 处理剧集结果 - 取所有结果
            if tv_res.status_code == 200:
                tv_data = tv_res.json()
                tv_total_pages = tv_data.get("total_pages", 1)
                tv_total_results = tv_data.get("total_results", 0)
                for item in tv_data.get("results", []):
                    tmdb_results.append({
                        "type": "tv",
                        "tmdb_id": item.get("id"),
                        "title": item.get("name", ""),
                        "year": item.get("first_air_date", "")[:4] if item.get("first_air_date") else "",
                    })

            if not tmdb_results:
                self._notify(chat_id, f"⚠️ [影巢搜索] 未找到相关资源: {keyword}", platform)
                return

            # 按年份排序（新的在前）
            tmdb_results.sort(key=lambda x: x.get("year", ""), reverse=True)
            
            # 计算实际的分页（合并后每页10个）
            RESULTS_PER_PAGE = 10
            total_results = movie_total_results + tv_total_results
            total_pages = (len(tmdb_results) + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE if len(tmdb_results) > RESULTS_PER_PAGE else 1
            
            logger.info(f"[影巢搜索] TMDB 第{tmdb_page}页找到 {len(tmdb_results)} 个结果 (电影{movie_total_results}+剧集{tv_total_results})")

            # 2. 展示 TMDB 结果让用户选择（只显示当前页的结果）
            import hashlib
            search_key = hashlib.md5(f"{keyword}_{tmdb_page}".encode()).hexdigest()[:8]
            _tmdb_cache[search_key] = {
                "results": tmdb_results,
                "keyword": keyword,
                "page": tmdb_page,
                "total_pages": total_pages,
                "total_results": total_results
            }

            keyboard = {"inline_keyboard": []}
            # 只显示前10个结果
            for i, item in enumerate(tmdb_results[:RESULTS_PER_PAGE]):
                res_type = "🎬" if item["type"] == "movie" else "📺"
                text = f"{res_type} {item['title']} ({item['year']})"
                keyboard["inline_keyboard"].append([{
                    "text": text,
                    "callback_data": f"hdhive_tmdb_{search_key}_{item['type']}_{item['tmdb_id']}"
                }])

            # 添加分页按钮（基于 TMDB API 的分页）
            # 修复：使用 TMDB 返回的 total_pages 判断是否有更多页
            api_total_pages = max(movie_total_pages, tv_total_pages)
            # 只要有多个结果页，或者当前页结果超过10个，就显示翻页按钮
            has_more_pages = api_total_pages > 1 or len(tmdb_results) > RESULTS_PER_PAGE
            logger.info(f"[影巢搜索] 分页判断: api_total_pages={api_total_pages}, tmdb_results={len(tmdb_results)}, RESULTS_PER_PAGE={RESULTS_PER_PAGE}, has_more_pages={has_more_pages}")
            if has_more_pages:
                nav_buttons = []
                # 使用 api_total_pages 判断上一页，如果 api_total_pages 为1但结果超过10个，使用合并后的分页
                effective_total_pages = api_total_pages if api_total_pages > 1 else total_pages
                if tmdb_page > 1:
                    nav_buttons.append({
                        "text": "⬅️ 上一页",
                        "callback_data": f"hdhive_tmdbprev_{tmdb_page - 1}_{keyword}"
                    })
                nav_buttons.append({
                    "text": f"{tmdb_page}/{effective_total_pages}",
                    "callback_data": "hdhive_nop"
                })
                # 只有当当前页小于总页数时才显示下一页按钮
                # 修复：使用 effective_total_pages 而不是 api_total_pages
                if tmdb_page < effective_total_pages:
                    nav_buttons.append({
                        "text": "➡️ 下一页",
                        "callback_data": f"hdhive_tmdbnext_{tmdb_page + 1}_{keyword}"
                    })
                keyboard["inline_keyboard"].append(nav_buttons)
                logger.info(f"[影巢搜索] TMDB 分页按钮: page={tmdb_page}, effective_total_pages={effective_total_pages}, buttons={len(nav_buttons)}")

            page_info = f"第 {tmdb_page}/{total_pages} 页" if total_pages > 1 else ""
            msg = f"🔍 <b>[影巢搜索]</b> 找到 {total_results} 个结果 {page_info}\n\n关键词: {keyword}\n\n请选择要搜索的影片："
            self._notify(chat_id, msg, platform, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"[影巢搜索] TMDB 搜索失败: {e}")
            self._notify(chat_id, "❌ [影巢搜索] 搜索失败，请检查网络或代理配置", platform)

    def _show_tmdb_results_from_cache(self, search_key, chat_id, platform, page=1, message_id=None):
        """从缓存中显示 TMDB 搜索结果（本地翻页）
        
        Args:
            search_key: 缓存的 key
            chat_id: 聊天ID
            platform: 平台
            page: 要显示的页码（从1开始）
            message_id: 消息ID（用于编辑消息）
        """
        cache = _tmdb_cache.get(search_key)
        if not cache:
            self._notify(chat_id, "⚠️ 搜索已过期，请重新搜索", platform, message_id=message_id)
            return

        tmdb_results = cache.get("results", [])
        keyword = cache.get("keyword", "")
        total_pages = cache.get("total_pages", 1)
        total_results = cache.get("total_results", len(tmdb_results))
        RESULTS_PER_PAGE = 10

        # 计算当前页要显示的结果
        start_idx = (page - 1) * RESULTS_PER_PAGE
        end_idx = min(start_idx + RESULTS_PER_PAGE, len(tmdb_results))
        page_results = tmdb_results[start_idx:end_idx]

        if not page_results:
            self._notify(chat_id, f"⚠️ [影巢搜索] 没有更多结果", platform, message_id=message_id)
            return

        # 构建键盘
        keyboard = {"inline_keyboard": []}
        for i, item in enumerate(page_results):
            res_type = "🎬" if item["type"] == "movie" else "📺"
            text = f"{res_type} {item['title']} ({item['year']})"
            keyboard["inline_keyboard"].append([{
                "text": text,
                "callback_data": f"hdhive_tmdb_{search_key}_{item['type']}_{item['tmdb_id']}"
            }])

        # 添加分页按钮
        nav_buttons = []
        if page > 1:
            nav_buttons.append({
                "text": "⬅️ 上一页",
                "callback_data": f"hdhive_tmdbprev_{page - 1}_{keyword}"
            })
        nav_buttons.append({
            "text": f"{page}/{total_pages}",
            "callback_data": "hdhive_nop"
        })
        if page < total_pages:
            nav_buttons.append({
                "text": "➡️ 下一页",
                "callback_data": f"hdhive_tmdbnext_{page + 1}_{keyword}"
            })
        keyboard["inline_keyboard"].append(nav_buttons)

        page_info = f"第 {page}/{total_pages} 页"
        msg = f"🔍 <b>[影巢搜索]</b> 找到 {total_results} 个结果 {page_info}\n\n关键词: {keyword}\n\n请选择要搜索的影片："
        self._notify(chat_id, msg, platform, reply_markup=keyboard, message_id=message_id)
        logger.info(f"[影巢搜索] 本地翻页显示: page={page}, total_pages={total_pages}, results={len(page_results)}")

    def _search_tmdb_select(self, search_key, res_type, tmdb_id, chat_id, platform, page=1):
        """用户选择 TMDB 结果后，查询影巢 115 资源
        
        Args:
            page: 页码（从1开始），用于分页显示
        """
        cache = _tmdb_cache.pop(search_key, None)
        if not cache:
            self._notify(chat_id, "⚠️ 搜索已过期，请重新搜索", platform)
            return

        # 找到用户选择的 TMDB 信息
        tmdb_results = cache.get("results", [])
        selected = None
        for item in tmdb_results:
            if str(item["tmdb_id"]) == str(tmdb_id):
                selected = item
                break

        if not selected:
            self._notify(chat_id, "⚠️ 未找到选择的影片", platform)
            return

        keyword = cache.get("keyword", "")
        self._log(f"用户选择: {selected['title']}，正在查询影巢资源...")

        from app.utils.proxy_helper import get_safe_proxies
        proxies = get_safe_proxies()

        try:
            resp = hdhive_client.search_resources(self._get_config().get("api_key", ""), res_type, tmdb_id, proxies=proxies, timeout=15)
            logger.info(f"[影巢搜索] 影巢API响应: HTTP {resp.status_code}, body: {resp.text[:200]}")

            resources_115 = []
            if resp.status_code == 200:
                data = resp.json()
                if not data.get("success"):
                    logger.warning(f"[影巢搜索] 影巢返回失败: {data}")
                    self._notify(chat_id, f"⚠️ [影巢搜索] 影巢查询失败: {data.get('message', '未知错误')}", platform)
                    return

                # 兼容 data 是 dict 或 list 的情况
                data_obj = data.get("data", {})
                if isinstance(data_obj, list):
                    resources = data_obj
                    slug = resources[0].get("slug", "") if resources else ""
                elif isinstance(data_obj, dict):
                    resources = data_obj.get("resources", [])
                    slug = data_obj.get("slug", "")
                else:
                    resources = []
                    slug = ""

                # 检查每个资源的网盘类型
                logger.info(f"[影巢搜索] 开始检查 {len(resources)} 个资源的网盘类型")
                for r in resources:
                    pan_type = r.get("pan_type", "")
                    res_slug = r.get("slug", "")
                    logger.info(f"[影巢搜索] 检查资源: {r.get('title', '未知')}, pan_type={pan_type}")

                    if pan_type == "115":
                        r["drive_type"] = "115"
                        r["item_info"] = selected
                        r["resource_type"] = "movie" if res_type == "movie" else "tv"
                        r["slug"] = res_slug or slug
                        r["website"] = "115"
                        resources_115.append(r)
                        logger.info(f"[影巢搜索] ✅ 找到115资源: {r.get('title', '未知')}")
                    else:
                        logger.info(f"[影巢搜索] ⏭️ 跳过非115资源(pan_type={pan_type})")
        except Exception as e:
            logger.error(f"[影巢搜索] 查询影巢资源失败: {e}")
            self._notify(chat_id, f"❌ [影巢搜索] 查询失败: {e}", platform)
            return

        if not resources_115:
            self._notify(chat_id, f"⚠️ [影巢搜索] 未找到 115 网盘资源\n\n影片: {selected['title']}", platform)
            return

        # 展示 115 资源结果（优化排版，显示解锁状态和分享人）
        import hashlib
        search_key2 = hashlib.md5(f"{keyword}_{tmdb_id}".encode()).hexdigest()[:8]
        _search_cache[search_key2] = {
            "resources": resources_115,
            "keyword": keyword,
            "tmdb_info": selected
        }

        # 分页处理：每页显示5个资源
        PAGE_SIZE = 5
        total_resources = len(resources_115)
        total_pages = (total_resources + PAGE_SIZE - 1) // PAGE_SIZE

        # 构建资源详情消息（第一页）
        msg_lines = [
            f"🎬 <b>{selected['title']}</b> <b>({selected['year']})</b>",
            f"━━━━━━━━━━━━━━",
            f"📊 共找到 <b>{total_resources}</b> 个 115 资源",
            f""
        ]

        def build_resource_msg(r, idx):
            """构建单个资源卡片"""
            lines = []
            title = r.get("title") or "未知资源"
            size = r.get("share_size") or "未知大小"
            points = r.get("unlock_points")
            # 解锁状态：free表示免费，数字表示积分
            is_unlocked = r.get("is_unlocked", False)
            is_free = points is None or points == 0
            is_official = r.get("is_official", False)
            
            # 状态标签 - 放在标题后面
            if is_unlocked:
                status_str = " ✅已解锁"
            elif is_free:
                status_str = " 🆓免费"
            else:
                status_str = f" 🔴{points}分"
            
            # 官方资源标记
            official_str = " 👑官方" if is_official else ""
            
            # 分享人 - 从 user 对象获取
            user_obj = r.get("user", {})
            uploader = user_obj.get("username") or user_obj.get("name") or user_obj.get("nickname") or "" if user_obj else ""
            
            # 分辨率和来源
            resolution = ", ".join(r.get("video_resolution", [])) if r.get("video_resolution") else ""
            source = ", ".join(r.get("source", [])) if r.get("source") else ""
            
            # 标题行：序号 + 标题 + 状态 + 官方
            lines.append(f"<b>{idx}. {title}{status_str}{official_str}</b>")
            lines.append(f"   📦 {size}")
            if resolution:
                lines.append(f"   🎬 {resolution}")
            if source:
                lines.append(f"   📀 {source}")
            if uploader:
                lines.append(f"   👤 分享: {uploader}")
            
            # 备注（截断）
            remark = r.get("remark", "")
            if remark:
                remark_short = remark[:50] + "..." if len(remark) > 50 else remark
                lines.append(f"   📝 {remark_short}")
            
            return "\n".join(lines)

        # 显示第一页资源
        for i, r in enumerate(resources_115[:PAGE_SIZE]):
            msg_lines.append(build_resource_msg(r, i+1))
            msg_lines.append("")  # 资源间隔

        if total_pages > 1:
            msg_lines.append(f"📄 第 1/{total_pages} 页 | 点击按钮解锁或翻页")
        else:
            msg_lines.append("💡 点击按钮一键解锁转存")

        # 构建键盘：资源按钮 + 翻页按钮
        keyboard = {"inline_keyboard": []}

        # 资源按钮（每行2个）
        resource_row = []
        for i, r in enumerate(resources_115[:PAGE_SIZE]):
            points = r.get("unlock_points")
            is_unlocked = r.get("is_unlocked", False)
            is_free = points is None or points == 0
            
            # 按钮文本
            if is_unlocked:
                btn_text = f"{i+1}.✅"
            elif is_free:
                btn_text = f"{i+1}.🆓"
            else:
                btn_text = f"{i+1}.🔴{points}"
            
            resource_row.append({
                "text": btn_text,
                "callback_data": f"hdhive_sr_{search_key2}_{i}"
            })
            if len(resource_row) == 2:  # 每行2个按钮
                keyboard["inline_keyboard"].append(resource_row)
                resource_row = []
        if resource_row:  # 添加剩余按钮
            keyboard["inline_keyboard"].append(resource_row)

        # 添加翻页按钮（如果有多页）
        if total_pages > 1:
            keyboard["inline_keyboard"].append([
                {
                    "text": "➡️ 下一页",
                    "callback_data": f"hdhive_page_{search_key2}_2"  # 第一页的下一页是第2页
                }
            ])

        msg = "\n".join(msg_lines)
        self._notify(chat_id, msg, platform, reply_markup=keyboard)

    def _unlock_and_transfer(self, search_key, index, chat_id, platform):
        """解锁资源并转存到115"""
        # 修复：使用 get 而不是 pop，避免翻页后缓存被删除导致其他页面无法点击
        cache = _search_cache.get(search_key)
        if not cache:
            self._notify(chat_id, "⚠️ 搜索已过期，请重新搜索", platform)
            return

        resources = cache.get("resources", [])
        if index >= len(resources):
            self._notify(chat_id, "⚠️ 资源不存在", platform)
            return

        resource = resources[index]
        # 解锁成功后删除缓存（可选，保留一段时间让用户可以重复解锁）
        # _search_cache.pop(search_key, None)
        slug = resource.get("slug", "")
        if not slug:
            self._notify(chat_id, "❌ 无法获取资源 slug", platform)
            return

        item_info = resource.get("item_info", {})
        title = item_info.get("title", "未知资源")

        self._log(f"一键解锁转存: {title}")
        self._notify(chat_id, f"🔓 <b>[影巢]</b> 正在解锁并转存...\n\n📦 {title}", platform)

        # 调用解锁 API
        result = self.unlock(slug, auto_transfer=False)
        if result.get("status") != "success":
            self._notify(chat_id, f"❌ [影巢] 解锁失败: {result.get('message', '未知错误')}", platform)
            return

        data = result.get("data", {})
        url = data.get("url", "")
        access_code = data.get("access_code", "")
        points_cost = data.get("points_cost", 0)
        already_owned = data.get("already_owned", False)

        if not url:
            self._notify(chat_id, f"⚠️ [影巢] 解锁成功但未获取到链接", platform)
            return

        # 拼接完整链接
        full_link = url
        if access_code:
            sep = "&" if "?" in url else "?"
            full_link = f"{url}{sep}password={access_code}"

        cost_msg = "（免费）" if points_cost == 0 else f"（{'已拥有' if already_owned else f'消耗 {points_cost} 积分'}）"

        # 触发115转存
        try:
            from app.plugins import get_plugin
            cloud115 = get_plugin("cloud115")
            if cloud115 and cloud115.enabled:
                bus.publish("bot.admin_message", full_link, chat_id, platform)
                self._notify(chat_id, f"✅ <b>[影巢]</b> 解锁成功 {cost_msg}\n\n📦 {title}\n🔄 正在自动转存到 115...", platform)
        except:
            # 没有115插件，直接展示链接
            link_display = f"<code>{url}</code>"
            if access_code:
                link_display += f"\n🔑 访问码: <code>{access_code}</code>"
            self._notify(chat_id, f"✅ <b>[影巢]</b> 解锁成功 {cost_msg}\n\n📦 {title}\n🔗 {link_display}", platform)

    def _process_hdhive_link(self, link, chat_id, platform):
        """处理单个影巢链接：提取slug → 解锁 → 获取115链接 → 转存"""
        import re
        # 从链接提取 slug: hdhive.com/resource/115/SLUG 或 hdhive.com/resource/SLUG
        m = re.search(r'hdhive\.com/resource/(?:\w+/)?([a-f0-9]+)', link)
        if not m:
            self._notify(chat_id, f"⚠️ [影巢] 无法解析链接", platform)
            return

        slug = m.group(1)
        self._log(f"解锁资源: {slug[:16]}...")

        # 调用解锁 API（不自动转存，由本方法统一处理）
        result = self.unlock(slug, auto_transfer=False)
        if result.get("status") != "success":
            self._notify(chat_id, f"❌ [影巢] 解锁失败: {result.get('message', '未知错误')}", platform)
            return

        data = result.get("data", {})
        url = data.get("url", "")
        access_code = data.get("access_code", "")
        title = data.get("title", "未知资源")
        points_cost = data.get("points_cost", 0)
        already_owned = data.get("already_owned", False)

        cost_msg = "（免费）" if points_cost == 0 else f"（{'已拥有' if already_owned else f'消耗 {points_cost} 积分'}）"

        if not url:
            self._notify(chat_id, f"⚠️ [影巢] 解锁成功但未获取到链接", platform)
            return

        # 拼接完整链接（带访问码）
        full_link = url
        if access_code:
            sep = "&" if "?" in url else "?"
            full_link = f"{url}{sep}password={access_code}"

        # 检查是否有115插件可以转存
        try:
            from app.plugins import get_plugin
            cloud115 = get_plugin("cloud115")
            if cloud115 and cloud115.enabled:
                # 通知管理员并自动触发115转存
                self._notify(chat_id, f"🔓 <b>[影巢] 资源已解锁</b>{cost_msg}\n\n📦 {title}\n🔗 正在自动转存到 115...", platform)
                # 发布到事件总线让115插件处理
                bus.publish("bot.admin_message", full_link, chat_id, platform)
                return
        except Exception: pass

        # 没有115插件，直接展示链接
        link_display = f"<code>{url}</code>"
        if access_code:
            link_display += f"\n🔑 访问码: <code>{access_code}</code>"
        self._notify(chat_id, f"🔓 <b>[影巢] 资源已解锁</b>{cost_msg}\n\n📦 {title}\n🔗 {link_display}", platform)

    def _notify(self, chat_id, text, platform, reply_markup=None, message_id=None):
        """发送或编辑消息
        
        Args:
            chat_id: 聊天ID
            text: 消息文本
            platform: 平台
            reply_markup: 键盘
            message_id: 消息ID（如果提供则编辑消息）
        """
        try:
            from app.domains.notifications.bot_service import bot
            if message_id and platform == "tg":
                # 编辑已有消息
                logger.info(f"[_notify] 编辑消息: chat_id={chat_id}, message_id={message_id}, platform={platform}")
                result = bot.edit_message(chat_id, message_id, text, reply_markup=reply_markup, platform=platform)
                logger.info(f"[_notify] 编辑结果: {result}")
            else:
                # 发送新消息
                logger.info(f"[_notify] 发送新消息: chat_id={chat_id}, message_id={message_id}, platform={platform}")
                bot.send_message(chat_id, text, reply_markup=reply_markup, platform=platform)
        except Exception as e:
            logger.error(f"[_notify] 异常: {e}")

    def _format_size(self, size_bytes):
        """格式化文件大小"""
        if not size_bytes:
            return "0B"
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f}{unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f}PB"

    # ==========================================
    # 自动签到线程
    # ==========================================
    def _checkin_loop(self):
        """自动签到线程
        
        签到逻辑：
        1. 每 60 秒检查一次时间
        2. 当时间匹配配置的签到时间（精确到分钟）时执行签到
        3. 每天只签到一次
        """
        import re
        
        # 启动延迟，等待插件完全加载
        time.sleep(30)
        last_checkin_date = None  # 记录上次签到日期
        
        while self._running and self._enabled:
            try:
                config = self._get_config()
                auto = config.get("auto_checkin", "")
                
                if "enabled" in auto:
                    now = datetime.datetime.now()
                    current_date = now.strftime("%Y-%m-%d")
                    
                    # 解析签到时间配置（格式：HH:MM 或 HH，默认 08:00）
                    checkin_time_str = config.get("checkin_time", "08:00").strip()
                    checkin_hour = 8
                    checkin_minute = 0
                    
                    # 支持多种格式：HH:MM、HH:MM:SS、纯数字（小时）
                    time_match = re.match(r'^(\d{1,2}):?(\d{2})?', checkin_time_str)
                    if time_match:
                        checkin_hour = int(time_match.group(1))
                        if time_match.group(2):
                            checkin_minute = int(time_match.group(2))
                    
                    # 边界检查
                    checkin_hour = max(0, min(23, checkin_hour))
                    checkin_minute = max(0, min(59, checkin_minute))
                    
                    # 检查是否到达签到时间（精确匹配小时和分钟）
                    if now.hour == checkin_hour and now.minute == checkin_minute and last_checkin_date != current_date:
                        is_gambler = "gambler" in auto
                        
                        logger.info(f"[影巢] 开始自动签到: 时间={checkin_hour:02d}:{checkin_minute:02d}, 赌狗模式={is_gambler}")
                        result = self.checkin(is_gambler=is_gambler)
                        last_checkin_date = current_date
                        
                        if result.get("status") == "success":
                            mode = "赌狗模式 🎲" if is_gambler else "普通模式"
                            self._log(f"自动签到完成 ({mode})")
                            
                            # 通知用户
                            if config.get("notify_enabled"):
                                # 构建详细的签到结果消息
                                data = result.get("data", {})
                                checked_in = data.get("checked_in", False)
                                points_earned = data.get("points_earned", 0)
                                total_points = data.get("total_points", 0)
                                signin_days = data.get("signin_days", 0)
                                checkin_message = data.get("message", "")
                                
                                # 判断是今日首次签到还是重复签到
                                if checked_in and points_earned > 0:
                                    title = "✅ [影巢] 自动签到成功"
                                    status_line = f"🎉 {checkin_message}"
                                elif checked_in:
                                    title = "✅ [影巢] 签到完成"
                                    status_line = f"💬 {checkin_message}"
                                else:
                                    # 今日已签到
                                    title = "ℹ️ [影巢] 今日已签到"
                                    status_line = f"💬 {checkin_message}"
                                
                                msg_lines = [
                                    f"{title}",
                                    f"",
                                    f"🎯 <b>签到模式：</b>{mode}",
                                ]
                                
                                if points_earned > 0:
                                    msg_lines.append(f"💰 <b>获得积分：</b>+{points_earned} 分")
                                
                                msg_lines.append(f"📊 <b>当前积分：</b>{total_points} 分")
                                
                                if signin_days > 0:
                                    msg_lines.append(f"📅 <b>累计签到：</b>{signin_days} 天")
                                
                                msg_lines.append(f"")
                                msg_lines.append(status_line)
                                
                                msg = "\n".join(msg_lines)
                                try:
                                    from app.domains.notifications.bot_service import bot
                                    bot.send_message("sys_notify", msg, platform="all")
                                except Exception as e:
                                    logger.error(f"[影巢] 发送签到通知失败: {e}")
                        else:
                            self._log(f"自动签到失败: {result.get('message', '')}")
                            
            except Exception as e:
                logger.error(f"[影巢] 自动签到检查异常: {e}")
                
            # 每 60 秒检查一次
            for _ in range(60):
                if not self._running:
                    return
                time.sleep(1)


# 搜索结果缓存
_search_cache = {}
# TMDB 选择缓存
_tmdb_cache = {}


def handle_hdhive_search_callback(data, chat_id, cq_id, platform):
    """处理搜索结果回调：一键解锁转存

    Args:
        data: callback_data，格式: hdhive_sr_{search_key}_{index}
    """
    parts = data.split("_")
    if len(parts) < 4 or parts[0] != "hdhive" or parts[1] != "sr":
        return False

    search_key = parts[2]
    try:
        index = int(parts[3])
    except ValueError:
        return False

    from app.plugins import get_plugin
    plugin = get_plugin("hdhive")
    if not plugin or not plugin.enabled:
        return True

    # 异步处理解锁转存
    threading.Thread(target=plugin._unlock_and_transfer, args=(search_key, index, chat_id, platform), daemon=True).start()

    return True


def handle_hdhive_tmdbpage_callback(data, chat_id, cq_id, platform, message_id=None):
    """处理 TMDB 分页回调

    Args:
        data: callback_data，格式: hdhive_tmdbprev_{page}_{keyword} 或 hdhive_tmdbnext_{page}_{keyword}
        message_id: 消息ID，用于编辑消息
    """
    logger.info(f"[影巢TMDB翻页] 收到回调: {data}")
    parts = data.split("_")
    if len(parts) < 4 or parts[0] != "hdhive":
        logger.warning(f"[影巢TMDB翻页] 格式错误: parts={parts}")
        return False
    
    if parts[1] not in ["tmdbprev", "tmdbnext", "tmdbpage"]:
        logger.warning(f"[影巢TMDB翻页] 类型错误: parts[1]={parts[1]}")
        return False
    
    try:
        page = int(parts[2])
    except ValueError:
        logger.warning(f"[影巢TMDB翻页] 页码解析失败: {parts[2]}")
        return False
    
    # 关键词可能包含下划线，所以要重新拼接
    keyword = "_".join(parts[3:])
    logger.info(f"[影巢TMDB翻页] keyword={keyword}, page={page}")

    from app.plugins import get_plugin
    plugin = get_plugin("hdhive")
    if not plugin or not plugin.enabled:
        logger.warning("[影巢TMDB翻页] 插件未启用")
        return True

    # 检查是否有本地缓存可以翻页（当 api_total_pages == 1 时）
    # 查找匹配的缓存（关键词相同，且是第1页的结果）
    local_page = None
    for key, cache in _tmdb_cache.items():
        if cache.get("keyword") == keyword and cache.get("page") == 1:
            total_pages = cache.get("total_pages", 1)
            if total_pages > 1 and page <= total_pages:
                # 使用本地缓存翻页
                local_page = page
                logger.info(f"[影巢TMDB翻页] 使用本地缓存翻页: keyword={keyword}, local_page={local_page}, total_pages={total_pages}")
                threading.Thread(target=plugin._show_tmdb_results_from_cache, args=(key, chat_id, platform, local_page, message_id), daemon=True).start()
                return True
    
    # 没有本地缓存，请求 TMDB
    logger.info(f"[影巢TMDB翻页] 启动搜索线程: keyword={keyword}, page={page}")
    threading.Thread(target=plugin._search_and_show, args=(keyword, chat_id, platform, page), daemon=True).start()

    return True


def handle_hdhive_tmdb_callback(data, chat_id, cq_id, platform):
    """处理 TMDB 选择回调：查询影巢 115 资源

    Args:
        data: callback_data，格式: hdhive_tmdb_{search_key}_{type}_{tmdb_id}
    """
    parts = data.split("_")
    if len(parts) < 5 or parts[0] != "hdhive" or parts[1] != "tmdb":
        return False

    search_key = parts[2]
    res_type = parts[3]  # movie or tv
    tmdb_id = parts[4]

    from app.plugins import get_plugin
    plugin = get_plugin("hdhive")
    if not plugin or not plugin.enabled:
        return True

    # 异步处理查询
    threading.Thread(target=plugin._search_tmdb_select, args=(search_key, res_type, tmdb_id, chat_id, platform), daemon=True).start()

    return True


def handle_hdhive_page_callback(data, chat_id, cq_id, platform, message_id=None):
    """处理翻页回调

    Args:
        data: callback_data，格式: hdhive_page_{search_key}_{target_page}
        message_id: 消息ID，用于编辑消息
    """
    logger.info(f"[影巢翻页] 收到回调: {data}, message_id={message_id}, platform={platform}")
    parts = data.split("_")
    if len(parts) < 4 or parts[0] != "hdhive" or parts[1] != "page":
        logger.warning(f"[影巢翻页] 回调格式错误: parts={parts}")
        return False

    search_key = parts[2]
    try:
        target_page = int(parts[3])  # 目标页码（直接是要跳转的页码）
    except ValueError:
        logger.warning(f"[影巢翻页] 页码解析失败: {parts[3]}")
        return False

    logger.info(f"[影巢翻页] search_key={search_key}, target_page={target_page}")

    from app.plugins import get_plugin
    plugin = get_plugin("hdhive")
    if not plugin or not plugin.enabled:
        logger.warning("[影巢翻页] 插件未启用")
        return True

    # 从缓存获取资源
    cache = _search_cache.get(search_key)
    if not cache:
        logger.warning(f"[影巢翻页] 缓存不存在或已过期, search_key={search_key}, cache_keys={list(_search_cache.keys())}")
        plugin._notify(chat_id, "⚠️ 搜索已过期，请重新搜索", platform, message_id=message_id)
        return True

    resources = cache.get("resources", [])
    tmdb_info = cache.get("tmdb_info", {})
    keyword = cache.get("keyword", "")
    logger.info(f"[影巢翻页] 缓存命中: resources={len(resources)}, keyword={keyword}, message_id={message_id}")

    PAGE_SIZE = 5
    total_resources = len(resources)
    total_pages = (total_resources + PAGE_SIZE - 1) // PAGE_SIZE

    # 边界检查
    if target_page < 1:
        target_page = 1
    if target_page > total_pages:
        target_page = total_pages

    start_idx = (target_page - 1) * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, total_resources)
    page_resources = resources[start_idx:end_idx]

    # 构建消息
    msg_lines = [
        f"🎬 <b>{tmdb_info.get('title', keyword)}</b> <b>({tmdb_info.get('year', '')})</b>",
        f"━━━━━━━━━━━━━━",
        f"📊 共 {total_resources} 个资源 | 第 {target_page}/{total_pages} 页",
        f""
    ]

    def build_resource_msg(r, idx):
        """构建单个资源卡片"""
        lines = []
        title = r.get("title") or "未知资源"
        size = r.get("share_size") or "未知大小"
        points = r.get("unlock_points")
        is_unlocked = r.get("is_unlocked", False)
        is_free = points is None or points == 0
        is_official = r.get("is_official", False)
        
        # 状态标签 - 放在标题后面
        if is_unlocked:
            status_str = " ✅已解锁"
        elif is_free:
            status_str = " 🆓免费"
        else:
            status_str = f" 🔴{points}分"
        
        # 官方资源标记
        official_str = " 👑官方" if is_official else ""
        
        # 分享人 - 从 user 对象获取
        user_obj = r.get("user", {})
        uploader = user_obj.get("username") or user_obj.get("name") or user_obj.get("nickname") or "" if user_obj else ""
        resolution = ", ".join(r.get("video_resolution", [])) if r.get("video_resolution") else ""
        source = ", ".join(r.get("source", [])) if r.get("source") else ""

        # 标题行：序号 + 标题 + 状态 + 官方
        lines.append(f"<b>{idx}. {title}{status_str}{official_str}</b>")
        lines.append(f"   📦 {size}")
        if resolution:
            lines.append(f"   🎬 {resolution}")
        if source:
            lines.append(f"   📀 {source}")
        if uploader:
            lines.append(f"   👤 分享: {uploader}")
        
        remark = r.get("remark", "")
        if remark:
            remark_short = remark[:50] + "..." if len(remark) > 50 else remark
            lines.append(f"   📝 {remark_short}")
        
        return "\n".join(lines)

    for i, r in enumerate(page_resources):
        msg_lines.append(build_resource_msg(r, start_idx + i + 1))
        msg_lines.append("")

    if total_pages > 1:
        msg_lines.append(f"💡 点击数字按钮解锁，或翻页查看更多")

    # 构建键盘
    keyboard = {"inline_keyboard": []}

    # 资源按钮（每行2个）
    resource_row = []
    for i, r in enumerate(page_resources):
        points = r.get("unlock_points")
        is_unlocked = r.get("is_unlocked", False)
        is_free = points is None or points == 0
        
        if is_unlocked:
            btn_text = f"{start_idx + i + 1}.✅"
        elif is_free:
            btn_text = f"{start_idx + i + 1}.🆓"
        else:
            btn_text = f"{start_idx + i + 1}.🔴{points}"
        
        resource_row.append({
            "text": btn_text,
            "callback_data": f"hdhive_sr_{search_key}_{start_idx + i}"
        })
        if len(resource_row) == 2:
            keyboard["inline_keyboard"].append(resource_row)
            resource_row = []
    if resource_row:
        keyboard["inline_keyboard"].append(resource_row)

    # 翻页按钮
    if total_pages > 1:
        prev_page = target_page - 1 if target_page > 1 else total_pages
        next_page = target_page + 1 if target_page < total_pages else 1
        keyboard["inline_keyboard"].append([
            {
                "text": "⬅️ 上一页",
                "callback_data": f"hdhive_page_{search_key}_{prev_page}"
            },
            {
                "text": f"{target_page}/{total_pages}",
                "callback_data": "hdhive_nop"
            },
            {
                "text": "➡️ 下一页",
                "callback_data": f"hdhive_page_{search_key}_{next_page}"
            }
        ])

    msg = "\n".join(msg_lines)
    # 使用编辑消息而不是发送新消息
    logger.info(f"[影巢翻页] 准备调用 _notify: chat_id={chat_id}, message_id={message_id}, platform={platform}")
    plugin._notify(chat_id, msg, platform, reply_markup=keyboard, message_id=message_id)
    logger.info(f"[影巢翻页] _notify 调用完成")

    return True


def handle_request_hdhive_callback(data, chat_id, cq_id, platform, tmdb_info=None):
    """处理求片通知的影巢搜索回调 - 直接复用现有的搜索展示逻辑
    
    Args:
        data: callback_data，格式:
              首次搜索: req_hdhive_{tmdb_id}_{media_type}_{seasons}_{title}
              翻页请求: req_hdhive_page_{tmdb_id}_{media_type}_{page}_{title}
              追新搜索: req_hdhive_ep_{tmdb_id}_{season}_{episodes}_{title}
    """
    parts = data.split("_")
    if len(parts) < 4 or parts[0] != "req" or parts[1] != "hdhive":
        return False
    
    from app.plugins import get_plugin
    plugin = get_plugin("hdhive")
    if not plugin or not plugin.enabled:
        logger.warning("[求片影巢] 影巢插件未启用")
        return True
    
    # 解析参数
    try:
        if parts[2] == "page":
            # 翻页请求: req_hdhive_page_{tmdb_id}_{media_type}_{page}_{title}
            tmdb_id = int(parts[3])
            media_type = parts[4]
            page = int(parts[5])
            title = "_".join(parts[6:]) if len(parts) > 6 else ""
        elif parts[2] == "ep":
            # 🔥 追新搜索: req_hdhive_ep_{tmdb_id}_{season}_{episodes}_{title}
            tmdb_id = int(parts[3])
            season = int(parts[4])  # 季号
            episodes = parts[5]  # 集数，如 "1,2"
            title = "_".join(parts[6:]) if len(parts) > 6 else ""
            media_type = "tv"  # 追新一定是剧集
            page = 1
            logger.info(f"[追新影巢] 解析: tmdb_id={tmdb_id}, season={season}, episodes={episodes}, title={title}")
        else:
            # 首次搜索: req_hdhive_{tmdb_id}_{media_type}_{seasons}_{title}
            tmdb_id = int(parts[2])
            media_type = parts[3]
            page = 1
            title = "_".join(parts[5:]) if len(parts) > 5 else ""
    except (ValueError, IndexError) as e:
        logger.error(f"[求片影巢] 参数解析失败: {data}, error: {e}")
        return False
    
    title = title.replace("-", " ")
    res_type = "movie" if media_type == "movie" else "tv"
    logger.info(f"[求片影巢] 搜索请求: tmdb_id={tmdb_id}, type={res_type}, title={title}, page={page}")
    
    # 构造 TMDB 选择结果，直接调用现有的 _search_tmdb_select 方法
    import hashlib
    search_key = hashlib.md5(f"req_{tmdb_id}".encode()).hexdigest()[:8]
    _tmdb_cache[search_key] = {
        "results": [{
            "type": res_type,
            "tmdb_id": tmdb_id,
            "title": title,
            "year": ""
        }],
        "keyword": title,
        "page": 1,
        "total_pages": 1,
        "total_results": 1
    }
    
    # 调用现有的搜索展示方法
    threading.Thread(
        target=plugin._search_tmdb_select, 
        args=(search_key, res_type, tmdb_id, chat_id, platform), 
        daemon=True
    ).start()
    
    return True


# ==========================================
# 求片通知影巢搜索回调（供 bot_service.py 调用）
# ==========================================
def handle_request_hdhive_search(data, chat_id, cq_id, platform):
    """处理求片通知的影巢搜索回调

    Args:
        data: callback_data，格式: req_hdhive_{tmdb_id}_{media_type}_{season}_{title}
              其中 title 可能包含下划线（已替换为-），需要特殊处理
    
    Returns:
        bool: 是否处理成功
    """
    parts = data.split("_")
    # 格式: req_hdhive_{tmdb_id}_{media_type}_{season}_{title}
    # parts[0] = "req", parts[1] = "hdhive", parts[2] = tmdb_id, parts[3] = media_type, parts[4] = season, parts[5:] = title
    if len(parts) < 5 or parts[0] != "req" or parts[1] != "hdhive":
        return False

    try:
        tmdb_id = int(parts[2])
        media_type = parts[3]  # movie 或 tv
        season_str = parts[4] if len(parts) > 4 else "0"
        # title 可能包含下划线（已替换为-），需要恢复
        title = "_".join(parts[5:]) if len(parts) > 5 else "未知"
        title = title.replace("-", " ")  # 恢复空格
    except (ValueError, IndexError):
        return False

    from app.plugins import get_plugin
    plugin = get_plugin("hdhive")
    if not plugin or not plugin.enabled:
        # 编辑原消息提示插件未启用
        try:
            from app.domains.notifications.bot_service import bot
            bot.send_message(chat_id, "⚠️ 影巢插件未启用，请先在后台配置影巢 API Key", platform=platform)
        except:
            pass
        return True

    # 异步处理搜索
    threading.Thread(
        target=_search_hdhive_for_request,
        args=(plugin, tmdb_id, media_type, title, chat_id, platform),
        daemon=True
    ).start()

    return True
