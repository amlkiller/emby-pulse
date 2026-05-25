import os
import json
import asyncio
import threading
import socket
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# 应用版本号（单一来源，修改版本只改这里）
APP_VERSION = "1.4.5"

# 🔥 安全：日志脱敏过滤器
from app.utils.sensitive_filter import SensitiveLogFilter

# 应用日志过滤器到所有 logger
for handler in logging.getLogger().handlers:
    handler.addFilter(SensitiveLogFilter())
for logger_name in ['uvicorn', 'uvicorn.access', 'uvicorn.error']:
    for handler in logging.getLogger(logger_name).handlers:
        handler.addFilter(SensitiveLogFilter())
print("[🔒 安全] 已启用日志脱敏过滤器")

# 🔒 安全：速率限制中间件
from app.core.rate_limiter import RateLimitMiddleware, start_cleanup_timer
start_cleanup_timer()

# 🔥 修复 SQLite "database is locked" 问题：全局 Monkey Patch
import sqlite3
_original_connect = sqlite3.connect

def _patched_connect(database, timeout=5.0, *args, **kwargs):
    """增强版 sqlite3.connect，自动启用 WAL 模式和更长超时"""
    # 如果调用方没有指定 timeout，使用 30 秒
    if timeout == 5.0:  # 默认值
        timeout = 30.0
    conn = _original_connect(database, timeout=timeout, *args, **kwargs)
    # 启用 WAL 模式提高并发
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")  # 30秒
        conn.execute("PRAGMA synchronous=NORMAL")  # 平衡性能和安全
    except:
        pass  # 只读数据库可能失败，忽略
    return conn

sqlite3.connect = _patched_connect
print("[🔧 SQLite] 已启用 WAL 模式 + 30秒超时（解决 database is locked）")
from app.core.session_middleware import DatabaseSessionMiddleware
from app.core.security_headers_middleware import SecurityHeadersMiddleware
from app.routers import dedupe
from app.routers import notify_rules
from app.routers import system_tools
from app.routers import pro
from app.routers import db_tools  # 🔥 数据库管理工具
from app.routers import messages  # 🔥 消息中心
from app.routers import api_tokens  # 🔑 API Token 管理

# 🔥 修复在这里：完整的引入语句
from app.services.risk_service import start_risk_monitor

from app.routers import insight
from app.core.config import PORT, CONFIG_DIR, FONT_DIR, cfg, DB_PATH, SYSTEM_DB_PATH
from app.core.database import init_db, DB_PATH, SYSTEM_DB_PATH, auto_migrate_system_db
from app.services.bot_service import bot
from app.services.user_bot_service import user_bot
from app.routers import media_request
from app.routers import points
from app.routers import plugins as plugins_router
# 🔥 引入所有路由
from app.routers import views, auth, users, stats, bot as bot_router, system, proxy, report, webhook, insight, tasks, history, calendar, search, clients, gaps, risk,notifications, notify_admin, pwa, audit
from app.plugins import discover_plugins, get_enabled_plugins

# 初始化目录和数据库
if not os.path.exists("static"): os.makedirs("static")
if not os.path.exists("templates"): os.makedirs("templates")
if not os.path.exists(CONFIG_DIR): os.makedirs(CONFIG_DIR)
if not os.path.exists(FONT_DIR): os.makedirs(FONT_DIR)

# 🔒 安全：启动时清空 Session 表（强制用户重新登录）
try:
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    # 检查表是否存在
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'")
    if c.fetchone():
        c.execute("DELETE FROM sessions")
        deleted_count = c.rowcount
        conn.commit()
        print(f"🔒 [安全] 已清空 {deleted_count} 个 Session，所有用户需要重新登录")
    else:
        print("🔒 [安全] Session 表不存在，跳过清理")
    conn.close()
except Exception as e:
    print(f"⚠️ [安全] 清空 Session 失败: {e}")

# 🔒 安全：启动时运行安全检查
try:
    from app.core.security_check import run_security_checks
    run_security_checks()
except Exception as e:
    print(f"[🔒 安全] 安全检查失败: {e}")

# 🔥 启动时自动检测并迁移系统数据（默认关闭，设置 AUTO_MIGRATE_DB=1 启用）
print("[🚀 启动] 正在检查数据库状态...")
auto_migrate_enabled = os.getenv("AUTO_MIGRATE_DB", "") == "1"
if auto_migrate_enabled:
    migrated = auto_migrate_system_db()
else:
    print("[🔄 迁移检测] 自动迁移已关闭，跳过（设置 AUTO_MIGRATE_DB=1 启用）")
    migrated = False
init_db(skip_migration=True)  # 迁移已在上面执行（或跳过）

