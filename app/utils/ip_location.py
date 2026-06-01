"""
IP 归属地工具模块
统一用于 bot_service 和 history 等模块
"""
import re
import ipaddress
import logging
from app.infra.clients.ip_location_client import ip_location_client

logger = logging.getLogger("uvicorn")

# IP 缓存（归属地 + 运营商）
_ip_cache = {}
IP_CACHE_MAX_SIZE = 10000  # 最多缓存 10000 个 IP

def _cleanup_ip_cache():
    """清理 IP 缓存，保留最近的条目"""
    global _ip_cache
    if len(_ip_cache) > IP_CACHE_MAX_SIZE:
        # 保留最近的一半
        items = list(_ip_cache.items())
        _ip_cache = dict(items[-IP_CACHE_MAX_SIZE // 2:])
        logger.debug(f"[IP缓存] 已清理，当前大小: {len(_ip_cache)}")


def clean_location(loc: str) -> str:
    """清理归属地数据"""
    if not loc:
        return ""
    loc = re.sub(r'(中国|省|市|自治区|自治州|特别行政区|移动|联通|电信|铁通|教育网|广电|通信|数据中心|IDC)', ' ', loc)
    loc = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s]', ' ', loc)
    loc = re.sub(r'\s+', ' ', loc).strip()
    return loc


def _is_ipv6(ip: str) -> bool:
    """检查是否为 IPv6 地址"""
    try:
        ip_obj = ipaddress.ip_address(ip)
        return ip_obj.version == 6
    except:
        return False


def _is_private_ip(ip: str) -> bool:
    """检查是否为私有 IP"""
    try:
        ip_obj = ipaddress.ip_address(ip)
        return ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local
    except:
        return False


def get_location(ip: str) -> str:
    """获取 IP 归属地 - 多 API 备用方案"""
    if not ip:
        return ""

    # 检查缓存
    cache_key = f"{ip}_loc"
    if cache_key in _ip_cache:
        return _ip_cache[cache_key]

    # 检查是否为私有 IP
    if _is_private_ip(ip):
        _ip_cache[cache_key] = "局域网"
        _cleanup_ip_cache()
        return "局域网"

    # IPv6 地址尝试查询，失败则返回空（不显示错误位置）
    is_ipv6 = _is_ipv6(ip)

    loc = ""

    # API 1: open.ipw.cn
    try:
        res = ip_location_client.get_open_ipw_location(ip, timeout=3)
        if res.status_code == 200:
            d = res.json().get('data', {})
            if d.get('province') or d.get('city'):
                loc = f"{d.get('province', '')} {d.get('city', '')}"
                loc = clean_location(loc)
                if loc:
                    _ip_cache[cache_key] = loc
                    _cleanup_ip_cache()
                    return loc
    except:
        pass

    # API 2: ip.zxinc.org (备用)
    try:
        res = ip_location_client.get_ip_zxinc_location(ip, timeout=3)
        if res.status_code == 200:
            d = res.json()
            if d.get('data', {}).get('location'):
                loc = d.get('data', {}).get('location')
                loc = clean_location(loc)
                if loc:
                    _ip_cache[cache_key] = loc
                    _cleanup_ip_cache()
                    return loc
    except:
        pass

    # API 3: pconline (备用) - 仅对 IPv4 尝试
    if not is_ipv6:
        try:
            res = ip_location_client.get_pconline_location(ip, timeout=3)
            if res.status_code == 200:
                d = res.json()
                if d.get('pro') or d.get('city'):
                    loc = f"{d.get('pro', '')} {d.get('city', '')}"
                    loc = clean_location(loc)
                    if loc:
                        _ip_cache[cache_key] = loc
                        _cleanup_ip_cache()
                        return loc
        except:
            pass

    # IPv6 查询失败返回空字符串，避免显示错误位置
    _ip_cache[cache_key] = ""
    _cleanup_ip_cache()
    return ""


def get_isp(ip: str) -> str:
    """获取运营商信息"""
    if not ip:
        return ""

    # 检查缓存
    cache_key = f"{ip}_isp"
    if cache_key in _ip_cache:
        return _ip_cache[cache_key]

    # 检查是否为私有 IP
    if _is_private_ip(ip):
        _ip_cache[cache_key] = "局域网"
        _cleanup_ip_cache()
        return "局域网"

    # IPv6 不查询运营商
    if _is_ipv6(ip):
        _ip_cache[cache_key] = ""
        _cleanup_ip_cache()
        return ""

    isp = ""

    # API 1: open.ipw.cn
    try:
        res = ip_location_client.get_open_ipw_location(ip, timeout=3)
        if res.status_code == 200:
            d = res.json().get('data', {})
            isp = d.get('isp', '') or d.get('org', '')
            if isp:
                _ip_cache[cache_key] = isp
                _cleanup_ip_cache()
                return isp
    except:
        pass

    # API 2: pconline
    try:
        res = ip_location_client.get_pconline_location(ip, timeout=3)
        if res.status_code == 200:
            d = res.json()
            isp = d.get('isp', '') or d.get('addr', '')
            if isp:
                _ip_cache[cache_key] = isp
                _cleanup_ip_cache()
                return isp
    except:
        pass

    _ip_cache[cache_key] = isp
    _cleanup_ip_cache()
    return isp


def get_location_with_isp(ip: str) -> str:
    """获取归属地 + 运营商的组合字符串"""
    location = get_location(ip)
    isp = get_isp(ip)

    # 清理无效值
    if location in ["", "未知地区", "未知"]:
        location = ""
    if isp in ["", "未知运营商", "未知"]:
        isp = ""

    if location and isp:
        return f"{location} · {isp}"
    elif location:
        return location
    elif isp:
        return isp
    else:
        return ""


def clear_cache():
    """清理缓存"""
    global _ip_cache
    _ip_cache.clear()
