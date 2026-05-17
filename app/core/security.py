import sqlite3
from fastapi import Request, HTTPException
from app.core.config import SYSTEM_DB_PATH


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


def verify_pro_status(request: Request):
    """Pro 权限依赖拦截器（同时检查认证状态）"""
    # 先检查认证
    if not request.session.get("user"):
        raise HTTPException(status_code=401, detail="未登录")

    # 再检查 Pro 状态
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        row = conn.execute("SELECT status FROM sys_license LIMIT 1").fetchone()
        conn.close()

        if row and row[0] == 'pro':
            return True
    except Exception:
        pass

    raise HTTPException(
        status_code=402,
        detail="👑 此高级功能为 EmbyPulse Pro 专属，请先激活解锁。"
    )