# 🔥 自动补充缺失的系统表（新增功能，确保新部署不缺表）
from app.core.db_manager import ensure_tables
table_result = ensure_tables()
if table_result["created_tables"]:
    print(f"[🔧 自动修复] 已创建缺失表: {', '.join(table_result['created_tables'])}")

# 🔥 打印数据库状态
print(f"[📊 数据库] 系统库: {SYSTEM_DB_PATH} {'✅' if os.path.exists(SYSTEM_DB_PATH) else '❌'}")
print(f"[📊 数据库] 播放库: {DB_PATH} {'✅' if os.path.exists(DB_PATH) else '❌ (将使用API模式)'}")

# 🔥 启动天气缓存服务（后台定时刷新）
def _start_weather_service():
    import time
    time.sleep(10)  # 等待服务完全启动
    from app.routers.system_tools import preload_weather_cache
    preload_weather_cache()

threading.Thread(target=_start_weather_service, daemon=True).start()

# ==============================================================================
# 🔥 真·物理隔离：10308 专属 ASGI 独立引擎 (无视任何反代环境)
# ==============================================================================
async def user_portal_app(scope, receive, send):
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return

    elif scope["type"] == "http":
        path = scope.get("path", "")

        # 强制送去求片中心
        if path == "/":
            scope["path"] = "/request"
            scope["raw_path"] = b"/request"

        # 铁血隔离白名单：放行求片相关页面、静态资源、公开 API
        allowed = (
            "/request",
            "/request_login",
            "/static",
            "/favicon.ico",
            "/manifest.json",
            "/sw.js",
            "/apple-touch-icon.png",
            "/api/login",
            "/api/register",
            "/api/auth/settings",
            "/api/auth/avatar",
            "/api/requests",
            "/api/user/messages",
            "/api/user/announcements",
            "/api/user/my_series",
            "/api/user/request_update",
            "/api/user/points",
            "/api/user/mute_status",
            "/api/user/avatar",
            "/api/user/password",
            "/api/user/libraries",
            "/api/user/image",
            "/api/user/renew",
            "/api/announcements",
            "/api/wallpaper",
            "/api/proxy/",
            "/api/library/",
            "/api/pro/status",
            "/api/pro/activate",
            "/api/notifications",
            "/api/pwa/",
            "/api/ping",
            "/api/live",
            "/api/stats/dashboard",
            "/api/stats/badges",
            "/api/stats/trend",
            "/api/stats/user_details",
            "/api/stats/chart",
            "/api/stats/recent",
            "/api/stats/latest",
            "/api/stats/libraries",
            "/api/stats/top_movies",
            "/api/stats/monthly_stats",
            "/api/stats/recent_added",
            # "/api/stats/item_detail",  # 🔒 移除：非管理员可越权读取全量用户播放数据
            "/api/stats/poster_data",
            "/api/stats/live",
            "/api/points/config",
            "/api/points/rank",
            "/api/slot/",
            "/api/scratch/",
            "/api/wheel/",
            "/api/guess/",
            "/api/lottery/",
            "/invite",
        )
        # 明确禁止的敏感路径（即使前缀匹配也拦截）
        blocked = (
            "/api/system",
            "/api/settings",
            "/api/users",
            "/api/manage",
            "/api/tokens",
            "/api/bot",
            "/api/risk",
            "/api/audit",
            "/api/tasks",
            "/api/db",
            "/api/requests/refresh_cache",
            "/api/requests/clear_cache",
            "/api/requests/pending_notify",
        )
        if not scope["path"].startswith(allowed) or scope["path"].startswith(blocked):
            body = json.dumps({"detail": "非法越界，后台管理界面已被物理阻断"}).encode("utf-8")
            await send({"type": "http.response.start", "status": 403, "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": body})
            return

        await app(scope, receive, send)
    else:
        await app(scope, receive, send)

REQUEST_PORT = int(os.getenv("REQUEST_PORT", "10308"))

def start_10308_server():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, 'SO_REUSEPORT'):
            try: sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError: pass
        sock.bind(('0.0.0.0', REQUEST_PORT))
        sock.listen(100)
    except OSError:
        return

    import uvicorn
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # 错误日志才会打印，保证前台安静
    config = uvicorn.Config(app=user_portal_app, log_level="error")

    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None
    try:
        loop.run_until_complete(server.serve(sockets=[sock]))
    except BaseException:
        pass

