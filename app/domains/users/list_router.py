from fastapi import APIRouter, Request

from app.infra.clients.media_server_client import media_api
from app.infra.config.user_visibility_settings import get_hidden_users


router = APIRouter()


@router.get("/api/users")
def api_get_users(request: Request):
    """获取用户列表 - 仅限管理员访问"""
    # 🔒 安全检查:必须登录
    if not request.session.get("user"):
        return {"status": "error", "message": "未授权"}

    # 🔒 安全检查:必须是管理员
    user = request.session.get("user", {})
    if user.get("auth_type") != "emby" and user.get("role") != "admin":
        return {"status": "error", "message": "权限不足"}

    try:
        res = media_api.get("/Users", timeout=5)
        if res.status_code == 200:
            hidden = get_hidden_users()
            data = [{"UserId": u['Id'], "UserName": u['Name'], "IsHidden": u['Id'] in hidden} for u in res.json()]
            data.sort(key=lambda x: x['UserName'])
            return {"status": "success", "data": data}
        return {"status": "success", "data": []}
    except: return {"status": "error"}
