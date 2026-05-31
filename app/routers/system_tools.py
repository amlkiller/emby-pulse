import time
import requests
import logging
import sys
import datetime
import os
import asyncio
import threading

logger = logging.getLogger("uvicorn")
from collections import deque
from fastapi import APIRouter, Request
from app.routers.auth import is_admin_user  # 🔒 引入管理员权限检查
from app.core.config import cfg
from app.dao.system_tool_dao import check_system_db_readwrite, check_system_table_integrity
from app.infra.db.perf_stats import get_query_perf_stats
from app.queries.system_tool_queries import get_latest_playback_date
from app.utils.proxy_helper import get_safe_proxies  # 🔒 SSRF 安全代理读取
from app.core.security_utils import safe_error_message

router = APIRouter(prefix="/api/system", tags=["System Tools"])

@router.get("/perf")
def api_perf_status(request: Request):
    """性能状态概览（管理员）"""
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    process = None
    try:
        import psutil
        process = psutil.Process(os.getpid())
    except Exception:
        process = None

    image_cache = {"files": 0, "bytes": 0}
    try:
        from app.routers import proxy
        if os.path.exists(proxy.IMAGE_CACHE_DIR):
            for name in os.listdir(proxy.IMAGE_CACHE_DIR):
                path = os.path.join(proxy.IMAGE_CACHE_DIR, name)
                if os.path.isfile(path):
                    image_cache["files"] += 1
                    image_cache["bytes"] += os.path.getsize(path)
        image_cache["smart_image_cache"] = len(proxy.smart_image_cache)
        image_cache["max_bytes_per_image"] = proxy._image_max_bytes()
    except Exception:
        pass

    caches = {}
    try:
        from app.routers import media_request
        caches["community_cache"] = len(media_request._community_cache)
    except Exception:
        pass
    try:
        from app.routers import stats
        caches["dashboard_cached"] = stats._dashboard_cache.get("data") is not None
        caches["dashboard_cache_age"] = int(time.time() - stats._dashboard_cache.get("ts", 0)) if stats._dashboard_cache.get("ts") else None
    except Exception:
        pass

    return {
        "status": "success",
        "data": {
            "process": {
                "rss_mb": round(process.memory_info().rss / 1024 / 1024, 2) if process else None,
                "threads": process.num_threads() if process else threading.active_count(),
                "python_threads": threading.active_count(),
            },
            "queries": get_query_perf_stats(),
            "caches": caches,
            "image_cache": image_cache,
        }
    }

# ==================== 🔥 天气缓存 ====================
_weather_cache = {
    "data": None,       # 天气数据
    "city": None,       # 城市名
    "ts": 0,            # 缓存时间戳
    "expires": 0        # 过期时间戳
}
WEATHER_CACHE_TTL = 3600  # 1小时缓存
_weather_refresh_thread = None
_weather_refresh_running = False

def _fetch_weather_from_api(city: str) -> dict:
    """从天气 API 获取数据（内部函数）"""
    import urllib.parse
    headers = {"User-Agent": "Mozilla/5.0 (EmbyPulse)"}
    encoded_city = urllib.parse.quote(city)
    weather_source = cfg.get("weather_source", "wttr")

    # 和风天气
    if weather_source == "qweather":
        weather_key = cfg.get("weather_qweather_key", "")
        qw_host = cfg.get("weather_qweather_host", "").strip().rstrip("/")
        if weather_key and qw_host:
            try:
                auth_headers = {**headers, "X-QW-Api-Key": weather_key}
                loc_res = requests.get(f"https://{qw_host}/geo/v2/city/lookup?location={encoded_city}", headers=auth_headers, timeout=6)
                if loc_res.status_code == 200:
                    loc_data = loc_res.json()
                    if loc_data.get("code") == "200" and loc_data.get("location"):
                        loc_id = loc_data["location"][0]["id"]
                        w_res = requests.get(f"https://{qw_host}/v7/weather/now?location={loc_id}", headers=auth_headers, timeout=6)
                        if w_res.status_code == 200:
                            w = w_res.json()
                            if w.get("code") == "200":
                                now = w.get("now", {})
                                return {"success": True, "data": {"current_condition": [{"temp_C": now.get("temp", "--"), "humidity": now.get("humidity", "--"), "weatherDesc": [{"value": now.get("text", "未知")}], "lang_zh": [{"value": now.get("text", "")}]}]}}
            except Exception as e:
                print(f"[天气缓存] 和风天气获取失败: {e}")

    # 高德天气
    if weather_source == "amap":
        amap_key = cfg.get("weather_amap_key", "")
        if amap_key:
            try:
                res = requests.get(f"https://restapi.amap.com/v3/weather/weatherInfo?city={encoded_city}&key={amap_key}&extensions=base", headers=headers, timeout=6)
                if res.status_code == 200:
                    d = res.json()
                    if d.get("status") == "1" and d.get("lives"):
                        live = d["lives"][0]
                        return {"success": True, "data": {"current_condition": [{"temp_C": live.get("temperature", "--"), "humidity": live.get("humidity", "--"), "weatherDesc": [{"value": live.get("weather", "未知")}], "lang_zh": [{"value": live.get("weather", "")}]}]}}
            except Exception as e:
                print(f"[天气缓存] 高德天气获取失败: {e}")

    # 兜底：wttr.in
    proxies = get_safe_proxies()
    try:
        res = requests.get(f"https://wttr.in/{encoded_city}?format=j1&lang=zh", headers=headers, timeout=6)
        if res.status_code == 200:
            # 🔥 显式设置编码为 UTF-8，避免中文乱码
            res.encoding = 'utf-8'
            return {"success": True, "data": res.json()}
    except Exception: pass
    if proxies:
        try:
            res = requests.get(f"https://wttr.in/{encoded_city}?format=j1&lang=zh", proxies=proxies, headers=headers, timeout=6)
            if res.status_code == 200:
                # 🔥 显式设置编码为 UTF-8，避免中文乱码
                res.encoding = 'utf-8'
                return {"success": True, "data": res.json()}
        except Exception: pass

    return {"success": False, "message": "天气获取失败"}

