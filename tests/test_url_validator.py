"""
URL 校验工具单元测试
覆盖 validate_url、validate_proxy_url 和 validate_wecom_proxy_base 的关键场景。
运行：pytest tests/test_url_validator.py -v
"""
import sys
import os

# 确保能够 import app
_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from app.utils.url_validator import (
    validate_url,
    validate_proxy_url,
    validate_wecom_proxy_base,
    WECOM_DEFAULT_BASE,
)


# ===== validate_url (CR-8 SSRF bypass coverage) =====

def test_validate_url_empty():
    assert validate_url("")["valid"] is False
    assert validate_url(None)["valid"] is False


def test_validate_url_bad_scheme():
    assert validate_url("ftp://example.com")["valid"] is False
    assert validate_url("file:///etc/passwd")["valid"] is False


def test_validate_url_no_domain():
    assert validate_url("http://")["valid"] is False


def test_validate_url_public_passes():
    r = validate_url("https://example.com/image.png")
    assert r["valid"] is True
    assert r["domain"] == "example.com"


def test_validate_url_allow_internal():
    r = validate_url("http://192.168.1.1/api", allow_internal=True)
    assert r["valid"] is True


def test_validate_url_loopback_rejected():
    assert validate_url("http://127.0.0.1:9300/")["valid"] is False


def test_validate_url_zero_address_rejected():
    """0.0.0.0 是 unspecified 地址，必须拒绝"""
    assert validate_url("http://0.0.0.0:9300/")["valid"] is False


def test_validate_url_decimal_ipv4_rejected():
    """十进制 IPv4 (2130706433 = 127.0.0.1) 必须拒绝"""
    assert validate_url("http://2130706433/")["valid"] is False


def test_validate_url_ipv4_shorthand_rejected():
    """127.1 是 127.0.0.1 的简写，必须拒绝"""
    assert validate_url("http://127.1/")["valid"] is False


def test_validate_url_ipv4_mapped_ipv6_rejected():
    """::ffff:127.0.0.1 是 IPv4-mapped IPv6 回环，必须拒绝"""
    assert validate_url("http://[::ffff:127.0.0.1]/")["valid"] is False


def test_validate_url_ipv6_unspecified_rejected():
    """:: 是 IPv6 unspecified 地址，必须拒绝"""
    assert validate_url("http://[::]/")["valid"] is False


def test_validate_url_cgnat_rejected():
    """100.64.0.1 是 CGNAT 地址 (RFC 6598)，必须拒绝"""
    assert validate_url("http://100.64.0.1/")["valid"] is False


def test_validate_url_link_local_rejected():
    assert validate_url("http://169.254.169.254/latest/meta-data/")["valid"] is False


def test_validate_url_private_a_rejected():
    assert validate_url("http://10.0.0.1/")["valid"] is False


def test_validate_url_private_b_rejected():
    assert validate_url("http://172.16.0.1/")["valid"] is False


def test_validate_url_private_c_rejected():
    assert validate_url("http://192.168.1.1/")["valid"] is False


def test_validate_url_localhost_rejected():
    assert validate_url("http://localhost:8080/")["valid"] is False


def test_validate_url_dotlocal_rejected():
    assert validate_url("http://myhost.local/")["valid"] is False


def test_validate_url_ipv6_loopback_rejected():
    assert validate_url("http://[::1]:8080/")["valid"] is False


def test_validate_url_ipv6_unique_local_rejected():
    assert validate_url("http://[fc00::1]/")["valid"] is False
    assert validate_url("http://[fd00::1]/")["valid"] is False


def test_validate_url_ipv6_link_local_rejected():
    assert validate_url("http://[fe80::1]/")["valid"] is False


def test_validate_url_ipv6_public_passes():
    r = validate_url("http://[2001:4860:4860::8888]/")
    assert r["valid"] is True


# ===== validate_proxy_url =====

def test_proxy_empty_is_valid():
    assert validate_proxy_url("")["valid"] is True
    assert validate_proxy_url(None)["valid"] is True
    assert validate_proxy_url("   ")["valid"] is True


def test_proxy_public_http():
    assert validate_proxy_url("http://1.2.3.4:8080")["valid"] is True


def test_proxy_public_https():
    assert validate_proxy_url("https://proxy.example.com:443")["valid"] is True


def test_proxy_public_domain():
    assert validate_proxy_url("http://proxy.example.com:3128")["valid"] is True


def test_proxy_loopback_ipv4_default_allowed():
    """默认 allow_internal=True，内网代理地址应通过"""
    r = validate_proxy_url("http://127.0.0.1:8888")
    assert r["valid"] is True


