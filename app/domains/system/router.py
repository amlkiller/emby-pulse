from fastapi import APIRouter, Request
from app.schemas.models import SettingsModel
from app.core.config import save_config
from app.routers.auth import is_admin_user  # 🔒 引入管理员权限检查
from app.dao.system_tool_dao import (
    get_dashboard_layout,
    repair_core_system_tables,
    save_dashboard_layout,
    system_database_exists,
)
from app.queries.system_tool_queries import diagnose_playback_database
import os
import logging
from app.core.security_utils import safe_error_message
from app.core.rate_limiter import get_client_ip
from app.infra.clients.media_server_client import media_api
from app.infra.clients.tmdb_client import tmdb_client
from app.infra.clients.moviepilot_client import moviepilot_client
from app.infra.clients.network_client import network_client
from app.infra.config.request_portal_settings import (
    get_client_download_url,
    get_pulse_url,
    get_redirect_to_community_value,
    get_user_portal_url,
    set_client_download_url,
    set_pulse_url,
    set_redirect_to_community_enabled,
    set_user_portal_url,
)
from app.infra.config.media_server_settings import get_media_server_routes
from app.infra.config.moviepilot_settings import get_moviepilot_token
from app.infra.config.system_settings import (
    get_system_config_env_source,
    get_system_config_value,
    get_system_emby_api_key,
    get_system_emby_host,
    get_system_emby_public_or_host,
    get_system_emby_public_url,
    get_system_hidden_users,
    get_system_moviepilot_url,
    get_system_notify_item_deleted,
    get_system_notify_user_login,
    get_system_playback_data_mode,
    get_system_proxy_url,
    get_system_server_type,
    get_system_tmdb_api_key,
    get_system_weather_amap_key,
    get_system_weather_greeting,
    get_system_weather_qweather_host,
    get_system_weather_qweather_key,
    get_system_weather_source,
    get_system_webhook_token,
    get_system_welcome_message,
    set_system_config_value,
)

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
        config_val = get_system_config_value(config_key, "")
        source = get_system_config_env_source(config_key)
        
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
        config_val = get_system_config_value(config_key, "")
        source = get_system_config_env_source(config_key)
        
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

    return diagnose_playback_database()

@router.get("/api/routes")
def api_get_routes(request: Request):
    """获取所有线路列表"""
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    routes = get_media_server_routes()
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
        "server_type": get_system_server_type(),
        "emby_host": get_system_emby_host(),
        "proxy_url": get_system_proxy_url(),
        "hidden_users": get_system_hidden_users(),
        "emby_public_url": get_system_emby_public_url(),
        "welcome_message": get_system_welcome_message(),
        "client_download_url": get_client_download_url(),
        "moviepilot_url": get_system_moviepilot_url(),
        "pulse_url": get_pulse_url(),
        "user_portal_url": get_user_portal_url(),
        "register_redirect_to_community": get_redirect_to_community_value(),
        "playback_data_mode": get_system_playback_data_mode(),
        "notify_user_login": get_system_notify_user_login(),
        "notify_item_deleted": get_system_notify_item_deleted(),
        "weather_greeting": get_system_weather_greeting(),
        "weather_source": get_system_weather_source(),
        "weather_qweather_host": get_system_weather_qweather_host(),
    }
    
    # 🔒 脱敏并标记敏感字段来源
    env_override_fields = []
    for field in SENSITIVE_FIELDS:
        value = get_system_config_value(field, "")
        source = get_system_config_env_source(field)
        
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
    webhook_token = get_system_webhook_token()
    webhook_source = get_system_config_env_source("webhook_token")
    
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
    if webhook_source == "env":
        result_data["webhook_url"] = "（Webhook Token 由环境变量管理，请在 Emby 中配置 Header）"
    else:
        result_data["webhook_url"] = f"{get_system_emby_public_or_host()}/api/v1/webhook"
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
        if get_system_config_env_source(field) == "env":
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
        "emby_host": get_system_emby_host(),
        "emby_api_key": get_system_emby_api_key(),
        "tmdb_api_key": get_system_tmdb_api_key(),
        "webhook_token": get_system_webhook_token(),
        "moviepilot_token": get_moviepilot_token(),
        "weather_qweather_key": get_system_weather_qweather_key(),
        "weather_amap_key": get_system_weather_amap_key(),
        "emby_public_url": get_system_emby_public_url(),
    }
    
    # 🔒 安全：敏感字段仅在非环境变量且非脱敏时更新
    # 提前获取需要验证连接的值
    emby_api_key_to_use = None
    if should_update_sensitive("emby_api_key", data.emby_api_key):
        emby_api_key_to_use = (data.emby_api_key or "").strip()
    else:
        emby_api_key_to_use = get_system_emby_api_key()
        env_source = get_system_config_env_source("emby_api_key")
        
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
        try:
            res = media_api.probe_settings(
                data.emby_host,
                emby_api_key_to_use,
                server_type=server_type,
                timeout=5,
            )
            if res.status_code != 200:
                return {"status": "error", "message": "无法连接媒体服务器，请检查地址或 API Key"}
        except Exception as e:
            return {"status": "error", "message": "服务器地址无法访问"}

    # 保存所有配置
    set_system_config_value("server_type", server_type)
    set_system_config_value("emby_host", data.emby_host)
    
    # 🔒 敏感字段：仅在非环境变量且非脱敏时更新
    if should_update_sensitive("emby_api_key", data.emby_api_key):
        set_system_config_value("emby_api_key", (data.emby_api_key or "").strip())
    if should_update_sensitive("tmdb_api_key", data.tmdb_api_key):
        set_system_config_value("tmdb_api_key", (data.tmdb_api_key or "").strip())
    if should_update_sensitive("webhook_token", data.webhook_token):
        set_system_config_value("webhook_token", (data.webhook_token or "").strip())
    if should_update_sensitive("moviepilot_token", data.moviepilot_token):
        set_system_config_value("moviepilot_token", (data.moviepilot_token or "").strip())
    if should_update_sensitive("weather_qweather_key", data.weather_qweather_key):
        set_system_config_value("weather_qweather_key", (data.weather_qweather_key or "").strip())
    if should_update_sensitive("weather_amap_key", data.weather_amap_key):
        set_system_config_value("weather_amap_key", (data.weather_amap_key or "").strip())
    
    # 非敏感字段直接保存
    # 🔒 SSRF 防护：校验代理地址，禁止内网/回环
    from app.utils.url_validator import validate_proxy_url
    _proxy_check = validate_proxy_url(data.proxy_url or "")
    if not _proxy_check.get("valid"):
        return {"status": "error", "message": f"代理地址不合法: {_proxy_check.get('error', '')}"}
    set_system_config_value("proxy_url", data.proxy_url)
    # 配置变更后失效 proxy_helper 缓存
    try:
        from app.utils.proxy_helper import invalidate_cache as _proxy_cache_invalidate
        _proxy_cache_invalidate()
    except Exception:
        pass
    set_system_config_value("hidden_users", data.hidden_users)
    set_system_config_value("emby_public_url", data.emby_public_url)
    set_system_config_value("welcome_message", data.welcome_message)
    set_client_download_url(data.client_download_url)
    set_system_config_value("moviepilot_url", data.moviepilot_url)
    set_pulse_url(data.pulse_url)
    set_user_portal_url(getattr(data, "user_portal_url", ""))
    set_redirect_to_community_enabled(getattr(data, "register_redirect_to_community", "false"))
    set_system_config_value("playback_data_mode", getattr(data, "playback_data_mode", "sqlite"))
    set_system_config_value("notify_user_login", getattr(data, "notify_user_login", False))
    set_system_config_value("notify_item_deleted", getattr(data, "notify_item_deleted", False))
    set_system_config_value("weather_greeting", getattr(data, "weather_greeting", ""))
    set_system_config_value("weather_source", getattr(data, "weather_source", "wttr"))
    set_system_config_value("weather_qweather_host", getattr(data, "weather_qweather_host", ""))
    
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
        ip_address=get_client_ip(request),
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
    set_system_config_value("weather_greeting", greeting)
    save_config()
    
    return {"status": "success", "message": "问候语已保存"}

