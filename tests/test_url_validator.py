"""
URL 校验工具单元测试
覆盖 validate_proxy_url 和 validate_wecom_proxy_base 的关键场景。
运行：pytest tests/test_url_validator.py -v
"""
import sys
import os

# 确保能够 import app
_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from app.utils.url_validator import (
    validate_proxy_url,
    validate_wecom_proxy_base,
    WECOM_DEFAULT_BASE,
)


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


def test_proxy_loopback_ipv4_rejected():
    r = validate_proxy_url("http://127.0.0.1:8888")
    assert r["valid"] is False
    assert "内网" in r["error"]


def test_proxy_private_a_rejected():
    assert validate_proxy_url("http://10.0.0.1:8080")["valid"] is False


def test_proxy_private_b_rejected():
    assert validate_proxy_url("http://172.16.0.1:8080")["valid"] is False
    assert validate_proxy_url("http://172.31.255.255:8080")["valid"] is False
    # 172.32 不是私网，应通过
    assert validate_proxy_url("http://172.32.0.1:8080")["valid"] is True


def test_proxy_private_c_rejected():
    assert validate_proxy_url("http://192.168.1.1:8080")["valid"] is False


def test_proxy_link_local_rejected():
    assert validate_proxy_url("http://169.254.169.254")["valid"] is False


def test_proxy_localhost_rejected():
    assert validate_proxy_url("http://localhost:8080")["valid"] is False


def test_proxy_ipv6_loopback_rejected():
    r = validate_proxy_url("http://[::1]:8080")
    assert r["valid"] is False


def test_proxy_ipv6_unique_local_rejected():
    assert validate_proxy_url("http://[fc00::1]:8080")["valid"] is False
    assert validate_proxy_url("http://[fd00::1]:8080")["valid"] is False


def test_proxy_ipv6_link_local_rejected():
    assert validate_proxy_url("http://[fe80::1]:8080")["valid"] is False


def test_proxy_ipv6_public():
    assert validate_proxy_url("http://[2001:4860:4860::8888]:8080")["valid"] is True


def test_proxy_socks5_with_userinfo():
    assert validate_proxy_url("socks5://user:pass@proxy.example.com:1080")["valid"] is True


def test_proxy_socks5h_public():
    assert validate_proxy_url("socks5h://proxy.example.com:1080")["valid"] is True


def test_proxy_socks5_loopback_rejected():
    assert validate_proxy_url("socks5://127.0.0.1:1080")["valid"] is False


def test_proxy_socks5_userinfo_loopback_rejected():
    # userinfo 不应绕过内网校验
    assert validate_proxy_url("socks5://user:pass@127.0.0.1:1080")["valid"] is False


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
