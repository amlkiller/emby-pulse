"""
JWT Token 工具
使用 SECRET_KEY 签名，用于 API 认证
"""
import jwt
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from app.core.config import SECRET_KEY

# Token 配置
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24  # Token 有效期：24 小时


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
    token = jwt.encode(data, SECRET_KEY, algorithm=JWT_ALGORITHM)
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
        payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
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
    验证 API Token
    
    Args:
        token: JWT Token
    
    Returns:
        用户信息或 None
    """
    payload = verify_token(token)
    if payload and payload.get("type") == "api_token":
        return payload
    return None


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
