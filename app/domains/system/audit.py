"""
审计日志 API
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from app.core.audit_logger import get_audit_logs, get_audit_stats, AUDIT_ACTIONS
from app.infra.db.audit_dao import list_user_audit_logs_since
from app.domains.users import public_service as user_service
from app.shared.version import APP_VERSION
import time
import os

router = APIRouter(prefix="/api/audit", tags=["审计日志"])
templates = Jinja2Templates(directory="templates")


@router.get("/page", response_class=HTMLResponse)
async def audit_page(request: Request):
    """审计日志页面"""
    # 检查登录
    user = request.session.get("user")
    if not user:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/login")
    # 🔒 仅管理员可访问审计页面
    if not user_service.is_admin_user(request):
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/login")

    return templates.TemplateResponse(
        "audit.html",
        {"request": request, "version": APP_VERSION}
    )


@router.get("/logs")
async def api_get_audit_logs(
    request: Request,
    user_id: str = None,
    action: str = None,
    days: int = 7,
    limit: int = 100,
    offset: int = 0
):
    """
    查询审计日志（合并两个表）
    """
    # 🔒 安全检查：必须管理员
    if not user_service.is_admin_user(request):
        return JSONResponse(status_code=403, content={"error": "需要管理员权限"})
    
    import json
    
    # 计算时间范围
    end_time = time.time()
    start_time = end_time - days * 86400
    
    all_logs = []
    
    # 1. 从 audit_logs 表获取数据
    logs = get_audit_logs(
        user_id=user_id,
        action=action,
        start_time=start_time,
        end_time=end_time,
        limit=min(limit, 500),
        offset=offset
    )
    
    for log in logs:
        if log.get("details"):
            try:
                log["details"] = json.loads(log["details"])
            except:
                pass
        log["source"] = "system"
        all_logs.append(log)
    
    # 2. 从 user_audit_logs 表获取数据
    try:
        start_datetime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))
        rows = list_user_audit_logs_since(start_datetime, limit)
        
        # 用户操作类型映射
        user_action_map = {
            "删除用户": "user_delete",
            "批量删除": "user_delete",
            "启用用户": "user_update",
            "禁用用户": "user_update",
            "应用模板": "user_update",
            "续费用户": "user_update",
            "设置线路": "user_update",
            "更新用户": "user_update",
            "置顶用户": "user_update",
            "取消置顶": "user_update",
            "更新头像": "user_update",
            "更新媒体库权限": "user_update",
            "更新请求权限": "user_update",
            "创建标签": "tag_create",
            "删除标签": "tag_delete",
            "生成邀请码": "invitation_create",
            "生成注册码": "invitation_create",
        }
        
        for row in rows:
            row_dict = dict(row)
            action_type = user_action_map.get(row_dict.get("action", ""), "user_action")
            
            all_logs.append({
                "id": f"u{row_dict['id']}",
                "timestamp": time.mktime(time.strptime(row_dict["created_at"], "%Y-%m-%dT%H:%M:%S.%f")) if "." in row_dict["created_at"] else time.mktime(time.strptime(row_dict["created_at"], "%Y-%m-%dT%H:%M:%S")),
                "datetime": row_dict["created_at"].replace("T", " ")[:19],
                "user_id": row_dict.get("admin_id", ""),
                "user_name": row_dict.get("admin_name", ""),
                "action": action_type,
                "resource_type": "user",
                "resource_id": row_dict.get("target_user_id", ""),
                "ip_address": row_dict.get("ip_address", ""),
                "details": {
                    "target_user_name": row_dict.get("target_user_name", ""),
                    "target_count": row_dict.get("target_count", 0),
                    "details": row_dict.get("details", ""),
                    "original_action": row_dict.get("action", ""),
                },
                "status": "success",
                "source": "user_management"
            })
    except Exception as e:
        import logging
        logging.error(f"[审计日志] 查询 user_audit_logs 失败: {e}")
    
    # 按时间排序
    all_logs.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    
    # 限制数量
    all_logs = all_logs[:limit]
    
    return {
        "status": "success",
        "data": all_logs,
        "total": len(all_logs)
    }


@router.get("/stats")
async def api_get_audit_stats(request: Request, days: int = 7):
    """
    获取审计日志统计
    """
    # 🔒 安全检查：必须管理员
    if not user_service.is_admin_user(request):
        return JSONResponse(status_code=403, content={"error": "需要管理员权限"})
    
    stats = get_audit_stats(days=days)
    
    return {
        "status": "success",
        "data": stats
    }


@router.get("/actions")
async def api_get_audit_actions(request: Request):
    """
    获取所有审计操作类型
    """
    # 🔒 安全检查：必须管理员
    if not user_service.is_admin_user(request):
        return JSONResponse(status_code=403, content={"error": "需要管理员权限"})
    
    return {
        "status": "success",
        "data": AUDIT_ACTIONS
    }
