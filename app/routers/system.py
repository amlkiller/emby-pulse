from fastapi import APIRouter, Request
from app.schemas.models import SettingsModel
from app.core.config import cfg, save_config
from app.routers.auth import is_admin_user  # 🔒 引入管理员权限检查
import requests
import os
import sqlite3
import logging
from app.core.security_utils import safe_error_message

logger = logging.getLogger("uvicorn")

router = APIRouter()

@router.get("/api/diag/config")
def api_diag_config(request: Request):
    """配置诊断 - 检查配置值是否正确"""
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    
    result = {
        "config_values": {},
        "env_values": {},
        "env_source": {},
        "issues": []
    }
    
    # 检查敏感字段
    sensitive_fields = {
        "tg_bot_token": "TG_BOT_TOKEN",
        "tg_user_bot_token": "TG_USER_BOT_TOKEN",
        "emby_api_key": "EMBY_API_KEY",
        "tmdb_api_key": "TMDB_API_KEY",
        "webhook_token": "WEBHOOK_TOKEN",
        "moviepilot_token": "MOVIEPILOT_TOKEN",
        "wecom_corpsecret": "WECOM_CORPSECRET",
        "wecom_token": "WECOM_TOKEN",
        "wecom_aeskey": "WECOM_AESKEY",
    }
    
    for config_key, env_key in sensitive_fields.items():
        env_val = os.getenv(env_key, "")
        config_val = cfg.get(config_key, "")
        source = cfg.get_env_source(config_key)
        
        result["env_values"][env_key] = {
            "set": bool(env_val),
            "length": len(env_val) if env_val else 0
        }
        result["config_values"][config_key] = {
            "length": len(config_val) if config_val else 0,
            "is_empty": not bool(config_val),
            "preview": "****" if config_val else "(空)"
        }
        result["env_source"][config_key] = source
        
        # 检查问题
        if env_val and not config_val:
            result["issues"].append(f"❌ {env_key} 已设置但 {config_key} 为空")
        elif env_val and config_val != env_val:
            result["issues"].append(f"⚠️ {config_key} 值与环境变量不一致")
    
    return result

@router.get("/api/diag/env")
def api_diag_env(request: Request):
    """环境变量诊断 - 帮助排查环境变量问题（安全版本）"""
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    
    import os
    from app.core.config import cfg
    
    # 检查敏感字段的环境变量
    sensitive_fields = {
        "tg_bot_token": "TG_BOT_TOKEN",
        "tg_user_bot_token": "TG_USER_BOT_TOKEN",
        "emby_api_key": "EMBY_API_KEY",
        "tmdb_api_key": "TMDB_API_KEY",
        "moviepilot_token": "MOVIEPILOT_TOKEN",
        "wecom_corpsecret": "WECOM_CORPSECRET",
        "wecom_token": "WECOM_TOKEN",
        "wecom_aeskey": "WECOM_AESKEY",
        "webhook_token": "WEBHOOK_TOKEN",
    }
    
    result = {
        "env_vars": {},
        "config_values": {},
        "env_source": {},
        "issues": []
    }
    
    for config_key, env_key in sensitive_fields.items():
        env_val = os.getenv(env_key, "")
        config_val = cfg.get(config_key, "")
        source = cfg.get_env_source(config_key)
        
        # 🔒 安全：只返回是否设置和长度，不返回任何实际值
        result["env_vars"][env_key] = {
            "set": bool(env_val),
            "length": len(env_val) if env_val else 0,
            "preview": "****" if env_val else "(未设置)"  # 不显示任何实际值
        }
        result["config_values"][config_key] = {
            "length": len(config_val) if config_val else 0,
            "preview": "****" if config_val else "(空)"  # 不显示任何实际值
        }
        result["env_source"][config_key] = source
        
        # 检查问题
        if env_val and not config_val:
            result["issues"].append(f"⚠️ {env_key} 已设置但 {config_key} 为空")
        elif env_val and config_val != env_val:
            result["issues"].append(f"⚠️ {config_key} 值与环境变量不一致")
        elif not env_val and not config_val:
            result["issues"].append(f"⚠️ {config_key} 未配置")
    
    return result

