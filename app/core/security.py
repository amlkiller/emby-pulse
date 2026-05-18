import re

from fastapi import Request, HTTPException


def validate_password_strength(password: str) -> tuple:
    """统一密码强度校验，返回 (is_valid, error_message)。

    所有注册渠道（管理端、邀请链接、社区注册、机器人）均应通过此函数校验，
    以保证策略一致：≥ 8 字符、含小写、含大写或数字。
    """
    if not isinstance(password, str):
        return False, "密码格式不正确"
    if len(password) < 8:
        return False, "密码至少需要 8 个字符"
    if len(password) > 128:
        return False, "密码不能超过 128 个字符"
    if not re.search(r'[a-z]', password):
        return False, "密码需要包含小写字母"
    if not re.search(r'[A-Z0-9]', password):
        return False, "密码需要包含大写字母或数字"
    return True, ""


def require_login(request: Request) -> dict:
    """统一登录依赖：未登录返回 401"""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return user


def require_admin(request: Request) -> dict:
    """统一管理员依赖：未登录 401，非管理员 403

    管理员判定：auth_type == 'emby'（Emby 管理员）或 role == 'admin'
    """
    user = require_login(request)
    if user.get("auth_type") != "emby" and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user