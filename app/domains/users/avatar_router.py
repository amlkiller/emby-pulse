import base64

from fastapi import APIRouter, File, Form, Request, Response, UploadFile

from app.core.rate_limiter import get_client_ip
from app.core.security_utils import safe_error_message
from app.domains.users.auth import is_admin_user
from app.infra.clients.media_server_client import media_api
from app.infra.clients.network_client import network_client
from app.utils.image_validator import check_magic_bytes


router = APIRouter()


def _noop_audit_log(**_kwargs):
    return None


_media_api_provider = lambda: media_api
_network_client_provider = lambda: network_client
_is_admin_user_provider = lambda: is_admin_user
_check_magic_bytes_provider = lambda: check_magic_bytes
_safe_error_message_provider = lambda: safe_error_message
_client_ip_provider = lambda: get_client_ip
_audit_log_provider = lambda: _noop_audit_log


def set_dependency_providers(
    *,
    media_api_provider=None,
    network_client_provider=None,
    is_admin_user_provider=None,
    check_magic_bytes_provider=None,
    safe_error_message_provider=None,
    client_ip_provider=None,
    audit_log_provider=None,
):
    global _media_api_provider
    global _network_client_provider
    global _is_admin_user_provider
    global _check_magic_bytes_provider
    global _safe_error_message_provider
    global _client_ip_provider
    global _audit_log_provider

    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if network_client_provider is not None:
        _network_client_provider = network_client_provider
    if is_admin_user_provider is not None:
        _is_admin_user_provider = is_admin_user_provider
    if check_magic_bytes_provider is not None:
        _check_magic_bytes_provider = check_magic_bytes_provider
    if safe_error_message_provider is not None:
        _safe_error_message_provider = safe_error_message_provider
    if client_ip_provider is not None:
        _client_ip_provider = client_ip_provider
    if audit_log_provider is not None:
        _audit_log_provider = audit_log_provider


@router.get("/api/user/image/{user_id}")
def get_user_avatar(user_id: str, request: Request):
    if not request.session.get("user"):
        return Response(status_code=401)
    if not _is_admin_user_provider()(request):
        return Response(status_code=403)
    try:
        res = _media_api_provider().get(
            f"/Users/{user_id}/Images/Primary",
            params={"quality": 90},
            timeout=5,
            stream=True,
        )
        if res.status_code == 200:
            return Response(
                content=res.content,
                media_type="image/jpeg",
                headers={"Cache-Control": "no-cache"},
            )
        return Response(status_code=404)
    except:
        return Response(status_code=404)


@router.post("/api/manage/user/image")
async def api_update_user_image(
    request: Request,
    user_id: str = Form(...),
    url: str = Form(None),
    file: UploadFile = File(None),
):
    if not request.session.get("user"):
        return {"status": "error"}
    if not _is_admin_user_provider()(request):
        return {"status": "error", "message": "需要管理员权限"}
    try:
        media = _media_api_provider()
        admin_user = request.session.get("user", {})
        admin_name = admin_user.get("name", admin_user.get("username", "未知"))
        ip_address = _client_ip_provider()(request)

        target_name = ""
        try:
            u_res = media.get(f"/Users/{user_id}", timeout=5)
            if u_res.status_code == 200:
                target_name = u_res.json().get("Name", "")
        except Exception:
            pass

        img_data = None
        c_type = "image/png"
        if url:
            from app.utils.url_validator import validate_url

            validation = validate_url(url, allow_internal=False)
            if not validation["valid"]:
                return {"status": "error", "message": f"URL 不安全: {validation['error']}"}
            d_res = _network_client_provider().get(url, timeout=10, allow_redirects=False, stream=True)
            if d_res.status_code == 200:
                img_data = d_res.content
                c_type = d_res.headers.get("Content-Type", "image/png")
        elif file:
            img_data = await file.read()
            c_type = file.content_type or "image/jpeg"
        if not img_data:
            return {"status": "error", "message": "无图片数据"}
        if len(img_data) > 10 * 1024 * 1024:
            return {"status": "error", "message": "图片不能超过 10MB"}
        if not _check_magic_bytes_provider()(img_data):
            return {"status": "error", "message": "文件头校验失败，请上传有效的图片文件"}
        b64 = base64.b64encode(img_data)
        media.delete(f"/Users/{user_id}/Images/Primary")
        media.post(f"/Users/{user_id}/Images/Primary", data=b64, headers={"Content-Type": c_type})

        source = "URL" if url else "文件上传"
        _audit_log_provider()(
            admin_id=admin_user.get("id", ""),
            admin_name=admin_name,
            action="修改用户头像",
            target_user_id=user_id,
            target_user_name=target_name,
            details=f"来源:{source}",
            ip_address=ip_address,
        )

        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": _safe_error_message_provider()(e)}


@router.post("/api/user/avatar")
async def api_user_self_avatar(request: Request, file: UploadFile = File(...)):
    """C 端用户自助修改头像(从 session 读 user_id,不能改别人的)"""
    user = request.session.get("req_user")
    if not user or not user.get("Id"):
        return {"status": "error", "message": "请先登录"}
    user_id = user["Id"]
    try:
        img_data = await file.read()
        if len(img_data) > 10 * 1024 * 1024:
            return {"status": "error", "message": "图片不能超过 10MB"}
        if not _check_magic_bytes_provider()(img_data):
            return {"status": "error", "message": "文件头校验失败，请上传有效的图片文件"}
        c_type = file.content_type or "image/jpeg"
        b64 = base64.b64encode(img_data)
        media = _media_api_provider()
        media.delete(f"/Users/{user_id}/Images/Primary")
        media.post(f"/Users/{user_id}/Images/Primary", data=b64, headers={"Content-Type": c_type})
        return {"status": "success", "message": "头像已更新"}
    except Exception as e:
        return {"status": "error", "message": _safe_error_message_provider()(e, "上传失败")}
