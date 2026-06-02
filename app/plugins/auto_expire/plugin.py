"""
用户到期提醒插件 (Pro 专享)
到期前 N 天通过 TG 机器人提醒用户续费，同时通知管理员
"""
import time
import logging
import threading
import datetime
from fastapi import Request
from app.plugins.base import PluginBase
from app.domains.users import public_service as user_service
from app.domains.users import user_bot_dao, user_dao
from app.domains.notifications import public_service as notification_service
from app.infra.clients.media_server_client import media_api

logger = logging.getLogger("uvicorn")


class AutoExpirePlugin(PluginBase):
    id = "auto_expire"
    name = "用户到期提醒"
    description = "到期前自动提醒用户续费并通知管理员（Pro 专享）"
    icon = "fa-clock"
    icon_color = "from-amber-500 to-orange-500"
    version = "1.3.0"
    author = "EmbyPulse"

    def __init__(self):
        super().__init__()
        self._thread = None
        self._running = False
        self._stop_event = threading.Event()
        self._reminded_today = set()
        self._setup_routes()

    def _setup_routes(self):
        """注册 API 路由"""

        @self.router.get("/config")
        async def api_get_config(request: Request):
            """获取插件配置"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not user_service.is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            from app.plugins import get_plugin_config
            return {
                "status": "success",
                "data": {
                    "schema": self.get_config_schema(),
                    "values": get_plugin_config(self.id)
                }
            }

        @self.router.post("/config")
        async def api_update_config(request: Request):
            """更新插件配置"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not user_service.is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            from app.plugins import save_plugin_config
            try:
                data = await request.json()
            except:
                return {"status": "error", "message": "无效的请求数据"}
            save_plugin_config(self.id, data)
            return {"status": "success", "message": "配置已更新"}

        @self.router.post("/check_now")
        async def api_check_now(request: Request):
            """立即执行检测"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not user_service.is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            try:
                result = self._do_check(manual=True)
                if isinstance(result, dict) and result.get("error"):
                    return {"status": "error", "message": result["error"]}
                return {"status": "success", "data": result}
            except Exception as e:
                logger.error(f"[到期提醒] 立即检测失败: {e}")
                return {"status": "error", "message": str(e)}

        @self.router.get("/expiring_users")
        async def api_get_expiring_users(request: Request, days: int = 7):
            """获取即将到期的用户列表"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not user_service.is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            try:
                users = self._get_expiring_users(days)
                return {"status": "success", "data": users}
            except Exception as e:
                logger.error(f"[到期提醒] 获取用户列表失败: {e}")
                return {"status": "error", "message": str(e)}

        @self.router.post("/clean_deleted")
        async def api_clean_deleted_users(request: Request):
            """清理已删除用户的到期记录"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not user_service.is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            try:
                if not media_api.host or not media_api.api_key:
                    return {"status": "error", "message": "Emby API 未配置"}

                # 获取 Emby 中所有用户 ID
                emby_users = self._get_all_emby_users()
                emby_user_ids = set(emby_users.keys())

                # 获取 users_meta 中有过期日期的用户
                users = user_dao.list_user_ids_with_expire_date()
                if not users:
                    return {"status": "success", "data": {"cleaned": 0}}

                # 找出已删除的用户
                deleted_user_ids = [u['user_id'] for u in users if u['user_id'] not in emby_user_ids]
                if not deleted_user_ids:
                    return {"status": "success", "data": {"cleaned": 0}}

                cleaned = user_dao.delete_user_meta_many(deleted_user_ids)

                logger.info(f"[到期提醒] 清理了 {cleaned} 个已删除用户的到期记录")
                return {"status": "success", "data": {"cleaned": cleaned}}
            except Exception as e:
                logger.error(f"[到期提醒] 清理失败: {e}")
                return {"status": "error", "message": str(e)}

    def on_enable(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._check_loop, daemon=True, name="auto-expire-check")
        self._thread.start()
        logger.info("🔌 [到期提醒] 插件已启用")

    def on_disable(self):
        self._running = False
        self._stop_event.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=1)
        if not thread or not thread.is_alive():
            self._thread = None
        logger.info("🔌 [到期提醒] 插件已禁用")

    def get_config_schema(self):
        return [
            {"key": "remind_days", "label": "提前提醒天数", "type": "number", "placeholder": "3", "hint": "到期前多少天开始提醒用户，默认3天"},
            {"key": "notify_admin", "label": "同时通知管理员", "type": "toggle", "hint": "提醒用户的同时向管理员机器人发送汇总"},
            {"key": "check_interval", "label": "巡检间隔（小时）", "type": "number", "placeholder": "6", "hint": "每隔多少小时检查一次，默认6小时"},
            {"key": "auto_clean_deleted", "label": "自动清理已删除用户", "type": "toggle", "hint": "巡检时自动清理 Emby 中已删除用户的过期记录"},
            {"key": "notify_enabled", "label": "启用通知", "type": "toggle", "hint": "开启后，插件运行状态会发送到全局通知"},
        ]

    def _get_config(self):
        from app.plugins import get_plugin_config
        return get_plugin_config(self.id)

    def _is_pro(self):
        return True

    def _log(self, msg, level="info"):
        """记录日志（兼容旧代码）"""
        self.log(msg, level=level)

    def _check_loop(self):
        if self._stop_event.wait(60):
            return
        while self._running and self._enabled:
            if not self._is_pro():
                if self._stop_event.wait(3600):
                    return
                continue
            try:
                # 每天重置已提醒列表
                today_key = datetime.date.today().isoformat()
                if not hasattr(self, '_last_date') or self._last_date != today_key:
                    self._reminded_today = set()
                    self._last_date = today_key
                self._do_check()
            except Exception as e:
                logger.error(f"[到期提醒] 巡检异常: {e}")
            config = self._get_config()
            interval = max(1, int(config.get("check_interval") or 6)) * 3600
            for _ in range(interval // 10):
                if not self._running or not self._enabled: return
                if self._stop_event.wait(10):
                    return

    def _do_check(self, manual=False):
        config = self._get_config()
        remind_days = int(config.get("remind_days") or 3)
        notify_admin = config.get("notify_admin") in [True, "true", "1", 1]

        if not media_api.host or not media_api.api_key:
            if manual:
                return {"error": "Emby API 未配置"}
            return

        users = user_dao.list_users_with_expire_date()
        if not users:
            if manual:
                return {"count": 0, "users": [], "message": "没有设置到期日期的用户"}
            return

        # 批量获取 Emby 用户信息，避免逐个调用 API
        emby_users = self._get_all_emby_users()

        today = datetime.date.today()
        today_str = today.strftime("%Y-%m-%d")
        remind_date = (today + datetime.timedelta(days=remind_days)).strftime("%Y-%m-%d")

        expiring_users = []
        deleted_users = []
        for u in users:
            uid = u['user_id']; exp = u['expire_date']
            if uid in self._reminded_today and not manual: continue
            try:
                exp_date = datetime.datetime.strptime(exp, "%Y-%m-%d").date()
            except: continue

            # 检查用户是否在 Emby 中存在
            if emby_users and uid not in emby_users:
                deleted_users.append(uid)
                continue

            if today_str <= exp <= remind_date:
                days_left = (exp_date - today).days
                # 优先从缓存获取用户名
                username = self._get_username_from_cache(uid, emby_users)
                if not manual:
                    self._send_user_remind(uid, days_left, exp)
                    self._reminded_today.add(uid)
                expiring_users.append({"user_id": uid, "name": username, "days_left": days_left, "expire": exp})

        # 汇总通知管理员（非手动模式或手动模式且开启通知）
        if expiring_users and notify_admin:
            lines = [f"⏰ <b>用户到期提醒汇总</b>\n"]
            for u in expiring_users:
                lines.append(f"👤 {u['name']} — {u['days_left']}天后到期({u['expire']})")
            try:
                from app.domains.notifications import public_service as notification_service
                notification_service.send_message("sys_notify", "\n".join(lines), platform="all")
            except Exception: pass

        if expiring_users:
            print(f"[到期提醒] {'检测到' if manual else '已提醒'} {len(expiring_users)} 位即将到期用户")

        if deleted_users:
            logger.info(f"[到期提醒] 跳过 {len(deleted_users)} 个已删除用户: {deleted_users}")
            # 自动清理已删除用户的过期记录
            auto_clean = config.get("auto_clean_deleted") in [True, "true", "1", 1]
            if auto_clean:
                try:
                    cleaned = user_dao.delete_user_meta_many(deleted_users)
                    logger.info(f"[到期提醒] 自动清理了 {cleaned} 个已删除用户的过期记录")
                except Exception as e:
                    logger.error(f"[到期提醒] 自动清理失败: {e}")

        if manual:
            return {"count": len(expiring_users), "users": expiring_users, "remind_days": remind_days, "deleted_count": len(deleted_users)}

    def _get_expiring_users(self, days: int = 7):
        """获取即将到期的用户列表（用于面板展示）"""
        users = user_dao.list_users_with_expire_date()
        if not users:
            return []

        # 批量获取 Emby 用户信息
        emby_users = self._get_all_emby_users() if media_api.host and media_api.api_key else {}

        today = datetime.date.today()
        today_str = today.strftime("%Y-%m-%d")
        end_date = (today + datetime.timedelta(days=days)).strftime("%Y-%m-%d")

        result = []
        for u in users:
            uid = u['user_id']
            exp = u['expire_date']
            try:
                exp_date = datetime.datetime.strptime(exp, "%Y-%m-%d").date()
            except:
                continue

            if today_str <= exp <= end_date:
                days_left = (exp_date - today).days
                username = self._get_username_from_cache(uid, emby_users)
                # 如果用户不在 Emby 中且没有本地备注，标记为已删除
                is_deleted = emby_users and uid not in emby_users and username == uid
                result.append({
                    "user_id": uid,
                    "name": username,
                    "days_left": days_left,
                    "expire": exp,
                    "is_deleted": is_deleted
                })

        # 按剩余天数排序
        result.sort(key=lambda x: x['days_left'])
        return result

    def _get_username_from_cache(self, uid, emby_users=None):
        """从缓存或本地数据库获取用户名"""
        # 1. 先尝试从本地数据库获取
        try:
            binding = user_bot_dao.get_binding_by_emby_id(uid)
            if binding and binding.get("emby_username"):
                return binding["emby_username"]
            display_name = user_dao.get_user_display_name(uid)
            if display_name:
                return display_name
        except Exception as e:
            logger.debug(f"[到期提醒] 从本地获取用户名失败: {e}")
        
        # 2. 从 Emby 用户缓存获取
        if emby_users and uid in emby_users:
            return emby_users[uid]
        
        # 3. 返回 UID
        return uid

    def _send_user_remind(self, user_id, days_left, expire_date):
        try:
            if not notification_service.is_user_bot_running(): return
            # tg_user_bindings 表：tg_user_id 对应 emby_user_id
            chat_id = user_bot_dao.get_tg_user_id_by_emby_id(user_id)
            if not chat_id:
                return False
            msg = (f"⏰ <b>账号到期提醒</b>\n\n"
                   f"您的账号将在 <b>{days_left} 天后</b>（{expire_date}）到期。\n"
                   f"请及时续费以免服务中断。")
            notification_service.send_user_bot_message(chat_id, msg)
            print(f"[到期提醒] 已向用户 {user_id} (TG:{chat_id}) 发送到期提醒")
        except Exception as e:
            print(f"[到期提醒] ❌ 发送用户提醒失败: {e}")

    def _get_all_emby_users(self):
        """批量获取 Emby 用户信息，建立 ID -> Name 的映射"""
        users_map = {}
        try:
            res = media_api.get("/Users", timeout=10)
            if res.status_code == 200:
                for u in res.json():
                    users_map[u.get("Id")] = u.get("Name", u.get("Id"))
        except Exception as e:
            logger.warning(f"[到期提醒] 获取 Emby 用户列表失败: {e}")
        return users_map


# 创建插件实例
plugin = AutoExpirePlugin()
