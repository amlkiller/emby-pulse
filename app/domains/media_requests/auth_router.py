import json
from datetime import date

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.domains.media_requests.media_request_dao import (
    get_user_expire_date,
    get_user_password_hash,
    get_user_status_meta,
    update_user_password_hash,
)
from app.infra.clients.media_server_client import media_api
from app.infra.config.media_server_settings import (
    get_media_server_main_public_or_host,
    get_media_server_user_routes,
)


router = APIRouter()

_media_api_provider = lambda: media_api
_main_server_url_provider = lambda: get_media_server_main_public_or_host
_user_routes_provider = lambda: get_media_server_user_routes
_user_status_meta_provider = lambda: get_user_status_meta
_user_password_hash_provider = lambda: get_user_password_hash
_update_user_password_hash_provider = lambda: update_user_password_hash
_user_expire_date_provider = lambda: get_user_expire_date
def _check_user_exists(user_id: str) -> bool:
    if not user_id:
        return False
    try:
        media = _media_api_provider()
        if media and media.host and media.api_key:
            res = media.get(f"/Users/{user_id}", timeout=5)
            return res.status_code == 200
    except:
        pass
    return True


_check_user_exists_provider = lambda: _check_user_exists


class RequestLoginModel(BaseModel):
    username: str
    password: str


def set_dependency_providers(
    *,
    media_api_provider=None,
    main_server_url_provider=None,
    user_routes_provider=None,
    user_status_meta_provider=None,
    user_password_hash_provider=None,
    update_user_password_hash_provider=None,
    user_expire_date_provider=None,
    check_user_exists_provider=None,
):
    global _media_api_provider
    global _main_server_url_provider
    global _user_routes_provider
    global _user_status_meta_provider
    global _user_password_hash_provider
    global _update_user_password_hash_provider
    global _user_expire_date_provider
    global _check_user_exists_provider

    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if main_server_url_provider is not None:
        _main_server_url_provider = main_server_url_provider
    if user_routes_provider is not None:
        _user_routes_provider = user_routes_provider
    if user_status_meta_provider is not None:
        _user_status_meta_provider = user_status_meta_provider
    if user_password_hash_provider is not None:
        _user_password_hash_provider = user_password_hash_provider
    if update_user_password_hash_provider is not None:
        _update_user_password_hash_provider = update_user_password_hash_provider
    if user_expire_date_provider is not None:
        _user_expire_date_provider = user_expire_date_provider
    if check_user_exists_provider is not None:
        _check_user_exists_provider = check_user_exists_provider


