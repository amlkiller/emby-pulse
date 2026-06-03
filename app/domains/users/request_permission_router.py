import datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.security_utils import safe_error_message
from app.domains.users import user_dao
from app.domains.users.auth import is_admin_user


router = APIRouter()


class UserReqPermissionModel(BaseModel):
    user_id: str
    req_free: int = 0  # 0=跟随全局, 1=免费, 2=付费
    req_free_count: int = -1  # -1=无限次, >=0=剩余次数


@router.post("/api/manage/user/req_permission")
def api_update_user_req_permission(data: UserReqPermissionModel, request: Request):
    """更新用户求片权限"""
    if not request.session.get("user"):
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}

    try:
        user_dao.save_user_req_permission(
            data.user_id,
            data.req_free,
            data.req_free_count,
            datetime.datetime.now().isoformat(),
        )
        return {"status": "success", "message": "求片权限已更新"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


@router.get("/api/manage/user/req_permission")
def api_get_user_req_permission(user_id: str, request: Request):
    """获取用户求片权限"""
    if not request.session.get("user"):
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}

    try:
        return {"status": "success", "data": user_dao.get_user_req_permission(user_id)}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}