def refresh_weather_cache(city: str = "北京", silent: bool = False):
    """刷新天气缓存"""
    global _weather_cache
    
    try:
        if not silent:
            print(f"[天气缓存] 正在刷新: {city}")
        
        result = _fetch_weather_from_api(city)
        
        if result.get("success"):
            now = time.time()
            _weather_cache = {
                "data": result["data"],
                "city": city,
                "ts": now,
                "expires": now + WEATHER_CACHE_TTL
            }
            if not silent:
                print(f"[天气缓存] ✅ 刷新成功: {city}")
            return True
        else:
            if not silent:
                print(f"[天气缓存] ❌ 刷新失败: {result.get('message', '未知错误')}")
            return False
    except Exception as e:
        if not silent:
            print(f"[天气缓存] ❌ 刷新异常: {e}")
        return False

def get_weather_cache(city: str = "北京") -> dict:
    """获取天气数据（优先缓存，过期时后台刷新）"""
    global _weather_cache
    
    now = time.time()
    
    # 缓存有效且城市匹配
    if (_weather_cache["data"] and 
        _weather_cache["city"] == city and 
        now < _weather_cache["expires"]):
        return {"success": True, "data": _weather_cache["data"], "cached": True}
    
    # 🔥 缓存过期或城市变更，异步后台刷新（不阻塞当前请求）
    # 如果有旧数据，先返回旧数据，后台刷新
    if _weather_cache["data"]:
        # 启动后台刷新线程
        import threading
        threading.Thread(target=refresh_weather_cache, args=(city, True), daemon=True).start()
        return {"success": True, "data": _weather_cache["data"], "cached": True, "refreshing": True}
    
    # 🔥 没有任何缓存数据时，才同步刷新（首次请求）
    refresh_weather_cache(city, silent=True)
    
    if _weather_cache["data"]:
        return {"success": True, "data": _weather_cache["data"], "cached": False}
    
    return {"success": False, "message": "天气获取失败"}

def _weather_background_refresh():
    """后台定时刷新天气缓存"""
    global _weather_refresh_running
    
    while _weather_refresh_running:
        try:
            # 每小时刷新一次
            time.sleep(WEATHER_CACHE_TTL)
            
            # 只刷新已缓存的城市（用户请求过的城市）
            if _weather_cache.get("city") and _weather_cache.get("data"):
                refresh_weather_cache(_weather_cache["city"], silent=True)
        except Exception as e:
            print(f"[天气缓存] 后台刷新异常: {e}")

def start_weather_cache_refresh():
    """启动天气缓存后台刷新"""
    global _weather_refresh_thread, _weather_refresh_running
    
    if _weather_refresh_thread and _weather_refresh_thread.is_alive():
        return
    
    _weather_refresh_running = True
    _weather_refresh_thread = threading.Thread(target=_weather_background_refresh, daemon=True)
    _weather_refresh_thread.start()
    print("[天气缓存] 🔄 后台定时刷新已启动（每小时）")

def preload_weather_cache():
    """启动时初始化天气缓存服务（不预热，等前端请求时再缓存）"""
    # 🔥 不预热，因为不知道用户设置的城市
    # 前端第一次请求时会触发缓存
    start_weather_cache_refresh()

# ==========================================
# 🔥 核心黑科技：全局底层流劫持器 (Stdout/Stderr Tee)
# 抛弃原生 logging 拦截，直接在最底层劫持所有 print() 和系统输出
# 保证你在网页端看到的日志，和 Docker 控制台 100% 绝对一致！
# ==========================================

