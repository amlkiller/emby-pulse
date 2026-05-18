import re

from fastapi import Request, HTTPException


def validate_password_strength(password: str) -> tuple:
    """统一密码强度校验，返回 (is_valid, error_message)。

    所有注册渠道（管理端、邀请链接、社区注册、机器人）均应通过此函数校验，
    以保证策略一致：≥ 8 字符、含小写、含大写或数字。
    """
    if not isinstance(password, str):
        return False, "密码格式不正确"
    if len(password) < 8:
        return False, "密码至少需要 8 个字符"
    if len(password) > 128:
        return False, "密码不能超过 128 个字符"
    if not re.search(r'[a-z]', password):
        return False, "密码需要包含小写字母"
    if not re.search(r'[A-Z0-9]', password):
        return False, "密码需要包含大写字母或数字"
    return True, ""


def require_login(request: Request) -> dict:
    """统一登录依赖：未登录返回 401"""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return user


def require_any_login(request: Request) -> dict:
    """放宽版登录依赖：管理端 session["user"] 或用户端 session["req_user"] 任一登录即可。

    用于双端共享的端点（如图片代理）。返回当前活动的会话用户对象。
    """
    user = request.session.get("user") or request.session.get("req_user")
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return user


def require_admin(request: Request) -> dict:
    """统一管理员依赖：未登录 401，非管理员 403

    管理员判定：auth_type == 'emby'（Emby 管理员）或 role == 'admin'
    """
    user = require_login(request)
    if user.get("auth_type") != "emby" and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def is_admin_session(user: dict) -> bool:
    """判定一个 session.user 对象是否具备管理员身份（不抛异常版本）。

    抽取自 ``require_admin`` 的判定逻辑，便于在需要"返回兼容响应 shape"
    的存量端点中复用（例如 ``return {"status": "error", "message": "..."}``）。
    """
    if not user:
        return False
    return user.get("auth_type") == "emby" or user.get("role") == "admin"


def require_self_or_admin(target_user_id_param: str = "user_id"):
    """工厂函数：返回一个依赖，校验当前会话用户为指定 user_id 本人或管理员。

    用法::

        @router.get("/api/devices/{user_id}")
        def list_devices(
            user_id: int,
            _: dict = Depends(require_self_or_admin("user_id")),
        ): ...

    路径参数从 ``request.path_params`` 取，避免与端点签名耦合。
    """

    def _dep(request: Request) -> dict:
        user = require_login(request)
        if is_admin_session(user):
            return user
        target = request.path_params.get(target_user_id_param)
        # session 中可能是 int 或 str，统一字符串化对比
        current_id = user.get("Id") or user.get("id") or user.get("user_id")
        if target is None or str(target) != str(current_id):
            raise HTTPException(status_code=403, detail="只能访问自己的资源")
        return user

    return _dep