# ==============================================================================
# 🔥 定制化纯中文启动面板 (一口气输出完毕防插队)
# ==============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 🔒 安全：Webhook Token 默认值自动生成（与 security_check.py 弱 token 列表保持一致）
    _weak_tokens = {"embypulse", "emby", "test", "123456", "password", ""}
    if cfg.get("webhook_token") in _weak_tokens:
        import secrets as _secrets
        new_token = _secrets.token_urlsafe(32)
        cfg.set("webhook_token", new_token)
        logging.getLogger("uvicorn").warning("[安全] Webhook Token 已自动生成（原为弱 token），请更新 Emby Webhook 配置")

    # 🔒 SSRF 防护：启动自检 proxy_url / wecom_proxy_url，发现内网/非法值时告警
    try:
        from app.utils.proxy_helper import audit_existing_proxy_config
        audit_existing_proxy_config()
    except Exception as _e:
        print(f"⚠️ proxy_helper 启动自检失败（忽略）: {_e}")

    bot.start()
    # 用户 TG 机器人（自动启动，无需手动保存配置）
    try:
        _token = cfg.get("tg_user_bot_token")
        if _token:
            user_bot.start()
    except Exception as _e:
        print(f"⚠️ 用户机器人启动异常: {_e}")
    # 唤醒 10308 独立守护引擎
    threading.Thread(target=start_10308_server, daemon=True).start()
    # 🔥 唤醒风控天眼
    start_risk_monitor()

    # 🔥 启动仪表盘缓存预热（后台异步执行，不阻塞启动）
    from app.routers.stats import preload_dashboard_cache, start_dashboard_cache_refresh_loop
    asyncio.create_task(preload_dashboard_cache())
    asyncio.create_task(start_dashboard_cache_refresh_loop())

    # 🔥 启动用户社区首页缓存刷新（后台定时刷新）
    def _start_community_cache_refresh():
        import time
        time.sleep(15)  # 等待服务完全启动
        from app.routers.media_request import _refresh_community_cache
        _refresh_community_cache()  # 首次刷新
        while True:
            time.sleep(300)  # 每 5 分钟刷新一次
            _refresh_community_cache()
    threading.Thread(target=_start_community_cache_refresh, daemon=True).start()

    # 🔒 安全：启动时清理过期会话，并启动定时清理（每小时）
    from app.core.session import cleanup_expired_sessions
    try:
        deleted = cleanup_expired_sessions()
        if deleted > 0:
            print(f"[Session] 已清理 {deleted} 个过期会话")
    except Exception as e:
        print(f"[Session] 清理失败: {e}")

    def _session_cleanup_loop():
        _logger = logging.getLogger("uvicorn")
        while True:
            try:
                deleted = cleanup_expired_sessions()
                if deleted > 0:
                    _logger.info(f"[Session] 已清理 {deleted} 个过期会话")
            except Exception as e:
                _logger.error(f"[Session] 清理失败: {e}")
            threading.Event().wait(3600)

    threading.Thread(target=_session_cleanup_loop, daemon=True).start()

    # 🔥 拿掉 sleep，把面板一口气打印完，绝对整齐！
    print("\n" + "="*55)
    print("🚀 [系统启动] EmbyPulse 双引擎初始化成功！")
    print("🤖 [消息通知] 机器人模块已就绪")
    print("🔥 [缓存预热] 仪表盘数据正在后台预热...")
    print("🎈 [用户社区] 首页缓存已启用，每 5 分钟自动刷新")
    print("👁️ [风险管控] 并发天眼已开启，时刻监控越界行为！")
    print(f"🌍 [核心后台] 管理员仪表盘运行在端口: {PORT}")
    print(f"🎈 [用户中心] 独立求片门户运行在端口: {REQUEST_PORT}")
    print("✅ [系统状态] 物理隔离架构已启动，安全防护中！")
    if user_bot.running: print("🤖 [Pro专属] 用户 TG 机器人已上线！")
    print("="*55 + "\n")

    yield

    print("\n" + "="*55)
    print("🛑 [系统关闭] 正在停止 EmbyPulse 服务...")
    bot.stop()
    user_bot.stop()
    print("💤 [系统关闭] 所有服务已安全退出。")
    print("="*55 + "\n")
# ==============================================================================

app = FastAPI(
    lifespan=lifespan,
    docs_url=None,  # 🔒 关闭 Swagger UI (/docs)
    redoc_url=None  # 🔒 关闭 ReDoc (/redoc)
)

# 🔒 全局异常处理器：未捕获异常统一返回脱敏响应，避免泄露堆栈
import traceback
import uuid
from fastapi import Request as _Request
from fastapi.responses import JSONResponse as _JSONResponse
from starlette.exceptions import HTTPException as _StarletteHTTPException

@app.exception_handler(Exception)
async def _global_exception_handler(request: _Request, exc: Exception):
    # HTTPException 走 FastAPI 默认处理，保留 status_code 与 detail
    if isinstance(exc, _StarletteHTTPException):
        raise exc
    request_id = uuid.uuid4().hex[:12]
    logging.getLogger("app.unhandled").error(
        f"[未捕获异常] request_id={request_id} path={request.url.path} "
        f"method={request.method}\n{traceback.format_exc()}"
    )
    return _JSONResponse(
        status_code=500,
        content={"error": "internal_error", "request_id": request_id},
    )