# 初始化全局内存环形队列，最多保留 300 行防内存溢出
if not hasattr(sys, '_emby_pulse_log_queue'):
    sys._emby_pulse_log_queue = deque(maxlen=300)
    sys._emby_pulse_log_queue.append(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SYSTEM] 底层控制台流嗅探器已挂载，同步捕获全局 Print 与 Uvicorn 输出...")

# 🔥 新增：全局 debug 模式标志位
if not hasattr(sys, '_emby_pulse_debug_mode'):
    sys._emby_pulse_debug_mode = False  # 默认关闭 debug

class StreamTee:
    def __init__(self, original_stream):
        self.original_stream = original_stream
        self.buffer = ""

    def write(self, data):
        # 1. 保证原有的控制台/Docker正常输出
        try:
            self.original_stream.write(data)
        except Exception:
            pass

        # 🔥 新增：如果未开启 debug 模式，过滤掉 DEBUG 级别的日志输出
        # DEBUG 日志通常包含详细的请求/响应信息，适合排查问题但日常不需要
        if not sys._emby_pulse_debug_mode:
            # 检测是否为 DEBUG 级别的日志（常见特征：包含 DEBUG、Request、Response 等关键词）
            debug_indicators = ['DEBUG', 'DEBUG:', 'Request', 'Response', 'POST /', 'GET /', 'PUT /', 'DELETE /']
            if any(indicator in data for indicator in debug_indicators):
                return  # 未开启 debug 时跳过这些日志

        # 2. 同步将输出数据劫持到我们的内存队列中
        try:
            self.buffer += data
            if '\n' in self.buffer:
                lines = self.buffer.split('\n')
                # 只处理完整的行
                for line in lines[:-1]:
                    clean_line = line.strip()
                    if clean_line:
                        # 智能时间戳：如果原本的输出(如 print)没有时间戳，给它自动补上
                        if not clean_line.startswith('['):
                            ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            sys._emby_pulse_log_queue.append(f"[{ts}] {clean_line}")
                        else:
                            sys._emby_pulse_log_queue.append(clean_line)

                # 剩余未换行的部分放回 buffer 等待下一次拼接
                self.buffer = lines[-1]
        except Exception:
            pass

    def flush(self):
        try:
            self.original_stream.flush()
        except Exception:
            pass
            
    # 完美伪装成原生 stream，防止部分第三方库调用底层属性时报错
    def __getattr__(self, name):
        return getattr(self.original_stream, name)

# 动态替换标准输出流 (加上防重复挂载机制，完美适配热重载)
if not getattr(sys.stdout, '_is_tee', False):
    sys.stdout = StreamTee(sys.stdout)
    sys.stdout._is_tee = True

if not getattr(sys.stderr, '_is_tee', False):
    sys.stderr = StreamTee(sys.stderr)
    sys.stderr._is_tee = True


# ==========================================
# 往下是常规的系统诊断与读取逻辑
# ==========================================
def ping_url(url, proxies=None):
    start = time.time()
    try:
        res = requests.get(url, proxies=proxies, timeout=5)
        latency = int((time.time() - start) * 1000)
        return True, latency
    except Exception:
        return False, 0

@router.get("/network_check")
async def network_check(request: Request):
    # 🔒 安全检查：必须登录且为管理员
    if not request.session.get("user"):
        return {"error": "未授权"}
    if not is_admin_user(request):
        return {"error": "需要管理员权限"}
    
    proxies = get_safe_proxies()

    tg_ok, tg_ping = ping_url("https://api.telegram.org", proxies)

    tmdb_key = cfg.get("tmdb_api_key", "")
    tmdb_url = f"https://api.themoviedb.org/3/configuration?api_key={tmdb_key}" if tmdb_key else "https://api.themoviedb.org/3/"
    tmdb_ok, tmdb_ping = ping_url(tmdb_url, proxies)

    last_webhook = "暂无记录"
    try:
        latest_playback_date = get_latest_playback_date()
        if latest_playback_date:
            last_webhook = latest_playback_date
            if 'T' in last_webhook:
                last_webhook = last_webhook.replace('T', ' ')[:19]
    except Exception:
        pass

    # ==========================================
    # 🔥 新增：数据库健康检测
    # ==========================================
    db_integrity = {"ok": False, "msg": "未检测"}
    db_readwrite = {"ok": False, "msg": "未检测"}

    # 1. 数据库完整性检查 - 检查系统数据库表
    db_integrity = check_system_table_integrity()

    # 2. 数据库读写权限检查
    db_readwrite = check_system_db_readwrite()

    return {
        "success": True,
        "data": {
            "tg": {"ok": tg_ok, "ping": tg_ping},
            "tmdb": {"ok": tmdb_ok, "ping": tmdb_ping},
            "webhook": {"last_active": last_webhook},
            "db_integrity": db_integrity,
            "db_readwrite": db_readwrite
        }
    }

