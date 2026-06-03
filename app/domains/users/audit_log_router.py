import datetime
import logging

from fastapi import APIRouter, Request

from app.core.security_utils import safe_error_message
from app.domains.users.auth import is_admin_user
from app.infra.db import audit_dao


router = APIRouter()


@router.get("/api/manage/audit_logs")
def api_get_audit_logs(
    request: Request,
    page: int = 1,
    limit: int = 20,
    action: str = None,
    start_date: str = None,
    end_date: str = None,
    target_user_id: str = None,
):
    """获取操作审计日志列表"""
    if not request.session.get("user"):
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    try:
        result = audit_dao.list_user_audit_logs(
            page=page,
            limit=limit,
            action=action,
            start_date=start_date,
            end_date=end_date,
            target_user_id=target_user_id,
        )

        return {
            "status": "success",
            "data": {
                "logs": result["logs"],
                "total_count": result["total_count"],
                "total_pages": result["total_pages"],
                "page": result["page"],
            },
        }
    except Exception as e:
        logging.error(f"[审计日志] 查询失败: {e}")
        return {"status": "error", "message": safe_error_message(e)}


@router.get("/api/manage/audit_logs/stats")
def api_get_audit_stats(request: Request, days: int = 7):
    """获取审计日志统计"""
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    days = max(1, min(days, 365))

    try:
        start_date = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
        stats = audit_dao.get_user_audit_stats(start_date)

        return {
            "status": "success",
            "data": {
                "action_stats": stats["action_stats"],
                "admin_stats": stats["admin_stats"],
                "total_count": stats["total_count"],
                "days": days,
            },
        }
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


@router.delete("/api/manage/audit_logs/{log_id}")
def api_delete_audit_log(log_id: int, request: Request):
    """删除单条审计日志"""
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    try:
        audit_dao.delete_user_audit_log(log_id)
        return {"status": "success", "message": "删除成功"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


@router.post("/api/manage/audit_logs/clear")
def api_clear_audit_logs(request: Request, days: int = 30):
    """清理超过指定天数的审计日志"""
    if not request.session.get("user"):
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    try:
        cutoff_date = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
        deleted_count = audit_dao.clear_user_audit_logs_before(cutoff_date)
        return {"status": "success", "message": f"已清理 {deleted_count} 条日志"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}
