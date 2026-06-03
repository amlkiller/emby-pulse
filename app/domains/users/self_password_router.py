from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.security import validate_password_strength
from app.core.security_utils import safe_error_message
from app.infra.clients.media_server_client import media_api


router = APIRouter()

_media_api_provider = lambda: media_api
_validate_password_strength_provider = lambda: validate_password_strength
_safe_error_message_provider = lambda: safe_error_message


class UserPasswordChangeModel(BaseModel):
    old_password: str
    new_password: str


def set_dependency_providers(
    *,
    media_api_provider=None,
    validate_password_strength_provider=None,
    safe_error_message_provider=None,
):
    global _media_api_provider
    global _validate_password_strength_provider
    global _safe_error_message_provider

    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if validate_password_strength_provider is not None:
        _validate_password_strength_provider = validate_password_strength_provider
    if safe_error_message_provider is not None:
        _safe_error_message_provider = safe_error_message_provider


@router.post("/api/user/password")
def api_user_self_password(data: UserPasswordChangeModel, request: Request):
    """C 端用户自助修改密码(先验证旧密码)"""
    user = request.session.get("req_user")
    if not user or not user.get("Id"):
        return {"status": "error", "message": "请先登录"}
    user_id = user["Id"]
    user_name = user.get("Name", "")
    if not data.new_password:
        return {"status": "error", "message": "新密码不能为空"}
    pw_valid, pw_error = _validate_password_strength_provider()(data.new_password)
    if not pw_valid:
        return {"status": "error", "message": pw_error}
    try:
        auth_res = _media_api_provider().authenticate_by_name(user_name, data.old_password, timeout=8)
        if auth_res.status_code != 200:
            return {"status": "error", "message": "旧密码不正确"}
        _media_api_provider().post(
            f"/Users/{user_id}/Password",
            json={"Id": user_id, "CurrentPw": data.old_password, "NewPw": data.new_password},
        )
        return {"status": "success", "message": "密码已修改"}
    except Exception as e:
        return {"status": "error", "message": _safe_error_message_provider()(e, "修改失败")}