@router.get("/api/diag/db")
def api_diag_db(request: Request):
    """数据库诊断 - 帮助排查数据库问题"""
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}

    from app.core.database import DB_PATH, SYSTEM_DB_PATH

    result = {
        "db_path": DB_PATH,
        "db_exists": os.path.exists(DB_PATH),
        "tables": [],
        "issues": []
    }

    if not result["db_exists"]:
        result["issues"].append(f"数据库文件不存在: {DB_PATH}")
        result["issues"].append("请确保已正确挂载 Emby 插件的 playback_reporting.db")
        result["issues"].append("Docker 示例: -v /path/to/playback_reporting.db:/emby-data/playback_reporting.db")
        return result

    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        c = conn.cursor()

        # 获取所有表
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in c.fetchall()]
        result["tables"] = tables

        # 检查关键表
        required_tables = [
            "users_meta", "tg_user_bindings", "invitations",
            "PlaybackActivity", "point_config", "point_logs"
        ]
        for tbl in required_tables:
            if tbl not in tables:
                result["issues"].append(f"缺少表: {tbl} (可能是插件版本较旧)")

        # 检查 users_meta 的关键列
        if "users_meta" in tables:
            c.execute("PRAGMA table_info(users_meta)")
            cols = [row[1] for row in c.fetchall()]
            for col in ["expire_date", "points", "is_vip", "max_concurrent"]:
                if col not in cols:
                    result["issues"].append(f"users_meta 缺少列: {col}")

        # 检查 tg_user_bindings 表
        if "tg_user_bindings" not in tables:
            result["issues"].append("缺少 tg_user_bindings 表，机器人功能将无法使用")

        conn.close()

    except Exception as e:
        result["issues"].append(safe_error_message(e, "数据库读取错误"))

    return result

@router.get("/api/routes")
def api_get_routes(request: Request):
    """获取所有线路列表"""
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    routes = cfg.get_all_routes()
    # 返回线路名称和URL用于展示
    return {"status": "success", "data": routes}

@router.get("/api/settings")
def api_get_settings(request: Request):
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    
    # 🔒 安全：脱敏敏感字段
    def mask_sensitive(value, show_len=4):
        if not value or not isinstance(value, str):
            return ""
        if len(value) <= show_len * 2:
            return "****"
        return value[:show_len] + "****" + value[-show_len:]
    
    # 🔒 敏感字段列表
    SENSITIVE_FIELDS = [
        "emby_api_key", "tmdb_api_key", "moviepilot_token",
        "weather_qweather_key", "weather_amap_key"
    ]
    
    # 构建返回数据
    result_data = {
        "server_type": cfg.get("server_type", "emby"),
        "emby_host": cfg.get("emby_host"),
        "proxy_url": cfg.get("proxy_url"),
        "hidden_users": cfg.get("hidden_users") or [],
        "emby_public_url": cfg.get("emby_public_url", ""),
        "welcome_message": cfg.get("welcome_message", ""),
        "client_download_url": cfg.get("client_download_url", ""),
        "moviepilot_url": cfg.get("moviepilot_url", ""),
        "pulse_url": cfg.get("pulse_url", ""),
        "user_portal_url": cfg.get("user_portal_url", ""),
        "register_redirect_to_community": cfg.get("register_redirect_to_community", "false"),
        "playback_data_mode": cfg.get("playback_data_mode", "sqlite"),
        "notify_user_login": cfg.get("notify_user_login", False),
        "notify_item_deleted": cfg.get("notify_item_deleted", False),
        "weather_greeting": cfg.get("weather_greeting", ""),
        "weather_source": cfg.get("weather_source", "wttr"),
        "weather_qweather_host": cfg.get("weather_qweather_host", ""),
    }
    
    # 🔒 脱敏并标记敏感字段来源
    env_override_fields = []
    for field in SENSITIVE_FIELDS:
        value = cfg.get(field, "")
        source = cfg.get_env_source(field)
        
        if source == "env":
            # 来自环境变量：返回标记，不返回实际值
            result_data[field] = "****（由环境变量设置）"
            result_data[f"{field}_source"] = "env"
            result_data[f"{field}_readonly"] = True
            env_override_fields.append(field)
        else:
            # 来自配置文件：返回脱敏值
            result_data[field] = mask_sensitive(value)
            result_data[f"{field}_source"] = "config"
            result_data[f"{field}_readonly"] = False
    
    # 🔥 Webhook Token 特殊处理
    webhook_token = cfg.get("webhook_token", "")
    webhook_source = cfg.get_env_source("webhook_token")
    
    if webhook_source == "env":
        result_data["webhook_token"] = "****（由环境变量设置）"
        result_data["webhook_token_source"] = "env"
        result_data["webhook_token_readonly"] = True
        result_data["webhook_token_masked"] = "****"
        env_override_fields.append("webhook_token")
    else:
        result_data["webhook_token"] = webhook_token
        result_data["webhook_token_source"] = "config"
        result_data["webhook_token_readonly"] = False
        result_data["webhook_token_masked"] = mask_sensitive(webhook_token)
    
    result_data["env_override_fields"] = env_override_fields
    webhook_source = cfg.get_env_source("webhook_token")
    if webhook_source == "env":
        result_data["webhook_url"] = "（Webhook Token 由环境变量管理，请在 Emby 中配置 Header）"
    else:
        result_data["webhook_url"] = f"{cfg.get('emby_public_url', '') or cfg.get('emby_host', '')}/api/v1/webhook"
    result_data["webhook_header_name"] = "X-Webhook-Token"
    result_data["webhook_token_available"] = bool(webhook_token and webhook_token != "embypulse" and webhook_token not in ("emby", "test", "123456", "password"))
    
    return {"status": "success", "data": result_data}

