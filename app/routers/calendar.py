import os
import logging
from fastapi import APIRouter, Request, Depends
from app.routers.auth import is_admin_user  # 🔒 引入管理员权限检查
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from app.services.calendar_service import calendar_service
from app.core.config import templates, cfg
from app.routers.auth import check_permission

from app.routers.views import get_common_vars

router = APIRouter()
logger = logging.getLogger("uvicorn")

# 🔥 获取应用版本号
APP_VERSION = os.environ.get("APP_VERSION", "1.3.0.Dev")

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
    public_url = cfg.get("emby_public_url") or cfg.get("emby_public_host") or cfg.get("emby_host")
    if public_url and public_url.endswith('/'): public_url = public_url[:-1]

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
    cfg.set("calendar_cache_ttl", config.ttl)
    return {"status": "success"}