# 🔥 删除重复的同步版本 test_tmdb，保留下方的 async 版本

@router.post("/api/settings/test_mp")
async def test_moviepilot(request: Request):
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    data = await request.json()
    mp_url = moviepilot_client.normalize_url(data.get("mp_url", ""))
    mp_token = moviepilot_client.normalize_token(data.get("mp_token", ""))

    # 🔒 如果前端发送的是脱敏值，从配置中读取真实值
    if not mp_token or "****" in mp_token:
        mp_token = get_moviepilot_token()

    if not mp_url or not mp_token: return {"status": "error", "message": "请填写 MoviePilot 信息"}

    # 🔒 SSRF 防护：验证 MoviePilot URL 不指向内网
    mp_validation = moviepilot_client.validate_url(mp_url)
    if not mp_validation["valid"]:
        return {"status": "error", "message": f"MoviePilot 地址不合法: {mp_validation['error']}"}

    try:
        res = moviepilot_client.test_site(mp_url, mp_token, timeout=8)
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
        api_key = get_system_tmdb_api_key() or ""
    
    if not api_key: return {"status": "error", "message": "请填写 TMDB API Key"}
    
    # 获取代理设置
    from app.utils.proxy_helper import get_safe_proxies
    proxies = get_safe_proxies()
    
    try:
        # 使用 TMDB 配置接口测试
        res = tmdb_client.get_configuration(api_key=api_key, proxies=proxies, timeout=10)
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
    except network_client.Timeout:
        return {"status": "error", "message": "❌ 连接超时，请检查网络或代理设置"}
    except network_client.ProxyError:
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
        res = network_client.test_proxy(
            "https://www.google.com/favicon.ico",
            proxies={"http": proxy_url, "https": proxy_url},
            timeout=10,
        )
        if res.status_code == 200:
            return {"status": "success", "message": "🎉 代理连通测试成功！"}
        return {"status": "error", "message": f"⚠️ 代理响应异常 (状态码: {res.status_code})"}
    except network_client.ProxyError:
        return {"status": "error", "message": "❌ 无法连接代理服务器"}
    except network_client.Timeout:
        return {"status": "error", "message": "❌ 代理连接超时"}
    except network_client.SSLError:
        return {"status": "error", "message": "❌ SSL 证书错误"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e, "❌ 测试失败")}


@router.post("/api/settings/fix_db")
def api_fix_db(request: Request):
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    if not system_database_exists(): return {"status": "error", "message": "数据库不存在"}
    try:
        results = repair_core_system_tables()
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
    try:
        layout = get_dashboard_layout()
        if layout is not None: return {"status": "success", "data": layout}
    except Exception: pass
    return {"status": "success", "data": None}

@router.post("/api/dashboard/layout")
async def api_save_dashboard_layout(request: Request):
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    try:
        data = await request.json()
        save_dashboard_layout(data)
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
        res = network_client.ping(ping_url, timeout=5, allow_redirects=False)
        latency = int((time.time() - start) * 1000)

        # 只要有响应（2xx/3xx/4xx/5xx）都算通
        return {"status": "success", "latency": latency, "http_code": res.status_code}
    except network_client.Timeout:
        return {"status": "error", "message": "timeout"}
    except Exception as e:
        logger.error(f"[Ping] 请求异常: {e}")
        return {"status": "error", "message": "请求失败"}
