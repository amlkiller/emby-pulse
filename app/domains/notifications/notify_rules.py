from fastapi import APIRouter, Request
from app.domains.notifications.notify_rule_dao import (
    ensure_bot_notify_mutes_table,
    list_bot_notify_mutes,
    replace_bot_notify_mutes,
)
from app.infra.clients.media_server_client import media_api
from app.domains.users import public_service as user_service
from app.core.security_utils import safe_error_message

router = APIRouter(prefix="/api/notify_rules", tags=["Notification Rules"])

def start_notify_rules_services():
    """确保 bot_notify_mutes 表存在"""
    try:
        ensure_bot_notify_mutes_table()
    except Exception as e:
        print(f"[降噪管理] 创建表失败: {e}")

@router.get("/users")
async def get_emby_users(request: Request):
    # 🔒 安全检查：必须管理员
    if not user_service.is_admin_user(request):
        return {"success": False, "data": [], "error": "需要管理员权限"}
    
    try:
        res = media_api.get("/Users", timeout=5)
        if res.status_code == 200:
            return {"success": True, "data": [{"id": u["Id"], "name": u["Name"]} for u in res.json()]}
    except Exception: pass
    return {"success": False, "data": []}

@router.get("/mutes")
async def get_mutes(request: Request):
    # 🔒 安全检查：必须管理员
    if not user_service.is_admin_user(request):
        return {"success": False, "data": {}, "error": "需要管理员权限"}
    
    try:
        rows = list_bot_notify_mutes()
        mutes = {"playback": [], "login": []}
        if rows:
            for r in rows:
                if r['event_type'] in mutes:
                    mutes[r['event_type']].append(r['user_id'])
        return {"success": True, "data": mutes}
    except Exception as e:
        return {"success": False, "msg": safe_error_message(e)}

@router.post("/mutes")
async def save_mutes(req: Request):
    # 🔒 安全检查：必须管理员
    if not user_service.is_admin_user(req):
        return {"success": False, "msg": "需要管理员权限"}
    
    data = await req.json()
    playback_users = data.get("playback", [])
    login_users = data.get("login", [])

    try:
        replace_bot_notify_mutes(playback_users, login_users)
        return {"success": True, "msg": "降噪规则保存成功！新规即刻生效。"}
    except Exception as e:
        return {"success": False, "msg": safe_error_message(e)}
