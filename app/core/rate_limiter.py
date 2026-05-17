"""
速率限制中间件 - 防止暴力破解和滥用
只限制敏感接口，不影响正常使用
"""
import os
import time
from collections import defaultdict
from threading import Lock
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

# 可信代理列表（从环境变量读取，逗号分隔）
TRUSTED_PROXIES = set(os.getenv("TRUSTED_PROXIES", "127.0.0.1").split(","))

# Docker 环境自动添加默认网关
def _detect_docker_gateway():
    gateway = os.getenv("DOCKER_GATEWAY", "")
    if gateway:
        TRUSTED_PROXIES.add(gateway)
    for gw in ["172.17.0.1", "172.18.0.1", "172.19.0.1"]:
        TRUSTED_PROXIES.add(gw)

_detect_docker_gateway()

# 速率限制配置
RATE_LIMITS = {
    # 登录接口：每分钟最多 10 次
    "/api/login": {"limit": 10, "window": 60},
    # 登出接口：每分钟最多 20 次
    "/api/logout": {"limit": 20, "window": 60},
    # 密码相关：每分钟最多 5 次
    "/api/auth/local-users": {"limit": 30, "window": 60},
    # Webhook：每秒最多 50 次（Emby 可能高频发送）
    "/api/v1/webhook": {"limit": 50, "window": 1},
    # Telegram Webhook：每秒最多 10 次
    "/api/bot/webhook": {"limit": 10, "window": 1},
    # Token 创建：每分钟最多 5 次
    "/api/tokens/create": {"limit": 5, "window": 60},
    # TOTP 设置：每 5 分钟最多 3 次
    "/api/auth/totp/setup": {"limit": 3, "window": 300},
    # 邀请码生成：每分钟最多 10 次
    "/api/manage/user/invite": {"limit": 10, "window": 60},
    "/api/user/points/checkin": {"limit": 3, "window": 60},
    "/api/user/points/buy": {"limit": 10, "window": 60},
    "/api/user/renew": {"limit": 5, "window": 60},
    "/api/user/points/transfer": {"limit": 5, "window": 60},
    "/api/requests/auth": {"limit": 10, "window": 60},
    "/api/register": {"limit": 5, "window": 300},
}

# 白名单路径（不受速率限制）
WHITELIST = [
    "/api/settings",
    "/api/bot/settings",
    "/api/me",
    "/api/routes",
    "/static",
    "/favicon.ico",
]


class RateLimiter:
    """基于内存的速率限制器"""
    
    def __init__(self):
        self.requests = defaultdict(list)  # IP -> [timestamp1, timestamp2, ...]
        self.lock = Lock()
    
    def is_allowed(self, key: str, path: str) -> tuple:
        """
        检查是否允许请求
        返回: (allowed: bool, retry_after: int)
        """
        # 白名单路径不受限制
        for whitelist_path in WHITELIST:
            if path.startswith(whitelist_path):
                return True, 0
        
        # 查找匹配的速率限制规则
        limit_config = None
        for limit_path, config in RATE_LIMITS.items():
            if path.startswith(limit_path):
                limit_config = config
                break
        
        if not limit_config:
            return True, 0  # 没有配置限制，允许
        
        now = time.time()
        window = limit_config["window"]
        limit = limit_config["limit"]
        
        with self.lock:
            # 清理过期的请求记录
            self.requests[key] = [
                ts for ts in self.requests[key]
                if now - ts < window
            ]
            
            # 检查是否超过限制
            if len(self.requests[key]) >= limit:
                retry_after = int(window - (now - self.requests[key][0]))
                return False, max(1, retry_after)
            
            # 记录本次请求
            self.requests[key].append(now)
            return True, 0
    
    def cleanup(self):
        """清理过期的请求记录"""
        now = time.time()
        with self.lock:
            for key in list(self.requests.keys()):
                # 清理超过 1 小时的记录
                self.requests[key] = [
                    ts for ts in self.requests[key]
                    if now - ts < 3600
                ]
                if not self.requests[key]:
                    del self.requests[key]


# 全局速率限制器
rate_limiter = RateLimiter()


def get_client_ip(request: Request) -> str:
    """获取客户端真实 IP，仅从可信代理的 XFF/X-Real-IP 中提取"""
    client_ip = request.client.host if request.client else "unknown"

    if client_ip in TRUSTED_PROXIES:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

    return client_ip


class RateLimitMiddleware(BaseHTTPMiddleware):
    """速率限制中间件"""

    async def dispatch(self, request: Request, call_next):
        # 获取客户端 IP
        client_ip = get_client_ip(request)
        path = request.url.path

        # 检查速率限制
        allowed, retry_after = rate_limiter.is_allowed(client_ip, path)

        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=f"请求过于频繁，请 {retry_after} 秒后再试",
                headers={"Retry-After": str(retry_after)}
            )

        response = await call_next(request)

        # 添加速率限制头
        response.headers["X-RateLimit-Limit"] = str(RATE_LIMITS.get(path, {}).get("limit", 100))

        return response


# 定期清理过期记录
import threading
import logging

logger = logging.getLogger("uvicorn")

def start_cleanup_timer():
    """启动定期清理定时器"""
    def cleanup():
        rate_limiter.cleanup()
        # 每 5 分钟清理一次
        timer = threading.Timer(300, cleanup)
        timer.daemon = True
        timer.start()
    
    cleanup()
    logger.info("🔒 [速率限制] 已启动，敏感接口受保护")
