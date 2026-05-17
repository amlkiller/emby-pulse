"""
代理配置安全读取工具

封装 cfg.get("proxy_url") / cfg.get("wecom_proxy_url") 的读取，
确保运行时使用的代理地址已通过 SSRF 校验。即使写入侧校验被绕过、
或历史配置已被污染，调用方拿到的也是安全的值（非法时自动降级）。
"""
import logging
from typing import Optional

from app.core.config import cfg
from app.utils.url_validator import (
    validate_proxy_url,
    validate_wecom_proxy_base,
    WECOM_DEFAULT_BASE,
)

logger = logging.getLogger("uvicorn")

# 模块级缓存：(原始字符串 -> 结果)，配置变更时调用 invalidate_cache()
_proxies_cache: dict = {}
_wecom_cache: dict = {}
# 已告警过的非法值，防刷屏
_warned_proxy: set = set()
_warned_wecom: set = set()


def invalidate_cache() -> None:
    """配置变更后调用，清空内部缓存。"""
    _proxies_cache.clear()
    _wecom_cache.clear()


def get_safe_proxies() -> Optional[dict]:
    """
    从 cfg 读取 proxy_url 并校验，返回 requests proxies dict 或 None。

    - 空值 / 非法值：返回 None（请求不走代理）
    - 合法值：返回 {"http": url, "https": url}
    - 首次发现非法值时打 WARNING 日志，相同值不重复打
    """
    raw = cfg.get("proxy_url") or ""
    if not isinstance(raw, str):
        raw = ""
    raw = raw.strip()

    if not raw:
        return None

    if raw in _proxies_cache:
        return _proxies_cache[raw]

    result = validate_proxy_url(raw)
    if not result.get("valid"):
        if raw not in _warned_proxy:
            _warned_proxy.add(raw)
            logger.warning(
                "[ProxyHelper] 配置中的 proxy_url 未通过安全校验，已自动降级为不使用代理: %s",
                result.get("error", "unknown"),
            )
        _proxies_cache[raw] = None
        return None

    proxies = {"http": raw, "https": raw}
    _proxies_cache[raw] = proxies
    return proxies


def get_safe_wecom_base() -> str:
    """
    从 cfg 读取 wecom_proxy_url 并校验，返回经过 rstrip('/') 的基址。

    - 空值 / 非法值：返回默认 https://qyapi.weixin.qq.com
    - 首次发现非法值时打 WARNING 日志，相同值不重复打
    """
    raw = cfg.get("wecom_proxy_url") or ""
    if not isinstance(raw, str):
        raw = ""
    raw = raw.strip()

    if not raw:
        return WECOM_DEFAULT_BASE

    if raw in _wecom_cache:
        return _wecom_cache[raw]

    result = validate_wecom_proxy_base(raw)
    if not result.get("valid"):
        if raw not in _warned_wecom:
            _warned_wecom.add(raw)
            logger.warning(
                "[ProxyHelper] 配置中的 wecom_proxy_url 未通过安全校验，已回退到默认基址: %s",
                result.get("error", "unknown"),
            )
        _wecom_cache[raw] = WECOM_DEFAULT_BASE
        return WECOM_DEFAULT_BASE

    base = raw.rstrip("/")
    _wecom_cache[raw] = base
    return base


def audit_existing_proxy_config() -> None:
    """
    启动自检：检查现有 proxy_url / wecom_proxy_url 是否通过校验，
    若不通过则写 WARNING 日志 + audit_log（不自动清除）。
    """
    try:
        proxy_raw = (cfg.get("proxy_url") or "").strip() if isinstance(cfg.get("proxy_url"), str) else ""
        wecom_raw = (cfg.get("wecom_proxy_url") or "").strip() if isinstance(cfg.get("wecom_proxy_url"), str) else ""

        issues = []

        if proxy_raw:
            r = validate_proxy_url(proxy_raw)
            if not r.get("valid"):
                issues.append(("proxy_url", proxy_raw, r.get("error", "")))

        if wecom_raw:
            r = validate_wecom_proxy_base(wecom_raw)
            if not r.get("valid"):
                issues.append(("wecom_proxy_url", wecom_raw, r.get("error", "")))

        if not issues:
            return

        for key, value, err in issues:
            logger.warning(
                "[ProxyHelper][启动自检] 检测到不安全的代理配置 %s=%s -> %s。运行时将自动降级，请管理员尽快修正。",
                key,
                value,
                err,
            )

        # 写一条 audit_log（best-effort）
        try:
            from app.core.audit_logger import log_audit
            log_audit(
                action="config_unsafe_proxy_detected",
                resource_type="system_settings",
                details={
                    "issues": [{"key": k, "value": v, "error": e} for k, v, e in issues],
                    "note": "运行时已自动降级，未自动清除配置",
                },
                status="warning",
            )
        except Exception as exc:
            logger.debug("[ProxyHelper] 写 audit_log 失败（忽略）: %s", exc)
    except Exception as exc:
        logger.debug("[ProxyHelper] 启动自检异常（忽略）: %s", exc)
