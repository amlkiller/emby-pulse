from fastapi import APIRouter, Request

from app.core.security_utils import safe_error_message
from app.domains.users.auth import is_admin_user
from app.infra.config.user_bot_settings import (
    get_default_user_template_id,
    set_default_user_template_id,
)


router = APIRouter()


@router.post("/api/manage/template/default")
def api_set_default_template(data: dict, request: Request):
    """设置默认用户权限模板"""
    if not request.session.get("user"): return {"status": "error", "message": "未登录"}

    # 检查管理员权限
    user = request.session.get("user", {})
    if user.get("auth_type") != "emby" and user.get("role") != "admin":
        return {"status": "error", "message": "需要管理员权限"}

    try:
        template_id = data.get("template_user_id", "")
        set_default_user_template_id(template_id)
        return {"status": "success", "message": "默认模板已更新"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


@router.get("/api/manage/template/default")
def api_get_default_template(request: Request):
    """获取当前默认用户权限模板"""
    if not request.session.get("user"): return {"status": "error", "message": "未登录"}
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    try:
        template_id = get_default_user_template_id()
        return {"status": "success", "data": {"template_user_id": template_id}}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}
