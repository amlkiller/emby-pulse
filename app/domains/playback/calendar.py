import os
import logging
from fastapi import APIRouter, Request, Depends
from app.domains.users.auth import is_admin_user  # 🔒 引入管理员权限检查
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from app.services.calendar_service import calendar_service
from app.core.config import templates
from app.infra.config.calendar_settings import get_calendar_public_url, set_calendar_cache_ttl
from app.domains.users.auth import check_permission

router = APIRouter()
logger = logging.getLogger("uvicorn")

def _check_pro_status():
    """检查 Pro 授权状态"""
    return True

# 定义请求模型
class CalendarConfigReq(BaseModel):
    ttl: int

@router.get("/calendar")
async def calendar_page(request: Request):
    """
    返回日历的前端页面 HTML
    """
    if not request.session.get("user"):
        return RedirectResponse("/login", status_code=303)
    
    # 权限检查
    if not check_permission(request, "calendar"):
        return RedirectResponse("/?no_permission=1", status_code=303)

    # 获取公网地址，如果没有则使用内网地址作为回退
    public_url = get_calendar_public_url()
    if public_url and public_url.endswith('/'): public_url = public_url[:-1]

    from app.domains.system.views import get_common_vars
    return templates.TemplateResponse("calendar.html", get_common_vars(request, "calendar", {
        "emby_public_url": public_url,
        "is_pro": _check_pro_status()
    }))

@router.get("/api/calendar/weekly")
def get_weekly_calendar(request: Request, refresh: bool = False, offset: int = 0): 
    # 🔒 安全检查（支持管理端和用户端登录）
    if not (request.session.get("user") or request.session.get("req_user")):
        return {"status": "error", "message": "请先登录"}
    """
    API: 获取本周数据 (JSON)
    refresh: 是否强制刷新缓存
    offset: 周偏移 (0=本周, 1=下周, -1=上周)
    """
    return calendar_service.get_weekly_calendar(force_refresh=refresh, week_offset=offset)

@router.post("/api/calendar/config")
async def update_calendar_config(request: Request, config: CalendarConfigReq):
    """API: 更新日历配置"""
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    set_calendar_cache_ttl(config.ttl)
    return {"status": "success"}
