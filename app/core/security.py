import sqlite3
from fastapi import HTTPException
from app.core.config import SYSTEM_DB_PATH

def verify_pro_status():
    """Pro 权限依赖拦截器"""
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        row = conn.execute("SELECT status FROM sys_license LIMIT 1").fetchone()
        conn.close()
        
        if row and row[0] == 'pro':
            return True
            
    except Exception as e:
        pass

    # 如果没查到 pro，直接抛出 402 Payment Required 异常，拦截请求
    raise HTTPException(
        status_code=402, 
        detail="👑 此高级功能为 EmbyPulse Pro 专属，请先激活解锁。"
    )