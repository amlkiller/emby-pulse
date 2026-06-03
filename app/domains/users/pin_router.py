import datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.rate_limiter import get_client_ip
from app.core.security_utils import safe_error_message
from app.domains.users import user_dao


router = APIRouter()


def _noop_audit_log(**_kwargs):
    return None


_user_dao_provider = lambda: user_dao
_safe_error_message_provider = lambda: safe_error_message
_client_ip_provider = lambda: get_client_ip
_audit_log_provider = lambda: _noop_audit_log
_now_provider = lambda: datetime.datetime.now().isoformat()


class PinUserModel(BaseModel):
    user_id: str
    pinned: bool


def set_dependency_providers(
    *,
    user_dao_provider=None,
    safe_error_message_provider=None,
    client_ip_provider=None,
    audit_log_provider=None,
    now_provider=None,
):
    global _user_dao_provider
    global _safe_error_message_provider
    global _client_ip_provider
    global _audit_log_provider
    global _now_provider

    if user_dao_provider is not None:
        _user_dao_provider = user_dao_provider
    if safe_error_message_provider is not None:
        _safe_error_message_provider = safe_error_message_provider
    if client_ip_provider is not None:
        _client_ip_provider = client_ip_provider
    if audit_log_provider is not None:
        _audit_log_provider = audit_log_provider
    if now_provider is not None:
        _now_provider = now_provider


@router.post("/api/manage/user/pin")
def api_pin_user(data: PinUserModel, request: Request):
    """置顶/取消置顶用户"""
    if not request.session.get("user"):
        return {"status": "error", "message": "未登录"}

    user = request.session.get("user", {})
    if user.get("auth_type") != "emby" and user.get("role") != "admin":
        return {"status": "error", "message": "需要管理员权限"}

    try:
        _user_dao_provider().set_user_pinned(data.user_id, data.pinned, _now_provider())

        action = "置顶用户" if data.pinned else "取消置顶"
        _audit_log_provider()(
            admin_id=user.get("id", ""),
            admin_name=user.get("name", "管理员"),
            action=action,
            target_user_id=data.user_id,
            ip_address=_client_ip_provider()(request),
        )

        return {"status": "success", "message": f"已{'置顶' if data.pinned else '取消置顶'}用户"}
    except Exception as e:
        return {"status": "error", "message": _safe_error_message_provider()(e)}
