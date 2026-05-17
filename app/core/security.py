import sqlite3
from fastapi import Request, HTTPException
from app.core.config import SYSTEM_DB_PATH

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