@router.post("/api/settings")
def api_update_settings(data: SettingsModel, request: Request):
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    
    # 🔒 安全：检查是否应该更新敏感字段
    def should_update_sensitive(field, value):
        """检查敏感字段是否应该更新
        - 环境变量设置的字段不更新
        - 空值不更新（前端禁用时发送空字符串）
        - 包含脱敏标记 **** 的值不更新
        """
        # 检查是否来自环境变量
        if cfg.get_env_source(field) == "env":
            return False
        # 检查是否为空值（前端禁用时发送空字符串）
        if not value or value.strip() == "":
            return False
        # 检查是否包含脱敏标记
        if "****" in str(value):
            return False
        return True
    
    # 🔒 安全：URL 验证
    from app.utils.url_validator import validate_url, validate_emby_host
    
    # 验证 Emby Host
    emby_validation = validate_emby_host(data.emby_host)
    if not emby_validation["valid"]:
        return {"status": "error", "message": f"Emby 地址不合法: {emby_validation['error']}"}
    
    # 验证公网 URL（如果配置了）
    if data.emby_public_url:
        try:
            import json
            routes = json.loads(data.emby_public_url)
            if isinstance(routes, list):
                for route in routes:
                    route_url = route.get("url", "")
                    if route_url:
                        route_validation = validate_url(route_url, allow_internal=False)
                        if not route_validation["valid"]:
                            pass
            else:
                public_validation = validate_url(data.emby_public_url, allow_internal=False)
                if not public_validation["valid"]:
                    return {"status": "error", "message": f"公网地址不合法: {public_validation['error']}"}
        except json.JSONDecodeError:
            public_validation = validate_url(data.emby_public_url, allow_internal=False)
            if not public_validation["valid"]:
                return {"status": "error", "message": f"公网地址不合法: {public_validation['error']}"}
    
    # 记录变更前的值（用于审计日志）
    old_values = {
        "emby_host": cfg.get("emby_host"),
        "emby_api_key": cfg.get("emby_api_key"),
        "tmdb_api_key": cfg.get("tmdb_api_key"),
        "webhook_token": cfg.get("webhook_token"),
        "moviepilot_token": cfg.get("moviepilot_token"),
        "weather_qweather_key": cfg.get("weather_qweather_key"),
        "weather_amap_key": cfg.get("weather_amap_key"),
        "emby_public_url": cfg.get("emby_public_url"),
    }
    
    # 🔒 安全：敏感字段仅在非环境变量且非脱敏时更新
    # 提前获取需要验证连接的值
    emby_api_key_to_use = None
    if should_update_sensitive("emby_api_key", data.emby_api_key):
        emby_api_key_to_use = (data.emby_api_key or "").strip()
    else:
        emby_api_key_to_use = cfg.get("emby_api_key")
        env_source = cfg.get_env_source("emby_api_key")
        
        # 如果环境变量设置了但值为空，说明环境变量没有正确加载
        if env_source == "env" and not emby_api_key_to_use:
            return {"status": "error", "message": "环境变量 EMBY_API_KEY 未正确加载，请检查 Docker 配置"}
    
    # 🔥 只在 Emby host 或 API key 变化时才验证连接
    emby_host_changed = old_values["emby_host"] != data.emby_host
    emby_api_key_changed = emby_api_key_to_use != old_values["emby_api_key"]
    
    # 🔥 提前定义 server_type，避免 UnboundLocalError
    server_type = getattr(data, "server_type", "emby")
    
    if emby_host_changed or emby_api_key_changed:
        # 验证 Emby 连接
        url = f"{data.emby_host}/System/Info" if server_type == "jellyfin" else f"{data.emby_host}/emby/System/Info"
        headers = {"Authorization": f'MediaBrowser Token="{emby_api_key_to_use}"'} if server_type == "jellyfin" else {"X-Emby-Token": emby_api_key_to_use}
        
        try:
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code != 200:
                return {"status": "error", "message": "无法连接媒体服务器，请检查地址或 API Key"}
        except Exception as e:
            return {"status": "error", "message": "服务器地址无法访问"}

    # 保存所有配置
    cfg["server_type"] = server_type
    cfg["emby_host"] = data.emby_host
    
    # 🔒 敏感字段：仅在非环境变量且非脱敏时更新
    if should_update_sensitive("emby_api_key", data.emby_api_key):
        cfg["emby_api_key"] = (data.emby_api_key or "").strip()
    if should_update_sensitive("tmdb_api_key", data.tmdb_api_key):
        cfg["tmdb_api_key"] = (data.tmdb_api_key or "").strip()
    if should_update_sensitive("webhook_token", data.webhook_token):
        cfg["webhook_token"] = (data.webhook_token or "").strip()
    if should_update_sensitive("moviepilot_token", data.moviepilot_token):
        cfg["moviepilot_token"] = (data.moviepilot_token or "").strip()
    if should_update_sensitive("weather_qweather_key", data.weather_qweather_key):
        cfg["weather_qweather_key"] = (data.weather_qweather_key or "").strip()
    if should_update_sensitive("weather_amap_key", data.weather_amap_key):
        cfg["weather_amap_key"] = (data.weather_amap_key or "").strip()
    
    # 非敏感字段直接保存
    # 🔒 SSRF 防护：校验代理地址，禁止内网/回环
    from app.utils.url_validator import validate_proxy_url
    _proxy_check = validate_proxy_url(data.proxy_url or "")
    if not _proxy_check.get("valid"):
        return {"status": "error", "message": f"代理地址不合法: {_proxy_check.get('error', '')}"}
    cfg["proxy_url"] = data.proxy_url
    # 配置变更后失效 proxy_helper 缓存
    try:
        from app.utils.proxy_helper import invalidate_cache as _proxy_cache_invalidate
        _proxy_cache_invalidate()
    except Exception:
        pass
    cfg["hidden_users"] = data.hidden_users
    cfg["emby_public_url"] = data.emby_public_url
    cfg["welcome_message"] = data.welcome_message
    cfg["client_download_url"] = data.client_download_url
    cfg["moviepilot_url"] = data.moviepilot_url
    cfg["pulse_url"] = data.pulse_url
    cfg["user_portal_url"] = getattr(data, "user_portal_url", "")
    cfg["register_redirect_to_community"] = getattr(data, "register_redirect_to_community", "false")
    cfg["playback_data_mode"] = getattr(data, "playback_data_mode", "sqlite")
    cfg["notify_user_login"] = getattr(data, "notify_user_login", False)
    cfg["notify_item_deleted"] = getattr(data, "notify_item_deleted", False)
    cfg["weather_greeting"] = getattr(data, "weather_greeting", "")
    cfg["weather_source"] = getattr(data, "weather_source", "wttr")
    cfg["weather_qweather_host"] = getattr(data, "weather_qweather_host", "")
    
    save_config()
    
    # 🔒 审计日志：记录实际变更的字段
    from app.core.audit_logger import log_audit
    user = request.session.get("user", {})
    
    changed_fields = []
    # 检查哪些字段实际发生了变化
    if old_values["emby_host"] != data.emby_host:
        changed_fields.append("emby_host")
    if old_values["emby_public_url"] != data.emby_public_url:
        changed_fields.append("emby_public_url")
    if old_values["emby_api_key"] != data.emby_api_key:
        changed_fields.append("emby_api_key")
    if old_values["tmdb_api_key"] != data.tmdb_api_key:
        changed_fields.append("tmdb_api_key")
    if old_values["webhook_token"] != data.webhook_token:
        changed_fields.append("webhook_token")
    if old_values["moviepilot_token"] != data.moviepilot_token:
        changed_fields.append("moviepilot_token")
    if old_values["weather_qweather_key"] != getattr(data, "weather_qweather_key", ""):
        changed_fields.append("weather_qweather_key")
    if old_values["weather_amap_key"] != getattr(data, "weather_amap_key", ""):
        changed_fields.append("weather_amap_key")
    
    log_audit(
        action="config_update",
        user_id=str(user.get("id", "")),
        user_name=user.get("name", ""),
        ip_address=request.client.host if request.client else "",
        resource_type="system_settings",
        details={
            "page": "系统设置",
            "changed_fields": changed_fields,
            "server_type": server_type
        }
    )
    
    return {"status": "success", "message": "配置已保存"}

