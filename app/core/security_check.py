"""
安全启动检查 - 首次启动时检查并修复安全问题
"""
import os
import secrets
import logging

from app.core.config import CONFIG_FILE
from app.infra.config.bot_settings import get_tg_bot_token, get_webhook_token, set_webhook_token
from app.infra.config.media_server_settings import get_media_server_api_key
from app.infra.config.proxy_settings import get_proxy_url
from app.infra.config.user_bot_settings import get_user_bot_token_or_empty

logger = logging.getLogger("uvicorn")

def generate_secure_token(length: int = 32) -> str:
    """生成安全的随机 Token"""
    return secrets.token_urlsafe(length)


def check_webhook_token():
    """检查 Webhook Token 是否为默认值"""
    current_token = get_webhook_token()
    default_tokens = ["embypulse", "emby", "test", "123456", "password", ""]
    
    if current_token in default_tokens:
        new_token = generate_secure_token(24)
        set_webhook_token(new_token)
        logger.warning("🔒 [安全] 检测到默认/空 Webhook Token，已自动生成安全 Token")
        logger.warning(f"   新 Token: {new_token[:8]}****{new_token[-8:]}")
        logger.warning("   请在 Emby Webhook 设置中更新此 Token")
        return False
    return True


def check_config_file_permissions():
    """检查配置文件权限"""
    if not os.path.exists(CONFIG_FILE):
        return True
    
    try:
        # 检查文件权限（仅 Unix）
        if os.name != 'nt':
            stat_info = os.stat(CONFIG_FILE)
            mode = stat_info.st_mode & 0o777
            if mode != 0o600:
                os.chmod(CONFIG_FILE, 0o600)
                logger.warning("🔒 [安全] 已将配置文件权限设置为 600")
    except Exception as e:
        logger.debug(f"检查配置文件权限失败: {e}")
    
    return True


def check_sensitive_tokens():
    """检查敏感 Token 是否配置"""
    warnings = []
    
    # 检查管理员机器人 Token
    token = get_tg_bot_token() or ""
    if token:
        if len(token) < 40 or ":" not in token:
            warnings.append("管理员机器人 Token 格式可能不正确")
    
    # 检查用户机器人 Token
    token = get_user_bot_token_or_empty()
    if token:
        if len(token) < 40 or ":" not in token:
            warnings.append("用户机器人 Token 格式可能不正确")
    
    # 检查 Emby API Key
    key = get_media_server_api_key() or ""
    if key:
        if len(key) < 32:
            warnings.append("Emby API Key 格式可能不正确")
    
    for warning in warnings:
        logger.warning(f"🔒 [安全] {warning}")
    
    return len(warnings) == 0


def check_proxy_security():
    """检查代理配置安全性"""
    proxy = get_proxy_url()
    
    if proxy:
        # 检查是否使用 HTTP 代理（不安全）
        if proxy.startswith("http://") and not proxy.startswith("http://127.0.0.1"):
            logger.warning("🔒 [安全] 检测到 HTTP 代理，建议使用 HTTPS 或 SOCKS5 代理")
            logger.warning(f"   当前代理: {proxy}")
            return False
    
    return True


def run_security_checks():
    """运行所有安全检查"""
    logger.info("🔒 [安全] 开始安全检查...")
    
    results = {
        "webhook_token": check_webhook_token(),
        "file_permissions": check_config_file_permissions(),
        "sensitive_tokens": check_sensitive_tokens(),
        "proxy_security": check_proxy_security(),
    }
    
    all_passed = all(results.values())
    
    if all_passed:
        logger.info("🔒 [安全] 安全检查通过")
    else:
        logger.warning("🔒 [安全] 安全检查发现问题，已自动修复部分问题")
    
    return all_passed


# 启动时自动运行
if __name__ != "__main__":
    # 被 import 时自动执行
    try:
        run_security_checks()
    except Exception as e:
        logger.debug(f"安全检查失败: {e}")
