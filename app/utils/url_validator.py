"""
URL 安全验证工具
防止 SSRF 攻击的基础防护
"""
from urllib.parse import urlparse
import re
import ipaddress


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

    # 处理 IPv6 方括号格式 (如 [::1]:8080)
    if domain.startswith('['):
        bracket_end = domain.find(']')
        if bracket_end > 0:
            ipv6_addr = domain[1:bracket_end]
            if is_internal_domain(ipv6_addr):
                return {"valid": False, "error": f"不允许访问内网地址: {ipv6_addr}"}
            return {"valid": True, "domain": ipv6_addr}

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
    - IPv6 环回和私有地址 (::1, fc00:, fd00:, fe80:)
    """
    domain = domain.lower().strip()

    # localhost
    if domain == 'localhost':
        return True

    # .local 域名
    if domain.endswith('.local'):
        return True

    # IPv6 环回和私有地址检查
    domain_clean = domain.strip('[]')
    ipv6_internal_prefixes = [
        '::1',
        '0:0:0:0:0:0:0:1',
        'fc00:',
        'fd00:',
        'fe80:',
    ]
    for prefix in ipv6_internal_prefixes:
        if domain_clean == prefix.rstrip(':') or domain_clean.startswith(prefix):
            return True

    # IPv4 地址检查
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


# 允许的代理 scheme
_ALLOWED_PROXY_SCHEMES = {"http", "https", "socks5", "socks5h", "socks4", "socks4a"}


def _hostname_is_internal(hostname: str) -> bool:
    """
    增强版内网判断：先用 ipaddress 模块（最准确），再回退到 is_internal_domain。
    """
    if not hostname:
        return True
    h = hostname.strip().strip('[]')
    # 先用 ipaddress 模块判断（覆盖所有 IPv4/IPv6 私网/回环/链路本地）
    try:
        ip = ipaddress.ip_address(h)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return True
        return False
    except ValueError:
        # 不是 IP，按域名判断
        return is_internal_domain(h)


def validate_proxy_url(url: str) -> dict:
    """
    校验代理 URL（用于 proxy_url 配置项）。

    - 空字符串视为合法（表示不使用代理）
    - scheme 必须在 {http, https, socks5, socks5h, socks4, socks4a}
    - hostname 必须为公网（IPv4/IPv6 私网、回环、链路本地一律拒绝）
    - 支持 user:pass@host:port userinfo 形式，仅校验 hostname 部分

    Returns:
        {"valid": bool, "error": str}
    """
    if url is None or url == "":
        return {"valid": True, "error": ""}

    if not isinstance(url, str):
        return {"valid": False, "error": "代理地址必须为字符串"}

    url = url.strip()
    if not url:
        return {"valid": True, "error": ""}

    try:
        parsed = urlparse(url)
    except Exception as e:
        return {"valid": False, "error": f"代理地址格式无效: {e}"}

    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_PROXY_SCHEMES:
        return {"valid": False, "error": f"不支持的代理协议: {scheme or '(空)'}，仅允许 http/https/socks5/socks5h/socks4/socks4a"}

    hostname = parsed.hostname  # urllib 自动剥离 userinfo 和端口
    if not hostname:
        return {"valid": False, "error": "代理地址缺少主机名"}

    if _hostname_is_internal(hostname):
        return {"valid": False, "error": f"不允许使用内网代理地址: {hostname}"}

    return {"valid": True, "error": ""}


# 企微默认基址，必须始终通过校验
WECOM_DEFAULT_BASE = "https://qyapi.weixin.qq.com"


def validate_wecom_proxy_base(url: str) -> dict:
    """
    校验企微代理基址（用于 wecom_proxy_url 配置项）。

    - 空字符串视为合法（运行时会回退默认值）
    - scheme 必须为 https（企微强制 TLS）
    - hostname 必须为公网
    - 默认值 https://qyapi.weixin.qq.com 必须通过

    Returns:
        {"valid": bool, "error": str}
    """
    if url is None or url == "":
        return {"valid": True, "error": ""}

    if not isinstance(url, str):
        return {"valid": False, "error": "企微代理地址必须为字符串"}

    url = url.strip()
    if not url:
        return {"valid": True, "error": ""}

    try:
        parsed = urlparse(url)
    except Exception as e:
        return {"valid": False, "error": f"企微代理地址格式无效: {e}"}

    scheme = (parsed.scheme or "").lower()
    if scheme != "https":
        return {"valid": False, "error": "企微代理地址必须使用 https"}

    hostname = parsed.hostname
    if not hostname:
        return {"valid": False, "error": "企微代理地址缺少主机名"}

    if _hostname_is_internal(hostname):
        return {"valid": False, "error": f"不允许使用内网企微代理地址: {hostname}"}

    return {"valid": True, "error": ""}
