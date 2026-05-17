from fastapi import Request, HTTPException


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