# 中间件
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)  # 🔒 速率限制
# 🔒 安全：CORS 默认拒绝所有跨域，需显式设置 CORS_ORIGINS 环境变量
_cors_env = os.getenv("CORS_ORIGINS", "").strip()
if _cors_env:
    allowed_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]
    # 安全检查：拒绝通配符和过于宽松的配置
    _dangerous = [o for o in allowed_origins if o in ("*", "null")]
    if _dangerous:
        print(f"🔒 [安全] CORS_ORIGINS 包含危险值 {_dangerous}，已忽略")
        allowed_origins = [o for o in allowed_origins if o not in ("*", "null")]
    if allowed_origins:
        print(f"🔒 [安全] CORS 已配置允许的来源: {allowed_origins}")
    else:
        print("🔒 [安全] CORS_ORIGINS 无有效值，已拒绝所有跨域请求")
else:
    allowed_origins = []
    print("🔒 [安全] CORS 未配置跨域来源，已拒绝所有跨域请求（如需开放请设置 CORS_ORIGINS 环境变量）")
from app.core.csrf_middleware import CSRFMiddleware
app.add_middleware(CSRFMiddleware)
app.add_middleware(DatabaseSessionMiddleware)  # Session 必须在 CSRF 之后添加（外层先执行），否则 CSRF 拿不到 session

app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_credentials=True, allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"], allow_headers=["Content-Type", "Authorization", "X-Requested-With", "X-Telegram-Bot-Api-Secret-Token"])

# 🔥 禁用浏览器缓存中间件（解决手机端缓存问题）
from starlette.middleware.base import BaseHTTPMiddleware
class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        # 🔥 对用户社区、HTML、API 响应禁用缓存
        is_no_cache_path = (
            request.url.path.endswith('.html') or
            request.url.path.startswith('/api/') or
            request.url.path == '/' or
            request.url.path.startswith('/request') or  # 🔥 用户社区
            request.url.path.startswith('/login') or    # 🔥 登录页
            request.url.path.startswith('/register')    # 🔥 注册页
        )
        if is_no_cache_path:
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, private'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            # 🔥 Vary 头告诉 CDN/代理不要基于请求头缓存
            response.headers['Vary'] = 'Cookie, Authorization'
        return response
app.add_middleware(NoCacheMiddleware)

# 静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")

# 公共文件（用于企微图片等）
import os
public_dir = os.path.join(os.getcwd(), "public")
if not os.path.exists(public_dir):
    os.makedirs(public_dir, exist_ok=True)
app.mount("/public", StaticFiles(directory=public_dir), name="public")

# 注册路由
app.include_router(views.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(stats.router)
app.include_router(bot_router.router)
app.include_router(system.router)
app.include_router(api_tokens.router)  # 🔑 API Token 管理
app.include_router(proxy.router)
app.include_router(report.router)
app.include_router(insight.router)
app.include_router(webhook.router)
app.include_router(tasks.router)
app.include_router(history.router)
app.include_router(calendar.router)
app.include_router(media_request.router)
app.include_router(search.router)
app.include_router(clients.router)
app.include_router(gaps.router)
app.include_router(risk.router)  # 🔥 挂载风控 API
app.include_router(notifications.router)  # 🔥 挂载全局通知 API
app.include_router(notify_admin.router)  # 🔥 挂载通知管理 API
app.include_router(dedupe.router)
app.include_router(notify_rules.router)
app.include_router(system_tools.router)
app.include_router(points.router)
app.include_router(pro.router)
app.include_router(db_tools.router)  # 🔥 数据库管理工具 API
app.include_router(messages.router)  # 🔥 消息中心 API
app.include_router(pwa.router)  # 🔥 PWA 自定义图标 API

# 🔥 日历通知 API
from app.routers import calendar_notify
app.include_router(calendar_notify.router)
# 启动日历通知服务
calendar_notify.init_calendar_notify_service()

# 🧩 发现并注册插件（必须在 plugins_router 之前注册，避免路由冲突）
discover_plugins()
for _p in get_enabled_plugins():
    try:
        app.include_router(_p.router)
    except Exception as e:
        print(f"[🧩 插件] 注册路由失败: {_p.id} - {e}")

# 注册插件管理路由（放在插件路由之后，避免动态路由抢占）
app.include_router(plugins_router.router)

# 🔒 审计日志路由
app.include_router(audit.router)

# 设置 app 引用，用于动态注册路由
plugins_router.set_app(app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
