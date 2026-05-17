"""
URL 安全验证工具
防止 SSRF 攻击的基础防护
"""
from urllib.parse import urlparse
import re


def validate_url(url: str, allow_internal: bool = False) -> dict:
    """
    验证 URL 是否安全
    
    Args:
        url: 要验证的 URL
        allow_internal: 是否允许内网地址（默认不允许）
    
    Returns:
        {"valid": bool, "error": str, "domain": str}
    """
    if not url:
        return {"valid": False, "error": "URL 不能为空"}
    
    # 基本格式验证
    try:
        parsed = urlparse(url)
    except Exception as e:
        return {"valid": False, "error": f"URL 格式无效: {e}"}
    
    # 检查协议
    if parsed.scheme not in ['http', 'https']:
        return {"valid": False, "error": f"不支持的协议: {parsed.scheme}，只允许 http/https"}
    
    # 检查域名
    domain = parsed.netloc
    if not domain:
        return {"valid": False, "error": "URL 缺少域名"}
    
    # 移除端口号
    if ':' in domain:
        domain = domain.split(':')[0]
    
    # 检查是否是内网地址
    if not allow_internal:
        if is_internal_domain(domain):
            return {"valid": False, "error": f"不允许访问内网地址: {domain}"}
    
    return {"valid": True, "domain": domain}


def is_internal_domain(domain: str) -> bool:
    """
    检查是否是内网域名或 IP
    
    包括：
    - localhost
    - 127.x.x.x
    - 10.x.x.x
    - 172.16-31.x.x
    - 192.168.x.x
    - 169.254.x.x (AWS 元数据)
    - .local 域名
    """
    domain = domain.lower()
    
    # localhost
    if domain == 'localhost':
        return True
    
    # .local 域名
    if domain.endswith('.local'):
        return True
    
    # IP 地址检查
    ip_pattern = r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$'
    match = re.match(ip_pattern, domain)
    
    if match:
        octets = [int(match.group(i)) for i in range(1, 5)]
        
        # 127.x.x.x (本地回环)
        if octets[0] == 127:
            return True
        
        # 10.x.x.x (A 类私有)
        if octets[0] == 10:
            return True
        
        # 172.16-31.x.x (B 类私有)
        if octets[0] == 172 and 16 <= octets[1] <= 31:
            return True
        
        # 192.168.x.x (C 类私有)
        if octets[0] == 192 and octets[1] == 168:
            return True
        
        # 169.254.x.x (链路本地/AWS 元数据)
        if octets[0] == 169 and octets[1] == 254:
            return True
    
    return False


def validate_emby_host(url: str) -> dict:
    """
    验证 Emby 服务器地址
    
    Args:
        url: Emby 服务器 URL
    
    Returns:
        {"valid": bool, "error": str}
    """
    result = validate_url(url, allow_internal=True)  # 允许内网，因为 Emby 可能在内网
    
    if not result["valid"]:
        return result
    
    # 检查是否包含路径
    parsed = urlparse(url)
    if parsed.path and parsed.path != '/':
        # 允许 /emby 等路径
        pass
    
    return {"valid": True}


def validate_webhook_url(url: str) -> dict:
    """
    验证 Webhook URL
    
    Args:
        url: Webhook URL
    
    Returns:
        {"valid": bool, "error": str}
    """
    # Webhook URL 必须是公网地址
    return validate_url(url, allow_internal=False)


# 预定义的合法域名白名单（可选）
ALLOWED_PROXY_DOMAINS = [
    "api.telegram.org",
    "qyapi.weixin.qq.com",
]


def is_allowed_proxy_domain(domain: str) -> bool:
    """
    检查是否是允许的代理域名
    
    Args:
        domain: 域名
    
    Returns:
        bool
    """
    domain = domain.lower()
    
    # 允许 Telegram API 相关域名
    if domain.endswith('.telegram.org') or domain == 'telegram.org':
        return True
    
    # 允许企业微信域名
    if domain.endswith('.weixin.qq.com') or domain == 'weixin.qq.com':
        return True
    
    return False