@router.get("/logs")
async def get_logs(request: Request, lines: int = 150):
    """直接从内存环形队列中读取最新日志"""
    # 🔒 安全检查：必须登录且为管理员
    user = request.session.get("user")
    if not user:
        return {"success": False, "msg": "未授权"}
    if not is_admin_user(request):
        return {"success": False, "msg": "需要管理员权限"}

    try:
        if not hasattr(sys, '_emby_pulse_log_queue'):
            return {"success": False, "msg": "日志服务未初始化"}
            
        logs_list = list(sys._emby_pulse_log_queue)[-lines:]
        return {"success": True, "data": "\n".join(logs_list)}
    except Exception as e:
        return {"success": False, "msg": safe_error_message(e)}

@router.post("/debug")
async def toggle_debug(req: Request):
    """动态热切换全局日志等级"""
    # 🔒 安全检查：必须登录且为管理员
    user = req.session.get("user")
    if not user:
        return {"success": False, "msg": "未授权"}
    if not is_admin_user(req):
        return {"success": False, "msg": "需要管理员权限"}

    data = await req.json()
    enable = data.get("enable", False)

    # 🔥 修复：同步更新全局 debug 标志位，控制 StreamTee 的日志过滤
    sys._emby_pulse_debug_mode = enable

    level = logging.DEBUG if enable else logging.INFO

    # 设置所有相关 logger 的级别
    for name in ["uvicorn", "uvicorn.error", "uvicorn.access", ""]:
        lg = logging.getLogger(name)
        lg.setLevel(level)
        # 同时设置所有 handler 的级别，防止 handler 自身的 level 过滤掉 DEBUG
        for handler in lg.handlers:
            handler.setLevel(level)

    if enable:
        print("======== DEBUG 模式已被控制中心动态开启 ========")
    else:
        # 🔥 修复：关闭 debug 时，使用不包含敏感关键词的方式输出，避免被过滤
        print("[SYSTEM] Debug 模式已关闭，日志输出已恢复为 INFO 级别")

    return {"success": True, "msg": f"Debug 模式已{'开启' if enable else '关闭'}"}


@router.post("/restart")
async def restart_system(req: Request):
    """重启 EmbyPulse 服务（Docker 环境下退出进程，由容器自动重启）"""
    # 🔒 安全检查：必须登录且为管理员
    if not req.session.get("user"):
        return {"success": False, "msg": "未授权"}
    if not is_admin_user(req):
        return {"success": False, "msg": "需要管理员权限"}

    import os, signal, threading
    print("🔄 [系统重启] 收到重启指令，3秒后退出进程...")
    def _delayed_exit():
        time.sleep(3)
        os.kill(os.getpid(), signal.SIGTERM)
    threading.Thread(target=_delayed_exit, daemon=True).start()
    return {"success": True, "msg": "重启指令已下发"}


@router.get("/weather")
def api_weather(request: Request, city: str = "北京"):
    """天气接口（后端缓存，1小时自动刷新）"""
    # 🔒 安全检查：必须登录且为管理员
    if not request.session.get("user"):
        return {"error": "未授权"}
    if not is_admin_user(request):
        return {"error": "需要管理员权限"}
    
    return get_weather_cache(city)


@router.post("/weather/refresh")
def api_weather_refresh(request: Request, city: str = "北京"):
    """强制刷新天气缓存"""
    # 🔒 安全检查：必须登录且为管理员
    if not request.session.get("user"):
        return {"success": False, "message": "未授权"}
    if not is_admin_user(request):
        return {"success": False, "message": "需要管理员权限"}
    
    success = refresh_weather_cache(city)
    if success:
        return {"success": True, "message": f"天气缓存已刷新: {city}"}
    return {"success": False, "message": "天气刷新失败"}


@router.get("/weather/status")
def api_weather_status(request: Request):
    """获取天气缓存状态"""
    # 🔒 安全检查：必须登录且为管理员
    if not request.session.get("user"):
        return {"error": "未授权"}
    if not is_admin_user(request):
        return {"error": "需要管理员权限"}
    
    global _weather_cache
    now = time.time()
    return {
        "success": True,
        "data": {
            "city": _weather_cache.get("city"),
            "cached": _weather_cache["data"] is not None,
            "ts": _weather_cache.get("ts"),
            "expires": _weather_cache.get("expires"),
            "ttl_seconds": max(0, int(_weather_cache.get("expires", 0) - now)),
            "is_expired": now >= _weather_cache.get("expires", 0)
        }
    }
