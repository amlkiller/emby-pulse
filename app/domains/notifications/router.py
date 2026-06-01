import logging
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.security_utils import safe_error_message
from app.dao.notification_dao import (
    add_system_notification,
    clear_notifications as clear_notifications_data,
    count_unread_notifications,
    delete_notification,
    ensure_notifications_table,
    list_notifications,
    mark_notifications_read,
)
from app.routers.auth import is_admin_user  # 🔒 引入管理员权限检查

logger = logging.getLogger("uvicorn")

router = APIRouter(prefix="/api/notifications", tags=["系统通知"])


class MarkReadReq(BaseModel):
    id: Optional[int] = None


def _ensure_table():
    try:
        ensure_notifications_table()
    except Exception as e:
        logger.error(f"[通知中心] 自动建表失败: {e}")


_ensure_table()


@router.get("")
@router.get("/")
async def get_notifications(request: Request, limit: int = 10, history: bool = False):
    if not is_admin_user(request):
        return {"success": False, "msg": "需要管理员权限"}

    try:
        unread_count = count_unread_notifications()
        notifications = list_notifications(limit=limit, include_cleared=history)
        return {"success": True, "unread_count": unread_count, "items": notifications}
    except Exception as e:
        print(f"❌ [通知中心] 发生异常: {e}")
        return {"success": False, "msg": safe_error_message(e)}


@router.post("/read")
async def mark_as_read(req: MarkReadReq, request: Request):
    if not is_admin_user(request):
        return {"success": False, "msg": "需要管理员权限"}

    try:
        mark_notifications_read(req.id)
        return {"success": True}
    except Exception as e:
        return {"success": False, "msg": safe_error_message(e)}


@router.delete("/clear")
async def clear_notifications(request: Request):
    if not is_admin_user(request):
        return {"success": False, "msg": "需要管理员权限"}

    try:
        clear_notifications_data()
        return {"success": True}
    except Exception as e:
        return {"success": False, "msg": safe_error_message(e)}


@router.delete("/{nid}")
async def delete_single_notification(nid: int, request: Request):
    if not is_admin_user(request):
        return {"success": False, "msg": "需要管理员权限"}

    try:
        delete_notification(nid)
        return {"success": True}
    except Exception as e:
        return {"success": False, "msg": safe_error_message(e)}


@router.get("/test_push")
async def test_push_notification(request: Request):
    if not is_admin_user(request):
        return {"success": False, "msg": "需要管理员权限"}

    ensure_notifications_table()
    try:
        add_system_notification(
            notify_type="system",
            title="✅ 测试通知成功接入",
            message="如果你看到了这条消息，说明从写入到读取的链路已经完全打通！",
            action_url="/",
        )
        return {"success": True, "msg": "测试通知已注入！"}
    except Exception as e:
        return {"success": False, "msg": safe_error_message(e, "注入失败")}