@router.post("/api/requests/auth")
def request_system_login(data: RequestLoginModel, request: Request):
    media = _media_api_provider()
    get_main_server_url = _main_server_url_provider()
    get_status_meta = _user_status_meta_provider()
    get_password_hash = _user_password_hash_provider()
    update_password_hash = _update_user_password_hash_provider()

    # 🔒 端口隔离检查：用户社区登录只能从用户端口访问
    host_header = request.headers.get("host", "")
    is_admin_port = ":10307" in host_header or host_header.endswith(":10307")

    # 如果从管理端口访问，拒绝用户社区登录
    if is_admin_port:
        return {"status": "error", "message": "请从用户社区端口(10308)登录"}

    host = get_main_server_url()
    if not host:
        return {"status": "error", "message": "未配置 Emby 服务器"}

    # 先获取用户列表，找到匹配的用户
    matched_user = None
    try:
        users_res = media.get("/Users", timeout=5)
        if users_res.status_code == 200:
            for u in users_res.json():
                if u.get("Name", "").lower() == data.username.lower():
                    matched_user = u
                    break
    except Exception as e:
        print(f"[用户社区登录] 获取用户列表失败: {e}")

    if not matched_user:
        return {"status": "error", "message": "账号或密码错误"}

    user_id = matched_user.get("Id")
    user_name = matched_user.get("Name")
    has_password = matched_user.get("HasPassword", False)
    is_emby_disabled = matched_user.get("Policy", {}).get("IsDisabled", False)

    # 检查数据库中的状态
    admin_disabled = 0
    expire_date = None
    try:
        row = get_status_meta(user_id)
        if row:
            admin_disabled, expire_date = row["admin_disabled"], row["expire_date"]
    except Exception as e:
        print(f"[用户社区登录] 检查用户状态失败: {e}")

    # 管理员封禁 - 拒绝登录
    if admin_disabled == 1:
        return {"status": "error", "message": "您的账号已被禁用，如需启用请联系管理员", "disabled": True}

    # 检查是否过期
    is_expired = False
    if expire_date:
        try:
            exp_date = date.fromisoformat(expire_date)
            if exp_date < date.today():
                is_expired = True
        except:
            pass

    # 验证密码
    if not has_password:
        return {"status": "error", "message": "安全要求：请先在 Emby 中为账号设置密码"}

    password_valid = False
    if has_password:
        if is_emby_disabled:
            # 🔒 安全修复：已禁用账号不修改 Emby IsDisabled 状态，使用本地哈希验证
            stored_hash = None
            try:
                row = get_password_hash(user_id)
                if row and row["emby_pw_hash"]:
                    stored_hash = row["emby_pw_hash"]
            except:
                pass

            if stored_hash:
                try:
                    import bcrypt

                    password_valid = bcrypt.checkpw(data.password.encode("utf-8"), stored_hash.encode("utf-8"))
                except:
                    password_valid = False
            else:
                # 无哈希缓存（用户从未成功登录过），安全拒绝
                return {"status": "error", "message": "账号已过期，请联系管理员续费后登录", "disabled": True, "need_renew": True}
        else:
            # 正常账号：通过 Emby API 验证密码
            try:
                res = media.authenticate_by_name(data.username, data.password, timeout=8)
                password_valid = res.status_code == 200
            except Exception as e:
                print(f"[用户社区登录] 验证密码失败: {e}")

    if not password_valid:
        return {"status": "error", "message": "账号或密码错误"}

    # 🔒 登录成功后缓存密码哈希（用于过期账号本地验证，永不修改 Emby IsDisabled）
    if has_password and data.password:
        try:
            import bcrypt

            pw_hash = bcrypt.hashpw(data.password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")
            update_password_hash(user_id, pw_hash)
        except:
            pass

    # 登录成功 - 清除整个 Session，防止残留其他用户数据
    request.session.clear()
    request.session["req_user"] = {"Id": user_id, "Name": user_name, "expired": is_expired}

    if is_expired:
        return {"status": "success", "expired": True, "message": f"您的账号已于 {expire_date} 过期，请及时续费"}
    return {"status": "success"}


@router.get("/api/requests/check")
def check_auth(request: Request):
    get_status_meta = _user_status_meta_provider()
    get_expire_date = _user_expire_date_provider()
    get_user_routes = _user_routes_provider()
    get_main_server_url = _main_server_url_provider()
    check_user_exists = _check_user_exists_provider()

    user = request.session.get("req_user")
    if user:
        user_id = user.get("Id")

        # 检查 Emby 账号是否仍然存在
        if not check_user_exists(user_id):
            request.session.pop("req_user", None)
            return {"status": "error", "message": "账号已被删除", "account_deleted": True}

        # 检查是否被封禁（实时检查，防止被封后仍能使用）
        try:
            row = get_status_meta(user_id)

            if row and row["admin_disabled"] == 1:
                # 被管理员封禁，强制登出
                request.session.pop("req_user", None)
                return {"status": "error", "message": "您的账号已被禁用，如需启用请联系管理员", "disabled": True}
        except:
            pass

        expire_date = "永久有效"
        is_expired = False
        if user_id:
            try:
                row = get_expire_date(user_id)
                if row and row["expire_date"]:
                    expire_date = row["expire_date"]
                    try:
                        exp_date = date.fromisoformat(expire_date)
                        if exp_date < date.today():
                            is_expired = True
                    except:
                        pass
            except Exception:
                pass

        # 返回用户可见的线路（根据权限过滤）
        user_routes = get_user_routes(user.get("Id"))
        server_url = json.dumps(user_routes) if user_routes else get_main_server_url()
        return {
            "status": "success",
            "user": {**user, "expire_date": expire_date, "expired": is_expired},
            "server_url": server_url,
        }
    return {"status": "error"}


@router.post("/api/requests/logout")
def request_system_logout(request: Request):
    # 🔥 完全清除 session，不只是 pop req_user
    request.session.clear()
    return {"status": "success"}
