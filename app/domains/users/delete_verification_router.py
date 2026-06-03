import datetime
import logging
from typing import List

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.domains.users.auth import is_admin_user
from app.infra.clients.media_server_client import media_api


admin_router = APIRouter()
router = APIRouter()

# 记录容器启动时间(用于验证重启后失效)
APP_START_TIME = datetime.datetime.now().isoformat()
_app_start_time_provider = lambda: APP_START_TIME


class PasswordVerifyModel(BaseModel):
    username: str  # 管理员账号
    password: str  # 管理员密码


def set_app_start_time_provider(provider):
    global _app_start_time_provider
    _app_start_time_provider = provider


def verify_emby_admin_password(username: str, password: str) -> bool:
    """验证指定的 Emby 管理员账号密码"""
    try:
        # 先验证该用户是否是管理员
        users_res = media_api.get("/Users", timeout=10)
        if users_res.status_code != 200:
            return False

        users = users_res.json()
        # 找到指定的用户并验证是否是管理员
        target_user = None
        for u in users:
            if u.get("Name") == username:
                target_user = u
                break

        if not target_user:
            return False  # 用户不存在

        if not target_user.get("Policy", {}).get("IsAdministrator", False):
            return False  # 不是管理员

        # 使用 Emby 认证接口验证密码
        auth_res = media_api.authenticate_by_name(username, password, timeout=10)
        return auth_res.status_code == 200
    except Exception as e:
        logging.error(f"[密码验证] Emby 验证失败: {e}")
        return False


def get_emby_admin_users() -> List[str]:
    """获取所有 Emby 管理员用户名列表"""
    try:
        users_res = media_api.get("/Users", timeout=10)
        if users_res.status_code != 200:
            return []

        users = users_res.json()
        admin_names = [u.get("Name") for u in users if u.get("Policy", {}).get("IsAdministrator", False)]
        return admin_names
    except Exception as e:
        logging.error(f"[密码验证] 获取管理员列表失败: {e}")
        return []


@admin_router.get("/api/manage/user/admin_list")
def api_get_admin_list(request: Request):
    """获取 Emby 管理员账号列表(用于密码验证选择)"""
    if not request.session.get("user"):
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    admin_list = get_emby_admin_users()
    return {"status": "success", "data": admin_list}


@router.post("/api/manage/user/verify_password")
def api_verify_delete_password(data: PasswordVerifyModel, request: Request):
    """验证删除用户密码(需要管理员账号和密码)"""
    if not request.session.get("user"):
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    if not data.username:
        return {"status": "error", "message": "请输入管理员账号"}

    if not data.password:
        return {"status": "error", "message": "请输入密码"}

    # 验证 Emby 管理员账号和密码
    if verify_emby_admin_password(data.username, data.password):
        # 验证成功,在 session 中记录验证状态(用于单次删除)
        request.session["delete_verified"] = True
        request.session["delete_verified_time"] = datetime.datetime.now().isoformat()
        return {"status": "success", "message": "验证成功"}

    return {"status": "error", "message": "账号或密码错误"}


@router.post("/api/manage/user/check_delete_verified")
def api_check_delete_verified(request: Request):
    """检查是否已验证删除密码"""
    if not request.session.get("user"):
        return {"status": "error", "message": "未登录", "verified": False}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限", "verified": False}

    verified = request.session.get("delete_verified", False)
    verified_time = request.session.get("delete_verified_time", "")

    # 验证有效期:30分钟内有效,且必须在容器启动时间之后
    if verified and verified_time:
        try:
            verify_dt = datetime.datetime.fromisoformat(verified_time)
            # 检查是否超过30分钟
            if datetime.datetime.now() - verify_dt > datetime.timedelta(minutes=30):
                verified = False
                request.session["delete_verified"] = False
            # 检查验证时间是否在容器启动之前(重启后失效)
            elif verify_dt < datetime.datetime.fromisoformat(_app_start_time_provider()):
                verified = False
                request.session["delete_verified"] = False
        except:
            verified = False

    return {"status": "success", "verified": verified}
