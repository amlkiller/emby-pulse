import sqlite3
import logging
from fastapi import APIRouter, Request
from pydantic import BaseModel
from app.core.config import cfg
from app.core.database import add_sys_notification, SYSTEM_DB_PATH
from app.core.license import get_machine_id
from app.routers.auth import is_admin_user

logger = logging.getLogger("uvicorn")
router = APIRouter()


def ensure_pro_schema():
    """初始化授权数据库表（使用系统数据库）"""
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS sys_license (
                        license_key TEXT,
                        machine_id TEXT,
                        pro_token TEXT,
                        status TEXT DEFAULT 'pro',
                        expire_date DATETIME,
                        last_checked DATETIME DEFAULT CURRENT_TIMESTAMP
                    )''')
        for col in ["pro_token TEXT", "expire_date DATETIME",
                     "last_checked DATETIME DEFAULT CURRENT_TIMESTAMP",
                     "max_devices INTEGER", "current_devices INTEGER"]:
            try:
                c.execute(f"ALTER TABLE sys_license ADD COLUMN {col}")
            except Exception:
                pass
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"授权表初始化失败: {e}")


ensure_pro_schema()


class ActivateModel(BaseModel):
    license_key: str


@router.post("/api/pro/activate")
async def activate_pro(data: ActivateModel, request: Request):
    """激活 Pro（本地直通）"""
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    key = data.license_key.strip()
    mid = get_machine_id()

    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM sys_license")
        c.execute(
            "INSERT INTO sys_license (license_key, machine_id, status) VALUES (?, ?, ?)",
            (key, mid, "pro"),
        )
        conn.commit()
        conn.close()
        add_sys_notification("system", "👑 Pro 激活成功", "全站高级功能已解锁！")
        return {"status": "success", "message": "激活成功"}
    except Exception as e:
        return {"status": "error", "message": f"激活失败: {e}"}


@router.get("/api/pro/status")
async def get_pro_status(request: Request):
    """获取 Pro 状态"""
    if not is_admin_user(request):
        return {"status": "error", "message": "权限不足"}

    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        row = conn.execute("SELECT license_key, machine_id, status FROM sys_license LIMIT 1").fetchone()
        conn.close()

        if row:
            return {
                "status": "success",
                "data": {
                    "license": {
                        "license_key": (row[0][:8] + "****") if row[0] else None,
                        "machine_id": row[1],
                        "status": row[2],
                    },
                    "device": {"max_devices": 10, "current_devices": 0},
                },
            }
    except Exception:
        pass

    return {
        "status": "success",
        "data": {
            "license": {"status": "pro"},
            "device": {"max_devices": 10, "current_devices": 0},
        },
    }
