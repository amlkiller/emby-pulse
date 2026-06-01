"""
JWT Token 工具
使用 SECRET_KEY 签名，用于 API 认证
"""
import jwt
import os
import secrets as _secrets
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from app.core.config import SECRET_KEY
from app.infra.db.api_token_store import get_api_token_by_hash

logger = logging.getLogger("uvicorn")

# Token 配置
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24  # Token 有效期：24 小时

JWT_SECRET = os.getenv("JWT_SECRET_KEY", "") or SECRET_KEY
if not JWT_SECRET:
    JWT_SECRET = _secrets.token_urlsafe(32)
    logger.warning("JWT_SECRET_KEY 未设置，使用自动生成的密钥（重启后失效）")


def create_token(payload: Dict[str, Any], expires_hours: int = JWT_EXPIRE_HOURS) -> str:
    """
    创建 JWT Token
    
    Args:
        payload: Token 载荷（用户信息等）
        expires_hours: 有效期（小时）
    
    Returns:
        JWT Token 字符串
    """
    # 复制载荷，避免修改原始数据
    data = payload.copy()
    
    # 添加过期时间
    expire = datetime.utcnow() + timedelta(hours=expires_hours)
    data.update({
        "exp": expire,
        "iat": datetime.utcnow()  # 签发时间
    })
    
    # 编码 Token
    token = jwt.encode(data, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """
    验证 JWT Token
    
    Args:
        token: JWT Token 字符串
    
    Returns:
        Token 载荷（验证成功）或 None（验证失败）
    """
    try:
        # 解码 Token
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        # Token 已过期
        return None
    except jwt.InvalidTokenError:
        # Token 无效
        return None


def create_api_token(user_id: str, username: str, is_admin: bool = False) -> str:
    """
    创建 API Token
    
    Args:
        user_id: 用户 ID
        username: 用户名
        is_admin: 是否为管理员
    
    Returns:
        JWT Token
    """
    payload = {
        "user_id": user_id,
        "username": username,
        "is_admin": is_admin,
        "type": "api_token"
    }
    return create_token(payload)


def verify_api_token(token: str) -> Optional[Dict[str, Any]]:
    """
    验证 API Token（JWT 签名 + 数据库存在性校验）

    Args:
        token: JWT Token

    Returns:
        用户信息或 None
    """
    payload = verify_token(token)
    if not payload or payload.get("type") != "api_token":
        return None

    # 查数据库确认 token 未被撤销且未过期
    try:
        import hashlib

        token_hash = hashlib.sha256(token.encode()).hexdigest()
        row = get_api_token_by_hash(token_hash)

        if not row:
            return None  # token 已被删除/撤销

        # 检查数据库记录的过期时间（管理员可能设了比 JWT 更短的有效期）
        if row[0]:
            from datetime import datetime
            expires_at = datetime.fromisoformat(row[0])
            if datetime.utcnow() > expires_at:
                return None  # 已过期
    except Exception:
        # 数据库异常时降级为仅 JWT 校验（保持可用性）
        pass

    return payload


def create_password_reset_token(user_id: str, email: str) -> str:
    """
    创建密码重置 Token（有效期 1 小时）
    
    Args:
        user_id: 用户 ID
        email: 用户邮箱
    
    Returns:
        JWT Token
    """
    payload = {
        "user_id": user_id,
        "email": email,
        "type": "password_reset"
    }
    return create_token(payload, expires_hours=1)


def verify_password_reset_token(token: str) -> Optional[Dict[str, Any]]:
    """
    验证密码重置 Token
    
    Args:
        token: JWT Token
    
    Returns:
        用户信息或 None
    """
    payload = verify_token(token)
    if payload and payload.get("type") == "password_reset":
        return payload
    return None
