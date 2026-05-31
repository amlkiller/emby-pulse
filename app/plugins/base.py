import threading
import logging
from fastapi import APIRouter, Request, HTTPException, Depends
from app.dao import plugin_dao

logger = logging.getLogger("uvicorn")

# 全局配置缓存 + 线程锁
_config_cache = {}
_config_cache_lock = threading.Lock()


def require_user(request: Request):
    """FastAPI 依赖：任意已登录用户可用。

    未登录返回 401。返回 session 中的 user 字典，便于端点直接使用。
    """
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return user


def require_admin(request: Request):
    """FastAPI 依赖：仅管理员可用。

    未登录 401，已登录非管理员 403。复用 is_admin_user 的判定语义。
    """
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    # 延迟导入避免循环依赖
    from app.routers.auth import is_admin_user
    if not is_admin_user(request):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


class PluginBase:
    # 插件元信息 (子类必须覆盖)
    id: str = ""              # 唯一标识，如 "cloud115"
    name: str = ""            # 显示名称，如 "115网盘转存"
    description: str = ""     # 一句话描述
    icon: str = "fa-puzzle-piece"  # FontAwesome 图标 class
    icon_color: str = "text-brand-500"  # 图标颜色 class
    version: str = "1.0.0"
    author: str = ""
    pro_only: bool = False    # 是否仅 Pro 用户可用
    permissions: list = []    # 插件声明需要的权限，如 ["db:read", "config:read", "event:subscribe"]

    def has_permission(self, perm: str) -> bool:
        """检查插件是否拥有指定权限"""
        return perm in self.permissions

    def __init__(self):
        self.router = APIRouter(
            prefix=f"/api/plugins/{self.id}",
            tags=[f"Plugin: {self.name}"],
            dependencies=[Depends(self._enabled_guard_dependency)],
        )
        self._enabled = False
        self._init_logs_table()
        # 初始化时加载配置到缓存
        self._load_config_to_cache()

    def _init_logs_table(self):
        """初始化插件日志表"""
        try:
            plugin_dao.ensure_plugin_tables()
        except Exception as e:
            import logging
            logging.getLogger("uvicorn").error(f"[{self.name}] 初始化日志表失败: {e}")

    @property
    def enabled(self):
        return self._enabled

    def enable(self):
        """启用插件时调用"""
        self._enabled = True
        self.on_enable()

    def disable(self):
        """禁用插件时调用"""
        self._enabled = False
        self.on_disable()

    def on_enable(self):
        """子类可覆盖：启用时的初始化逻辑"""
        pass

    def on_disable(self):
        """子类可覆盖：禁用时的清理逻辑"""
        pass

    async def _enabled_guard_dependency(self):
        """FastAPI 依赖：禁用的插件路由返回 404"""
        if not self._enabled:
            raise HTTPException(status_code=404, detail="插件未启用")

    def get_config_schema(self):
        """子类可覆盖：返回配置项定义列表"""
        return []

    def get_page_url(self):
        """子类可覆盖：返回插件页面路径，None 表示无独立页面"""
        return f"/plugins/{self.id}"

    def _load_config_to_cache(self):
        """从数据库加载配置到缓存"""
        global _config_cache
        try:
            with _config_cache_lock:
                _config_cache[self.id] = plugin_dao.get_plugin_config(self.id)
        except Exception:
            with _config_cache_lock:
                _config_cache[self.id] = {}

    def _get_config(self):
        """获取插件配置（从缓存读取，线程安全）"""
        with _config_cache_lock:
            return dict(_config_cache.get(self.id, {}))

    def _refresh_config_cache(self):
        """刷新配置缓存（保存配置后调用）"""
        self._load_config_to_cache()

    def _is_notification_enabled(self):
        """检查插件通知是否启用"""
        config = self._get_config()
        # 默认开启通知
        notify_enabled = config.get("notify_enabled")
        if notify_enabled is None:
            return True
        return notify_enabled in [True, "true", "1", 1]

    def log(self, message: str, level: str = "info", notify: bool = True):
        """
        记录插件日志

        Args:
            message: 日志内容
            level: 日志级别 (info, warning, error)
            notify: 是否发送到全局通知
        """
        import logging
        logger = logging.getLogger("uvicorn")

        # 写入本地日志表
        try:
            plugin_dao.add_plugin_log(self.id, level, message)
        except Exception as e:
            logger.error(f"[{self.name}] 写入日志失败: {e}")

        # 输出到控制台
        log_prefix = f"[{self.name}]"
        if level == "error":
            logger.error(f"{log_prefix} {message}")
        elif level == "warning":
            logger.warning(f"{log_prefix} {message}")
        else:
            logger.info(f"{log_prefix} {message}")

        # 发送到全局通知（如果启用）
        if notify and self._is_notification_enabled():
            try:
                from app.dao.notification_dao import add_sys_notification
                add_sys_notification("plugin", self.name, message, "/plugins")
            except Exception:
                pass

    def get_logs(self, limit: int = 50):
        """获取插件日志"""
        try:
            return [
                {"level": row["level"], "message": row["message"], "created_at": row["created_at"]}
                for row in plugin_dao.list_plugin_logs(self.id, limit)
            ]
        except Exception as e:
            logger.error(f"[{self.name}] 获取日志失败: {e}")
            return []

    def clear_logs(self):
        """清空插件日志"""
        try:
            plugin_dao.clear_plugin_logs(self.id)
            return True
        except Exception:
            return False

    def get_meta(self):
        """返回插件元信息字典，供前端渲染"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "icon_color": self.icon_color,
            "version": self.version,
            "author": self.author,
            "enabled": self._enabled,
            "page_url": self.get_page_url(),
            "config_schema": self.get_config_schema(),
            "pro_only": self.pro_only
        }
