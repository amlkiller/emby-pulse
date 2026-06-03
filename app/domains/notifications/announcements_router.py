from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional

from app.core.security_utils import sanitize_html, sanitize_rich_html
from app.domains.notifications.message_dao import (
    create_announcement as create_announcement_record,
    delete_announcement_by_id,
    ensure_announcement_tables,
    increment_announcement_view_count,
    list_active_announcements_with_reads,
    list_announcements,
    mark_announcement_read as mark_announcement_read_record,
    update_announcement_fields,
)
from app.domains.users import public_service as user_service


router = APIRouter()


class AnnouncementModel(BaseModel):
    title: str
    content: str
    is_active: bool = True
    priority: int = 0  # 优先级，数字越大越靠前


class AnnouncementUpdateModel(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    is_active: Optional[bool] = None
    priority: Optional[int] = None


@router.get("/api/announcements")
def get_announcements(request: Request, active_only: bool = False):
    """获取公告列表（管理端）"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    if not user_service.is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    ensure_announcement_tables()

    rows = list_announcements(active_only)
    announcements = [dict(row) for row in rows] if rows else []
    return {"status": "success", "data": announcements}


@router.post("/api/announcements")
def create_announcement(data: AnnouncementModel, request: Request):
    """创建公告"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    if not user_service.is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    ensure_announcement_tables()

    admin_id = user.get("Id", "")
    admin_name = user.get("Name", "管理员")

    ann_id = create_announcement_record(
        sanitize_html(data.title),
        sanitize_rich_html(data.content, max_length=50000),
        data.is_active,
        data.priority,
        admin_id,
        admin_name,
    )

    return {"status": "success", "message": "公告创建成功", "id": ann_id}


@router.put("/api/announcements/{ann_id}")
def update_announcement(ann_id: int, data: AnnouncementUpdateModel, request: Request):
    """更新公告"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    if not user_service.is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    ensure_announcement_tables()

    updates = {}
    if data.title is not None:
        updates["title"] = sanitize_html(data.title)
    if data.content is not None:
        updates["content"] = sanitize_rich_html(data.content, max_length=50000)
    if data.is_active is not None:
        updates["is_active"] = 1 if data.is_active else 0
    if data.priority is not None:
        updates["priority"] = data.priority

    if not updates:
        return {"status": "error", "message": "无更新内容"}

    update_announcement_fields(ann_id, updates)

    return {"status": "success", "message": "公告更新成功"}


@router.delete("/api/announcements/{ann_id}")
def delete_announcement(ann_id: int, request: Request):
    """删除公告"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    if not user_service.is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    ensure_announcement_tables()

    delete_announcement_by_id(ann_id)

    return {"status": "success", "message": "公告删除成功"}


@router.post("/api/announcements/{ann_id}/view")
def increment_announcement_view(ann_id: int, request: Request):
    """增加公告浏览次数"""
    user = request.session.get("user") or request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "请先登录"}

    ensure_announcement_tables()

    increment_announcement_view_count(ann_id)

    return {"status": "success"}


@router.get("/api/user/announcements")
def user_get_announcements(request: Request):
    """用户获取启用的公告列表"""
    # 🔒 安全检查（支持管理端和用户端）
    user = request.session.get("user") or request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "请先登录"}

    user_id = user.get("Id", "")
    ensure_announcement_tables()

    announcements = list_active_announcements_with_reads(user_id)

    return {"status": "success", "data": announcements}


@router.post("/api/user/announcements/{ann_id}/read")
def mark_announcement_read(ann_id: int, request: Request):
    """标记公告为已读"""
    user = request.session.get("user") or request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "请先登录"}

    user_id = user.get("Id", "")
    ensure_announcement_tables()

    mark_announcement_read_record(ann_id, user_id)

    return {"status": "success", "message": "已标记为已读"}