@router.post("/api/settings/weather_greeting")
async def api_update_weather_greeting(request: Request):
    """单独更新天气问候语（无需验证 Emby 连接）"""
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    
    data = await request.json()
    greeting = data.get("weather_greeting", "") if isinstance(data, dict) else ""
    cfg["weather_greeting"] = greeting
    save_config()
    
    return {"status": "success", "message": "问候语已保存"}

# 🔥 删除重复的同步版本 test_tmdb，保留下方的 async 版本

@router.post("/api/settings/test_mp")
async def test_moviepilot(request: Request):
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    data = await request.json()
    mp_url = data.get("mp_url", "").strip().rstrip('/')
    mp_token = data.get("mp_token", "").strip().strip("'\"")

    # 🔒 如果前端发送的是脱敏值，从配置中读取真实值
    if not mp_token or "****" in mp_token:
        mp_token = cfg.get("moviepilot_token", "")

    if not mp_url or not mp_token: return {"status": "error", "message": "请填写 MoviePilot 信息"}

    # 🔒 SSRF 防护：验证 MoviePilot URL 不指向内网
    from app.utils.url_validator import validate_url
    mp_validation = validate_url(mp_url, allow_internal=False)
    if not mp_validation["valid"]:
        return {"status": "error", "message": f"MoviePilot 地址不合法: {mp_validation['error']}"}

    try:
        res = requests.get(f"{mp_url}/api/v1/site/", headers={"X-API-KEY": mp_token, "User-Agent": "Mozilla/5.0"}, timeout=8)
        if res.status_code == 200: return {"status": "success", "message": "🎉 MoviePilot 连通测试成功！"}
        elif res.status_code in [401, 403]: return {"status": "error", "message": "❌ Token 认证失败"}
        else: return {"status": "success", "message": f"⚠️ 服务器连通(状态码: {res.status_code})"}
    except: return {"status": "error", "message": f"❌ 无法连接到 MoviePilot"}


