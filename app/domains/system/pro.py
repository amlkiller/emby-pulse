import logging
from fastapi import APIRouter, Request
from pydantic import BaseModel
from app.dao.notification_dao import add_system_notification
from app.dao.pro_license_dao import (
    ensure_pro_schema as ensure_pro_schema_data,
    get_license_status,
    replace_license,
)
from app.core.license import get_machine_id
from app.routers.auth import is_admin_user

logger = logging.getLogger("uvicorn")
router = APIRouter()


def ensure_pro_schema():
    """初始化授权数据库表（使用系统数据库）"""
    try:
        ensure_pro_schema_data()
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
        replace_license(key, mid)
        try:
            add_system_notification("system", "👑 Pro 激活成功", "全站高级功能已解锁！")
        except Exception as notify_error:
            logger.error(f"[系统通知] 写入数据库失败: {notify_error}")
        return {"status": "success", "message": "激活成功"}
    except Exception as e:
        return {"status": "error", "message": f"激活失败: {e}"}


@router.get("/api/pro/status")
async def get_pro_status(request: Request):
    """获取 Pro 状态"""
    if not is_admin_user(request):
        return {"status": "error", "message": "权限不足"}

    try:
        row = get_license_status()

        if row:
            return {
                "status": "success",
                "data": {
                    "license": {
                        "license_key": (row["license_key"][:8] + "****") if row["license_key"] else None,
                        "machine_id": row["machine_id"],
                        "status": row["status"],
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