def test_proxy_loopback_ipv4_explicit_rejected():
    """显式 allow_internal=False 时，内网地址应拒绝"""
    r = validate_proxy_url("http://127.0.0.1:8888", allow_internal=False)
    assert r["valid"] is False
    assert "内网" in r["error"]


def test_proxy_private_default_allowed():
    """默认允许内网代理：10.x, 172.16-31.x, 192.168.x"""
    assert validate_proxy_url("http://10.0.0.1:8080")["valid"] is True
    assert validate_proxy_url("http://172.16.0.1:8080")["valid"] is True
    assert validate_proxy_url("http://192.168.1.1:8080")["valid"] is True


def test_proxy_private_explicit_rejected():
    """显式 allow_internal=False 时，私网地址应拒绝"""
    assert validate_proxy_url("http://10.0.0.1:8080", allow_internal=False)["valid"] is False
    assert validate_proxy_url("http://172.16.0.1:8080", allow_internal=False)["valid"] is False
    assert validate_proxy_url("http://172.31.255.255:8080", allow_internal=False)["valid"] is False
    # 172.32 不是私网，应通过
    assert validate_proxy_url("http://172.32.0.1:8080", allow_internal=False)["valid"] is True
    assert validate_proxy_url("http://192.168.1.1:8080", allow_internal=False)["valid"] is False


def test_proxy_link_local_default_allowed():
    assert validate_proxy_url("http://169.254.169.254")["valid"] is True


def test_proxy_localhost_default_allowed():
    assert validate_proxy_url("http://localhost:8080")["valid"] is True


def test_proxy_ipv6_loopback_default_allowed():
    assert validate_proxy_url("http://[::1]:8080")["valid"] is True


def test_proxy_ipv6_unique_local_default_allowed():
    assert validate_proxy_url("http://[fc00::1]:8080")["valid"] is True
    assert validate_proxy_url("http://[fd00::1]:8080")["valid"] is True


def test_proxy_ipv6_link_local_default_allowed():
    assert validate_proxy_url("http://[fe80::1]:8080")["valid"] is True


def test_proxy_socks5_loopback_default_allowed():
    """SOCKS5 代理默认允许内网地址"""
    assert validate_proxy_url("socks5://127.0.0.1:1080")["valid"] is True
    assert validate_proxy_url("socks5://user:pass@127.0.0.1:1080")["valid"] is True


def test_proxy_socks5_loopback_explicit_rejected():
    assert validate_proxy_url("socks5://127.0.0.1:1080", allow_internal=False)["valid"] is False
    assert validate_proxy_url("socks5://user:pass@127.0.0.1:1080", allow_internal=False)["valid"] is False


def test_proxy_ipv6_public():
    assert validate_proxy_url("http://[2001:4860:4860::8888]:8080")["valid"] is True


def test_proxy_socks5_with_userinfo():
    assert validate_proxy_url("socks5://user:pass@proxy.example.com:1080")["valid"] is True


def test_proxy_socks5h_public():
    assert validate_proxy_url("socks5h://proxy.example.com:1080")["valid"] is True


def test_proxy_invalid_scheme():
    r = validate_proxy_url("ftp://x.com")
    assert r["valid"] is False
    assert "协议" in r["error"]


def test_proxy_no_host():
    assert validate_proxy_url("http://")["valid"] is False


# ===== validate_wecom_proxy_base =====

def test_wecom_empty_is_valid():
    assert validate_wecom_proxy_base("")["valid"] is True
    assert validate_wecom_proxy_base(None)["valid"] is True


def test_wecom_default_passes():
    assert validate_wecom_proxy_base(WECOM_DEFAULT_BASE)["valid"] is True
    assert validate_wecom_proxy_base("https://qyapi.weixin.qq.com")["valid"] is True


def test_wecom_https_public_passes():
    assert validate_wecom_proxy_base("https://wecom.example.com")["valid"] is True


def test_wecom_http_rejected():
    r = validate_wecom_proxy_base("http://qyapi.weixin.qq.com")
    assert r["valid"] is False
    assert "https" in r["error"].lower()


def test_wecom_internal_https_rejected():
    assert validate_wecom_proxy_base("https://127.0.0.1")["valid"] is False
    assert validate_wecom_proxy_base("https://10.0.0.1")["valid"] is False
    assert validate_wecom_proxy_base("https://localhost")["valid"] is False


def test_wecom_ipv6_loopback_rejected():
    assert validate_wecom_proxy_base("https://[::1]")["valid"] is False