@router.post("/api/settings/test_tmdb")
async def test_tmdb(request: Request):
    """测试 TMDB API 连通性"""
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    data = await request.json()
    api_key = data.get("api_key", "").strip()
    
    # 🔒 如果前端发送的是脱敏值，从配置中读取真实值
    if not api_key or "****" in api_key:
        api_key = cfg.get("tmdb_api_key", "")
    
    if not api_key: return {"status": "error", "message": "请填写 TMDB API Key"}
    
    # 获取代理设置
    from app.utils.proxy_helper import get_safe_proxies
    proxies = get_safe_proxies()
    
    try:
        # 使用 TMDB 配置接口测试
        res = requests.get(
            f"https://api.themoviedb.org/3/configuration?api_key={api_key}",
            proxies=proxies,
            timeout=10
        )
        if res.status_code == 200:
            data = res.json()
            if data.get("images"):
                return {"status": "success", "message": "🎉 TMDB API 连通测试成功！"}
            return {"status": "error", "message": "❌ API Key 无效"}
        elif res.status_code == 401:
            return {"status": "error", "message": "❌ API Key 无效或已过期"}
        elif res.status_code == 403:
            return {"status": "error", "message": "❌ API Key 权限不足"}
        else:
            return {"status": "error", "message": f"❌ 请求失败 (状态码: {res.status_code})"}
    except requests.exceptions.Timeout:
        return {"status": "error", "message": "❌ 连接超时，请检查网络或代理设置"}
    except requests.exceptions.ProxyError:
        return {"status": "error", "message": "❌ 代理连接失败，请检查代理地址"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e, "❌ 测试失败")}


