"""
Emby 服务器自动重启插件 (Pro 专享)
支持多台 Emby 服务器，通过 API 重启
"""
import logging
import threading
import time
import datetime
from fastapi import Request
from app.plugins.base import PluginBase
from app.routers.auth import is_admin_user  # 🔒 管理员鉴权
from app.core.config import cfg
from app.dao.emby_restart_dao import create_emby_restart_history, list_emby_restart_history
from app.infra.clients.media_server_client import media_api

logger = logging.getLogger("uvicorn")


class EmbyRestartPlugin(PluginBase):
    id = "emby_restart"
    name = "Emby 自动重启"
    description = "定时重启 Emby 服务器，避免内存溢出，支持多台服务器"
    icon = "fa-rotate"
    icon_color = "from-orange-500 to-red-500"
    version = "1.2.0"
    author = "EmbyPulse"
    pro_only = True  # Pro 专享

    def __init__(self):
        super().__init__()
        self.scheduler_thread = None
        self.scheduler_running = False
        self.last_restart = None
        self.restart_history = []
        self._load_history()  # 🔥 从数据库加载历史

    def _load_history(self):
        """从数据库加载重启历史"""
        try:
            rows = list_emby_restart_history(20)
            self.restart_history = [{
                "time": row["time"],
                "mode": row["mode"],
                "success": bool(row["success"]),
                "detail": row["detail"]
            } for row in reversed(rows)]  # 反转使最新的在最后
        except Exception as e:
            logger.error(f"[{self.name}] 加载历史失败: {e}")

    def _save_history(self, record):
        """保存重启历史到数据库"""
        try:
            create_emby_restart_history(record)
        except Exception as e:
            logger.error(f"[{self.name}] 保存历史失败: {e}")

    def on_enable(self):
        """启用插件"""
        self.log("Emby 自动重启插件已启用", notify=False)
        self._start_scheduler()

    def on_disable(self):
        """禁用插件"""
        self.log("Emby 自动重启插件已禁用", notify=False)
        self._stop_scheduler()

    def get_config_schema(self):
        """配置项定义 - 隐藏默认配置，全部在面板设置"""
        return []

    def _start_scheduler(self):
        """启动调度器"""
        if self.scheduler_running:
            return
        self.scheduler_running = True
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        logger.info(f"[{self.name}] 调度器已启动")

    def _stop_scheduler(self):
        """停止调度器"""
        self.scheduler_running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        logger.info(f"[{self.name}] 调度器已停止")

    def _scheduler_loop(self):
        """调度循环 - 每分钟检查一次"""
        last_check_minute = -1
        last_cron_check = None  # 🔥 cron 模式上次检查时间
        
        while self.scheduler_running:
            try:
                now = datetime.datetime.now()
                current_minute = now.hour * 60 + now.minute
                
                if current_minute == last_check_minute:
                    time.sleep(30)
                    continue
                last_check_minute = current_minute
                
                config = self._get_config()
                mode = config.get('restart_mode', 'disabled')
                
                if mode == 'disabled':
                    continue
                
                should_restart = False
                
                # 🔥 新增 cron 模式
                if mode == 'cron':
                    cron_expr = config.get('restart_cron', '')
                    if cron_expr:
                        try:
                            from croniter import croniter
                            cron = croniter(cron_expr, now)
                            prev_run = cron.get_prev(datetime.datetime)
                            # 如果上次运行时间在当前分钟内（允许 60 秒误差）
                            if last_cron_check is None:
                                # 首次检查，记录当前时间
                                last_cron_check = now
                            elif (now - prev_run).total_seconds() <= 60 and prev_run > last_cron_check:
                                # 上次运行时间在当前分钟内，且比上次检查时间新
                                should_restart = True
                                last_cron_check = now
                        except Exception as e:
                            logger.error(f"[{self.name}] cron 表达式解析失败: {e}")
                else:
                    restart_time = config.get('restart_time', '04:00')
                    try:
                        restart_hour, restart_minute = map(int, restart_time.split(':'))
                    except:
                        restart_hour, restart_minute = 4, 0
                    
                    target_minute = restart_hour * 60 + restart_minute
                    
                    if mode == 'daily':
                        if current_minute == target_minute:
                            should_restart = True
                    
                    elif mode == 'weekly':
                        weekdays = config.get('restart_weekdays', [])
                        if isinstance(weekdays, str):
                            weekdays = [w.strip() for w in weekdays.split(',') if w.strip()]
                        weekday_str = str(now.weekday() if now.weekday() > 0 else 7)
                        if weekday_str in weekdays and current_minute == target_minute:
                            should_restart = True
                    
                    elif mode == 'interval':
                        interval_days = int(config.get('interval_days', 3))
                        if interval_days <= 0:
                            interval_days = 3
                        
                        if current_minute == target_minute:
                            if self.last_restart is None:
                                should_restart = True
                            else:
                                days_since_last = (now - self.last_restart).days
                                if days_since_last >= interval_days:
                                    should_restart = True
                
                if should_restart:
                    self.log(f"触发定时重启，模式: {mode}", notify=False)
                    self._do_restart()
                
                time.sleep(30)
            except Exception as e:
                logger.error(f"[{self.name}] 调度器异常: {e}")
                time.sleep(60)

    def _do_restart(self):
        """执行重启"""
        config = self._get_config()
        servers = config.get('servers', [])
        
        if not servers:
            self.log("未配置 Emby 服务器", level="error", notify=True)
            return
        
        success_count = 0
        fail_count = 0
        errors = []
        
        for server in servers:
            name = server.get('name', '未命名')
            host = server.get('host', '')
            api_key = server.get('api_key', '')
            
            if not host or not api_key:
                fail_count += 1
                errors.append(f"{name}: 配置不完整")
                continue
            
            result = self._restart_via_emby_api(host, api_key)
            
            if result["success"]:
                success_count += 1
                self.log(f"服务器 [{name}] 重启成功", notify=False)
            else:
                fail_count += 1
                errors.append(f"{name}: {result.get('message', '未知错误')}")
                self.log(f"服务器 [{name}] 重启失败: {result.get('message')}", level="error", notify=False)
        
        # 记录历史
        self.last_restart = datetime.datetime.now()
        record = {
            "time": self.last_restart.strftime("%Y-%m-%d %H:%M:%S"),
            "mode": "restart",
            "success": fail_count == 0,
            "detail": f"成功 {success_count} 台，失败 {fail_count} 台"
        }
        self.restart_history.append(record)
        self._save_history(record)  # 🔥 保存到数据库
        
        if len(self.restart_history) > 20:
            self.restart_history = self.restart_history[-20:]
        
        # 汇总通知
        if fail_count == 0:
            self.log(f"全部 {success_count} 台 Emby 服务器重启成功", notify=True)
        else:
            error_msg = "\n".join(errors[:3])
            self.log(f"重启完成：成功 {success_count} 台，失败 {fail_count} 台\n{error_msg}", level="warning", notify=True)

    def _restart_via_emby_api(self, host: str, api_key: str) -> dict:
        """通过 Emby API 重启服务器"""
        if not host or not api_key:
            return {"success": False, "message": "配置不完整"}
        
        try:
            res = media_api.restart_server(host, api_key, timeout=10)
            if res.status_code == 204:
                return {"success": True, "message": "重启命令已发送"}
            else:
                return {"success": False, "message": f"API 返回 {res.status_code}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def manual_restart(self) -> dict:
        """手动重启"""
        self.log("触发手动重启", notify=False)
        self._do_restart()
        
        if self.restart_history:
            last = self.restart_history[-1]
            return {
                "success": last.get("success", False),
                "message": last.get("detail", "重启完成")
            }
        return {"success": False, "message": "重启执行异常"}

    def get_status(self) -> dict:
        """获取当前状态"""
        config = self._get_config()
        return {
            "enabled": self.enabled,
            "mode": config.get('restart_mode', 'disabled'),
            "last_restart": self.last_restart.strftime("%Y-%m-%d %H:%M:%S") if self.last_restart else "从未重启",
            "history": self.restart_history[-10:] if self.restart_history else [],
            "servers": config.get('servers', [])
        }


# 创建插件实例
plugin = EmbyRestartPlugin()


@plugin.router.get("/status")
async def get_status(request: Request):
    """获取插件状态"""
    # 🔒 鉴权检查
    if not request.session.get("user"):
        return {"success": False, "message": "未登录"}
    if not is_admin_user(request):
        return {"success": False, "message": "需要管理员权限"}
    return {"success": True, "data": plugin.get_status()}


@plugin.router.post("/restart")
async def manual_restart(request: Request):
    """手动重启所有服务器"""
    # 🔒 鉴权检查
    if not request.session.get("user"):
        return {"success": False, "message": "未登录"}
    if not is_admin_user(request):
        return {"success": False, "message": "需要管理员权限"}
    
    try:
        data = await request.json() if request.headers.get("content-type") == "application/json" else {}
    except:
        data = {}
    
    if not data.get("confirm"):
        return {"success": False, "message": "请确认重启操作"}
    
    result = plugin.manual_restart()
    return result


@plugin.router.post("/restart_single")
async def restart_single_server(request: Request):
    """重启单个服务器"""
    # 🔒 鉴权检查
    if not request.session.get("user"):
        return {"success": False, "message": "未登录"}
    if not is_admin_user(request):
        return {"success": False, "message": "需要管理员权限"}
    
    try:
        data = await request.json()
    except:
        return {"success": False, "message": "无效的请求数据"}
    
    index = data.get("index", -1)
    if index < 0:
        return {"success": False, "message": "请指定服务器"}
    
    config = plugin._get_config()
    servers = config.get('servers', [])
    
    if index >= len(servers):
        return {"success": False, "message": "服务器不存在"}
    
    server = servers[index]
    name = server.get('name', '未命名')
    host = server.get('host', '')
    api_key = server.get('api_key', '')
    
    if not host or not api_key:
        return {"success": False, "message": "服务器配置不完整"}
    
    result = plugin._restart_via_emby_api(host, api_key)
    
    if result["success"]:
        plugin.log(f"服务器 [{name}] 重启成功", notify=False)
        record = {
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "mode": "single",
            "success": True,
            "detail": f"服务器 [{name}]"
        }
        plugin.restart_history.append(record)
        plugin._save_history(record)  # 🔥 保存到数据库
        if len(plugin.restart_history) > 20:
            plugin.restart_history = plugin.restart_history[-20:]
    else:
        plugin.log(f"服务器 [{name}] 重启失败: {result.get('message')}", level="error", notify=False)
    
    return result


@plugin.router.get("/history")
async def get_history(request: Request):
    """获取重启历史"""
    # 🔒 鉴权检查
    if not request.session.get("user"):
        return {"success": False, "message": "未登录"}
    if not is_admin_user(request):
        return {"success": False, "message": "需要管理员权限"}
    return {"success": True, "data": plugin.restart_history[-20:]}


@plugin.router.get("/config")
async def get_config(request: Request):
    """获取插件配置"""
    # 🔒 鉴权检查
    if not request.session.get("user"):
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    from app.plugins import get_plugin_config
    return {
        "status": "success",
        "data": {
            "schema": plugin.get_config_schema(),
            "values": get_plugin_config(plugin.id)
        }
    }


@plugin.router.post("/config")
async def update_config(request: Request):
    """更新插件配置"""
    # 🔒 鉴权检查
    if not request.session.get("user"):
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    from app.plugins import save_plugin_config
    
    try:
        data = await request.json()
    except:
        return {"status": "error", "message": "无效的请求数据"}

    # 配置验证
    timeout = data.get("timeout")
    if timeout is not None:
        try:
            timeout = int(timeout)
            if timeout < 5 or timeout > 300:
                return {"status": "error", "message": "超时时间必须在 5-300 秒之间"}
            data["timeout"] = timeout
        except (ValueError, TypeError):
            return {"status": "error", "message": "超时时间必须为整数"}

    save_plugin_config(plugin.id, data)
    return {"status": "success", "message": "配置已更新"}


@plugin.router.get("/cron_explain")
async def explain_cron(request: Request, expr: str = ""):
    """解析 cron 表达式并返回人类可读的描述"""
    # 🔒 鉴权检查
    if not request.session.get("user"):
        return {"success": False, "message": "未登录"}
    if not is_admin_user(request):
        return {"success": False, "message": "需要管理员权限"}
    
    if not expr:
        return {"success": False, "message": "请提供 cron 表达式"}
    
    try:
        from croniter import croniter
        import datetime
        
        cron = croniter(expr, datetime.datetime.now())
        next_runs = [cron.get_next(datetime.datetime).strftime("%Y-%m-%d %H:%M") for _ in range(5)]
        
        # 简单的中文描述
        parts = expr.split()
        if len(parts) != 5:
            return {"success": False, "message": "cron 表达式格式错误，需要 5 个字段"}
        
        minute, hour, day, month, weekday = parts
        
        desc_parts = []
        if minute == "*" and hour == "*":
            desc_parts.append("每分钟")
        elif minute != "*" and hour == "*":
            desc_parts.append(f"每小时的第 {minute} 分钟")
        elif minute == "*" and hour != "*":
            desc_parts.append(f"每天 {hour} 点每分钟")
        elif minute != "*" and hour != "*":
            desc_parts.append(f"每天 {hour}:{minute.zfill(2)}")
        
        if day != "*":
            desc_parts.append(f"每月第 {day} 天")
        if month != "*":
            desc_parts.append(f"第 {month} 月")
        if weekday != "*":
            weekday_names = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"]
            try:
                wd = int(weekday)
                desc_parts.append(f"每{weekday_names[wd % 7]}")
            except:
                pass
        
        if not desc_parts:
            desc = "自定义时间"
        else:
            desc = "，".join(desc_parts)
        
        return {
            "success": True,
            "expression": expr,
            "description": desc,
            "next_runs": next_runs
        }
    except Exception as e:
        return {"success": False, "message": f"解析失败: {str(e)}"}