@router.post("/api/settings/test_proxy")
async def test_proxy(request: Request):
    """测试代理连通性"""
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    data = await request.json()
    proxy_url = data.get("proxy_url", "").strip()
    if not proxy_url: return {"status": "error", "message": "请填写代理地址"}

    # 🔒 SSRF 防护：统一校验（scheme + 内网拦截）
    from app.utils.url_validator import validate_proxy_url
    _check = validate_proxy_url(proxy_url)
    if not _check.get("valid"):
        return {"status": "error", "message": f"❌ {_check.get('error', '代理地址不合法')}"}
    
    try:
        # 测试连接 Google（需要代理才能访问）
        res = requests.get(
            "https://www.google.com/favicon.ico",
            proxies={"http": proxy_url, "https": proxy_url},
            timeout=10
        )
        if res.status_code == 200:
            return {"status": "success", "message": "🎉 代理连通测试成功！"}
        return {"status": "error", "message": f"⚠️ 代理响应异常 (状态码: {res.status_code})"}
    except requests.exceptions.ProxyError:
        return {"status": "error", "message": "❌ 无法连接代理服务器"}
    except requests.exceptions.Timeout:
        return {"status": "error", "message": "❌ 代理连接超时"}
    except requests.exceptions.SSLError:
        return {"status": "error", "message": "❌ SSL 证书错误"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e, "❌ 测试失败")}


@router.post("/api/settings/fix_db")
def api_fix_db(request: Request):
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    from app.core.database import SYSTEM_DB_PATH
    import sqlite3
    import os
    if not os.path.exists(SYSTEM_DB_PATH): return {"status": "error", "message": "数据库不存在"}
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        results = []

        try: c.execute("SELECT 1 FROM PlaybackActivity LIMIT 1")
        except sqlite3.OperationalError:
            c.execute('''CREATE TABLE IF NOT EXISTS PlaybackActivity (Id INTEGER PRIMARY KEY AUTOINCREMENT, UserId TEXT, UserName TEXT, ItemId TEXT, ItemName TEXT, PlayDuration INTEGER, DateCreated DATETIME DEFAULT CURRENT_TIMESTAMP, Client TEXT, DeviceName TEXT)''')
            results.append("已修复: 播放活动主表")

        try: c.execute("SELECT 1 FROM users_meta LIMIT 1")
        except sqlite3.OperationalError:
            c.execute('''CREATE TABLE IF NOT EXISTS users_meta (user_id TEXT PRIMARY KEY, expire_date TEXT, note TEXT, created_at TEXT)''')
            results.append("已修复: 用户元数据表")

        try: 
            c.execute("SELECT 1 FROM invitations LIMIT 1")
            try: c.execute("SELECT template_user_id FROM invitations LIMIT 1")
            except sqlite3.OperationalError:
                c.execute("ALTER TABLE invitations ADD COLUMN template_user_id TEXT")
                results.append("已升级: 邀请码模板字段")
        except sqlite3.OperationalError:
            c.execute('''CREATE TABLE IF NOT EXISTS invitations (code TEXT PRIMARY KEY, days INTEGER, used_count INTEGER DEFAULT 0, max_uses INTEGER DEFAULT 1, created_at TEXT, used_at DATETIME, used_by TEXT, status INTEGER DEFAULT 0, template_user_id TEXT)''')
            results.append("已修复: 邀请码表")

        try: c.execute("SELECT 1 FROM tv_calendar_cache LIMIT 1")
        except sqlite3.OperationalError:
            c.execute('''CREATE TABLE IF NOT EXISTS tv_calendar_cache (id TEXT PRIMARY KEY, series_id TEXT, season INTEGER, episode INTEGER, air_date TEXT, status TEXT, data_json TEXT)''')
            results.append("已修复: 追剧日历缓存表")

        try: c.execute("SELECT 1 FROM media_requests LIMIT 1")
        except sqlite3.OperationalError:
            c.execute('''CREATE TABLE IF NOT EXISTS media_requests (tmdb_id INTEGER, media_type TEXT, title TEXT, year TEXT, poster_path TEXT, status INTEGER DEFAULT 0, season INTEGER DEFAULT 0, reject_reason TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (tmdb_id, season))''')
            results.append("已修复: 求片主表")

        try: c.execute("SELECT 1 FROM request_users LIMIT 1")
        except sqlite3.OperationalError:
            c.execute('''CREATE TABLE IF NOT EXISTS request_users (id INTEGER PRIMARY KEY AUTOINCREMENT, tmdb_id INTEGER, user_id TEXT, username TEXT, season INTEGER DEFAULT 0, requested_at DATETIME DEFAULT CURRENT_TIMESTAMP, UNIQUE(tmdb_id, user_id, season))''')
            results.append("已修复: 求片关联表")

        try: c.execute("SELECT 1 FROM insight_ignores LIMIT 1")
        except sqlite3.OperationalError:
            c.execute('''CREATE TABLE IF NOT EXISTS insight_ignores (item_id TEXT PRIMARY KEY, item_name TEXT, ignored_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
            results.append("已修复: 盘点忽略表")

        try: c.execute("SELECT 1 FROM gap_records LIMIT 1")
        except sqlite3.OperationalError:
            c.execute('''CREATE TABLE IF NOT EXISTS gap_records (id INTEGER PRIMARY KEY AUTOINCREMENT, series_id TEXT, series_name TEXT, season_number INTEGER, episode_number INTEGER, status INTEGER DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, UNIQUE(series_id, season_number, episode_number))''')
            results.append("已修复: 缺集记录表")

        conn.commit()
        conn.close()
        
        return {"status": "success", "message": f"修复完成: {', '.join(results)}" if results else "数据库8大核心表结构完整健康，无需修复！"}
    except Exception as e:
        return {"status": "error", "message": f"修复严重错误: {e}"}

# ==========================================
# 🔥 仪表盘布局持久化 (跨设备同步)
# ==========================================
@router.get("/api/dashboard/layout")
def api_get_dashboard_layout(request: Request):
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    import sqlite3, json
    from app.core.database import SYSTEM_DB_PATH
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        conn.execute("CREATE TABLE IF NOT EXISTS sys_dashboard (id INTEGER PRIMARY KEY DEFAULT 1, layout_json TEXT)")
        row = conn.execute("SELECT layout_json FROM sys_dashboard WHERE id = 1").fetchone()
        conn.close()
        if row and row[0]: return {"status": "success", "data": json.loads(row[0])}
    except Exception: pass
    return {"status": "success", "data": None}

@router.post("/api/dashboard/layout")
async def api_save_dashboard_layout(request: Request):
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    import sqlite3, json
    from app.core.database import SYSTEM_DB_PATH
    try:
        data = await request.json()
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        conn.execute("CREATE TABLE IF NOT EXISTS sys_dashboard (id INTEGER PRIMARY KEY DEFAULT 1, layout_json TEXT)")
        conn.execute("INSERT OR REPLACE INTO sys_dashboard (id, layout_json) VALUES (1, ?)", (json.dumps(data, ensure_ascii=False),))
        conn.commit(); conn.close()
        return {"status": "success", "message": "布局已保存"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e, "保存失败")}


# ==========================================
# 🔥 线路延迟检测（后端代理，绕过 CORS）
# ==========================================
@router.post("/api/ping")
async def api_ping(request: Request):
    """后端代理 ping 线路，返回延迟"""
    # 允许管理员和用户社区用户访问
    if not request.session.get("user") and not request.session.get("req_user"):
        return {"status": "error", "message": "权限不足"}
    try:
        import time
        from app.utils.url_validator import validate_url
        data = await request.json()
        url = data.get("url", "").strip()
        if not url: return {"status": "error", "message": "URL 不能为空"}

        # SSRF 防护
        validation = validate_url(url, allow_internal=False)
        if not validation["valid"]:
            return {"status": "error", "message": validation["error"]}

        # 确保 URL 以 / 结尾，然后请求根路径
        ping_url = url.rstrip("/") + "/"

        start = time.time()
        res = requests.get(ping_url, timeout=5, allow_redirects=False)
        latency = int((time.time() - start) * 1000)

        # 只要有响应（2xx/3xx/4xx/5xx）都算通
        return {"status": "success", "latency": latency, "http_code": res.status_code}
    except requests.exceptions.Timeout:
        return {"status": "error", "message": "timeout"}
    except Exception as e:
        logger.error(f"[Ping] 请求异常: {e}")
        return {"status": "error", "message": "请求失败"}