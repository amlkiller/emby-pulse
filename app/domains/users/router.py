from fastapi import APIRouter, Request, Response, UploadFile, File, Form, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from app.infra.db import audit_dao
from app.domains.system import invitation_dao
from app.domains.users import user_dao
from app.domains.users import user_bot_dao
from app.domains.notifications import notify_admin
from app.domains.users.request_permission_router import (
    UserReqPermissionModel,
    api_get_user_req_permission,
    api_update_user_req_permission,
    router as request_permission_router,
)
from app.domains.users.tag_router import (
    TAG_COLORS,
    TagCreateModel,
    UserTagsUpdateModel,
    api_create_tag,
    api_delete_tag,
    api_delete_tag_by_name,
    api_get_tags,
    api_get_user_tags,
    api_update_user_tags,
    router as tag_router,
)
from app.domains.users.template_router import (
    api_get_default_template,
    api_set_default_template,
    router as template_router,
)
from app.infra.clients.media_server_client import media_api
from app.infra.clients.network_client import network_client
from app.infra.config.media_server_settings import get_media_server_public_host
from app.infra.config.request_portal_settings import get_user_portal_url
from app.infra.config.user_bot_settings import get_default_user_template_id
from app.infra.config.user_visibility_settings import get_hidden_users
from app.domains.users import public_service as user_service

from app.domains.users.auth import is_admin_user  # 🔒 引入管理员权限检查
from app.core.security import validate_password_strength  # 🔒 统一密码强度校验
from app.utils.image_validator import check_magic_bytes  # 🔒 头像魔数校验
import datetime
import secrets
import base64
import logging
from app.core.security_utils import safe_error_message
from app.core.rate_limiter import get_client_ip

router = APIRouter()

# 记录容器启动时间(用于验证重启后失效)
APP_START_TIME = datetime.datetime.now().isoformat()

# ==========================================
# 操作审计日志
# ==========================================

def add_audit_log(admin_id: str, admin_name: str, action: str,
                  target_user_id: str = None, target_user_name: str = None,
                  target_count: int = 0, details: str = "", ip_address: str = ""):
    """添加操作审计日志"""
    try:
        audit_dao.create_user_audit_log(
            admin_id,
            admin_name,
            action,
            target_user_id,
            target_user_name,
            target_count,
            details,
            ip_address,
            datetime.datetime.now().isoformat(),
        )
    except Exception as e:
        logging.error(f"[审计日志] 添加失败: {e}")

# ==========================================
# 密码验证相关
# ==========================================

class PasswordVerifyModel(BaseModel):
    username: str  # 管理员账号
    password: str  # 管理员密码

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

@router.get("/api/manage/user/admin_list")
def api_get_admin_list(request: Request):
    """获取 Emby 管理员账号列表(用于密码验证选择)"""
    if not request.session.get("user"):
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    admin_list = get_emby_admin_users()
    return {"status": "success", "data": admin_list}

# ==========================================
# 审计日志 API
# ==========================================

@router.get("/api/manage/audit_logs")
def api_get_audit_logs(request: Request, page: int = 1, limit: int = 20,
                       action: str = None, start_date: str = None,
                       end_date: str = None, target_user_id: str = None):
    """获取操作审计日志列表"""
    if not request.session.get("user"):
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    try:
        result = audit_dao.list_user_audit_logs(
            page=page,
            limit=limit,
            action=action,
            start_date=start_date,
            end_date=end_date,
            target_user_id=target_user_id,
        )

        return {
            "status": "success",
            "data": {
                "logs": result["logs"],
                "total_count": result["total_count"],
                "total_pages": result["total_pages"],
                "page": result["page"]
            }
        }
    except Exception as e:
        logging.error(f"[审计日志] 查询失败: {e}")
        return {"status": "error", "message": safe_error_message(e)}

@router.get("/api/manage/audit_logs/stats")
def api_get_audit_stats(request: Request, days: int = 7):
    """获取审计日志统计"""
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    days = max(1, min(days, 365))

    try:
        start_date = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
        stats = audit_dao.get_user_audit_stats(start_date)

        return {
            "status": "success",
            "data": {
                "action_stats": stats["action_stats"],
                "admin_stats": stats["admin_stats"],
                "total_count": stats["total_count"],
                "days": days
            }
        }
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

@router.delete("/api/manage/audit_logs/{log_id}")
def api_delete_audit_log(log_id: int, request: Request):
    """删除单条审计日志"""
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    try:
        audit_dao.delete_user_audit_log(log_id)
        return {"status": "success", "message": "删除成功"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

@router.post("/api/manage/audit_logs/clear")
def api_clear_audit_logs(request: Request, days: int = 30):
    """清理超过指定天数的审计日志"""
    if not request.session.get("user"):
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    try:
        cutoff_date = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
        deleted_count = audit_dao.clear_user_audit_logs_before(cutoff_date)
        return {"status": "success", "message": f"已清理 {deleted_count} 条日志"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

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
            elif verify_dt < datetime.datetime.fromisoformat(APP_START_TIME):
                verified = False
                request.session["delete_verified"] = False
        except:
            verified = False

    return {"status": "success", "verified": verified}

# 🔥 remark 字段迁移已由 database.py 的 ensure_tables() 处理,此处不再重复
# 移除重复的 ALTER TABLE 代码,避免日志报错

# 🔥 无感迁移:添加 admin_disabled 字段并迁移历史数据
def migrate_admin_disabled():
    """迁移 admin_disabled 字段,区分过期禁用和管理员禁用"""
    try:
        today = datetime.date.today().strftime("%Y-%m-%d")
        disabled_user_ids = set()

        try:
            res = media_api.get("/Users", timeout=10)
            if res.status_code == 200:
                for u in res.json():
                    if u.get('Policy', {}).get('IsDisabled', False):
                        disabled_user_ids.add(u['Id'])
        except Exception as e:
            logging.getLogger("uvicorn").warning(f"⚠️ 迁移时获取用户列表失败: {e}")

        migrated_count = user_dao.migrate_admin_disabled(disabled_user_ids, today)
        if migrated_count is not None:
            logging.getLogger("uvicorn").info("✅ 数据库迁移:已添加 admin_disabled 字段")
            logging.getLogger("uvicorn").info(f"✅ 数据库迁移完成:已标记 {migrated_count} 个管理员禁用用户")
    except Exception as e:
        logging.getLogger("uvicorn").error(f"❌ 数据库迁移失败: {e}")

class UserUpdateModelEx(BaseModel):
    user_id: str
    is_disabled: bool = False
    expire_date: Optional[str] = None
    password: Optional[str] = None
    enable_all_folders: Optional[bool] = None  # 🔥 改为 Optional，允许 null
    enabled_folders: Optional[List[str]] = None  # 🔥 改为 Optional，允许 null
    excluded_sub_folders: Optional[List[str]] = None  # 🔥 改为 Optional，允许 null
    enable_downloading: bool = True
    enable_video_transcoding: bool = True
    enable_audio_transcoding: bool = True
    max_parental_rating: Optional[int] = None
    block_unrated_items: Optional[bool] = None  # 阻止未分级项目
    blocked_tags: Optional[str] = None  # 阻止特定标签,逗号分隔
    max_concurrent: Optional[int] = None
    is_vip: bool = False
    remark: Optional[str] = ""
    allow_routes: Optional[str] = ""  # 用户专属允许线路,逗号分隔
    block_routes: Optional[str] = ""  # 用户专属屏蔽线路,逗号分隔
    req_free: Optional[int] = 0  # 求片权限:0=跟随全局, 1=免费, 2=付费
    req_free_count: Optional[int] = -1  # 免费求片次数:-1=无限, >=0=剩余次数
    tags: Optional[str] = ""  # 用户标签,逗号分隔
    apply_template_id: Optional[str] = None
    copy_library: bool = True
    copy_policy: bool = True
    copy_parental: bool = True

class NewUserModelEx(BaseModel):
    name: str
    password: Optional[str] = None
    expire_date: Optional[str] = None
    template_user_id: Optional[str] = None
    copy_library: bool = True
    copy_policy: bool = True
    copy_parental: bool = True
    max_concurrent: Optional[int] = None
    is_vip: bool = False
    remark: Optional[str] = ""
    allow_routes: Optional[str] = ""
    block_routes: Optional[str] = ""
    req_free: Optional[int] = 0  # 0=跟随全局, 1=免费
    req_free_count: Optional[int] = -1  # -1=无限次, >=0=剩余次数

class InviteGenModelLocal(BaseModel):
    days: int
    count: Optional[int] = 1
    template_user_id: Optional[str] = None
    type: Optional[str] = "register"  # register 或 renew
    routes: Optional[str] = ""  # 线路设置,逗号分隔
    route_mode: Optional[str] = "block"  # 允许或屏蔽模式
    req_free: Optional[int] = 0  # 求片权限:0=跟随全局, 1=免费
    req_free_count: Optional[int] = -1  # -1=无限次, >=0=剩余次数

class BatchActionModelLocal(BaseModel):
    user_ids: List[str]
    action: str
    value: Optional[str] = None
    copy_library: Optional[bool] = True
    copy_policy: Optional[bool] = True
    copy_parental: Optional[bool] = True
    allow_routes: Optional[str] = ""
    block_routes: Optional[str] = ""
    req_free: Optional[int] = 0  # 求片权限:0=跟随全局, 1=免费
    req_free_count: Optional[int] = -1  # 免费求片次数:-1=无限, >=0=次数
    username: Optional[str] = None  # 批量删除时必须传管理员账号
    password: Optional[str] = None  # 批量删除时必须传密码

class InviteBatchModelLocal(BaseModel):
    codes: List[str]
    action: str

DANGEROUS_POLICY_KEYS = {'IsAdministrator', 'IsDisabled', 'LoginAttemptsBeforeLockout'}
LIBRARY_POLICY_KEYS = {'EnableAllFolders', 'EnabledFolders', 'ExcludedSubFolders', 'BlockedMediaFolders', 'BlockedChannels', 'EnableAllChannels', 'EnabledChannels'}
PARENTAL_POLICY_KEYS = {'MaxParentalRating', 'BlockUnratedItems', 'BlockedTags', 'AllowedTags'}

def clone_policy(target_policy: dict, src_policy: dict, copy_lib: bool, copy_pol: bool, copy_par: bool):
    """深拷贝策略对象,支持分类映射。无需枚举,兼容未来所有 Emby 新权限字段!"""
    for k, v in src_policy.items():
        if k in DANGEROUS_POLICY_KEYS:
            continue
        is_lib = k in LIBRARY_POLICY_KEYS
        is_par = k in PARENTAL_POLICY_KEYS
        is_pol = not is_lib and not is_par

        if (copy_lib and is_lib) or (copy_par and is_par) or (copy_pol and is_pol):
            target_policy[k] = v
    return target_policy

def check_expired_users():
    """检查过期用户并自动禁用(标记为过期禁用,非管理员禁用)"""
    try:
        rows = user_dao.list_users_with_expire_date_for_check()
        if not rows: return
        now_str = datetime.datetime.now().strftime("%Y-%m-%d")
        for row in rows:
            if row['expire_date'] < now_str:
                uid = row['user_id']
                try:
                    u_res = media_api.get(f"/Users/{uid}", timeout=5)
                    if u_res.status_code == 200:
                        user = u_res.json()
                        policy = user.get('Policy', {})
                        if not policy.get('IsDisabled', False):
                            policy['IsDisabled'] = True
                            media_api.post(f"/Users/{uid}/Policy", json=policy)
                            # 标记为过期禁用(非管理员禁用)
                            try:
                                user_dao.set_user_admin_disabled(uid, False)
                            except Exception: pass
                except Exception as e: pass
    except Exception as e: pass

@router.get("/api/manage/libraries")
def api_get_libraries(request: Request):
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    try:
        res = media_api.get("/Library/VirtualFolders", timeout=5)
        if res.status_code == 200:
            libs = [{"Id": item["Guid"], "Name": item["Name"]} for item in res.json() if "Guid" in item]
            return {"status": "success", "data": libs}
        return {"status": "error", "message": "媒体服务器 API 返回异常"}
    except Exception as e: return {"status": "error", "message": safe_error_message(e)}

@router.get("/api/manage/users")
def api_manage_users(request: Request, refresh: bool = False):
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    check_expired_users()

    # 如果请求强制刷新,清除缓存
    if refresh:
        user_service.invalidate_emby_users_cache()

    public_host = get_media_server_public_host()
    if public_host.endswith('/'): public_host = public_host[:-1]

    try:
        # 🔥 使用缓存的用户列表
        emby_users = user_service.get_emby_users_cached()
        if emby_users is None:
            return {"status": "error", "message": "媒体服务器无法连接"}
        meta_rows = user_dao.list_all_user_meta()
        meta_map = {r['user_id']: dict(r) for r in meta_rows} if meta_rows else {}

        # 查询 TG 绑定关系 (emby_user_id -> tg_user_id)
        tg_bindings = {}
        try:
            rows = user_bot_dao.list_emby_tg_user_bindings()
            tg_bindings = {row["emby_user_id"]: row["tg_user_id"] for row in rows if row["emby_user_id"]}
        except:
            pass

        final_list = []
        for u in emby_users:
            uid = u['Id']
            meta = meta_map.get(uid, {})
            policy = u.get('Policy', {})
            remark = meta.get('remark', '')

            # 检查是否置顶(备注以 [PINNED] 开头)
            is_pinned = remark.startswith('[PINNED]') if remark else False
            # 显示时移除 [PINNED] 标记
            display_remark = remark[8:] if is_pinned else remark

            final_list.append({
                "Id": uid, "Name": u['Name'], "LastLoginDate": u.get('LastLoginDate'),
                "IsDisabled": policy.get('IsDisabled', False), "IsAdmin": policy.get('IsAdministrator', False),
                "AdminDisabled": bool(meta.get('admin_disabled', 0)),  # 管理员禁用标记
                "ExpireDate": meta.get('expire_date'), "Note": meta.get('note'), "PrimaryImageTag": u.get('PrimaryImageTag'),
                "EnableAllFolders": policy.get('EnableAllFolders', True),
                "EnabledFolders": policy.get('EnabledFolders', []), "ExcludedSubFolders": policy.get('ExcludedSubFolders', []),
                "EnableDownloading": policy.get('EnableContentDownloading', True),
                "EnableVideoTranscoding": policy.get('EnableVideoPlaybackTranscoding', True),
                "EnableAudioTranscoding": policy.get('EnableAudioPlaybackTranscoding', True),
                "MaxParentalRating": policy.get('MaxParentalRating'),
                "MaxConcurrent": meta.get('max_concurrent'),
                "IsVIP": bool(meta.get('is_vip', 0)),
                "Remark": display_remark,
                "Pinned": is_pinned,  # 置顶标记
                "AllowRoutes": meta.get('allow_routes', ''),
                "BlockRoutes": meta.get('block_routes', ''),
                "TgUserId": tg_bindings.get(uid),  # TG 用户 ID
                # 🔥 求片权限
                "req_free": meta.get('req_free', 0),
                "req_free_count": meta.get('req_free_count', -1),
                # 🔥 用户标签
                "tags": meta.get('tags', '')
            })
        return {"status": "success", "data": final_list, "emby_url": public_host}
    except Exception as e: return {"status": "error", "message": safe_error_message(e)}

@router.get("/api/manage/user/{user_id}")
def api_get_single_user(user_id: str, request: Request):
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    try:
        res = media_api.get(f"/Users/{user_id}", timeout=5)
        if res.status_code == 200:
            user_data = res.json()
            policy = user_data.get('Policy', {})
            meta_row = user_dao.get_user_meta(user_id)

            return {
                "status": "success",
                "data": {
                    "Id": user_data['Id'], "Name": user_data['Name'],
                    "EnableAllFolders": policy.get('EnableAllFolders', True), "EnabledFolders": policy.get('EnabledFolders', []),
                    "ExcludedSubFolders": policy.get('ExcludedSubFolders', []), "EnableDownloading": policy.get('EnableContentDownloading', True),
                    "EnableVideoTranscoding": policy.get('EnableVideoPlaybackTranscoding', True), "EnableAudioTranscoding": policy.get('EnableAudioPlaybackTranscoding', True),
                    "MaxParentalRating": policy.get('MaxParentalRating'),
                    "BlockUnratedItems": policy.get('BlockUnratedItems', False),
                    "BlockedTags": ','.join(policy.get('BlockedTags', [])) if policy.get('BlockedTags') else "",
                    "MaxConcurrent": meta_row['max_concurrent'] if meta_row else None,
                    "IsVIP": bool(meta_row['is_vip']) if meta_row and meta_row['is_vip'] else False,
                    "Remark": meta_row['remark'] if meta_row and 'remark' in meta_row.keys() else "",
                    # 🔥 求片权限
                    "req_free": meta_row['req_free'] if meta_row and 'req_free' in meta_row.keys() else 0,
                    "req_free_count": meta_row['req_free_count'] if meta_row and 'req_free_count' in meta_row.keys() else -1
                }
            }
        return {"status": "error"}
    except: return {"status": "error"}

@router.get("/api/user/image/{user_id}")
def get_user_avatar(user_id: str, request: Request):
    if not request.session.get("user"):
        return Response(status_code=401)
    if not is_admin_user(request):
        return Response(status_code=403)
    try:
        res = media_api.get(f"/Users/{user_id}/Images/Primary", params={"quality": 90}, timeout=5, stream=True)
        if res.status_code == 200: return Response(content=res.content, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})
        return Response(status_code=404)
    except: return Response(status_code=404)

@router.post("/api/manage/user/image")
async def api_update_user_image(request: Request, user_id: str = Form(...), url: str = Form(None), file: UploadFile = File(None)):
    if not request.session.get("user"): return {"status": "error"}
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    try:
        admin_user = request.session.get("user", {})
        admin_name = admin_user.get("name", admin_user.get("username", "未知"))
        ip_address = get_client_ip(request)

        # 获取目标用户名
        target_name = ""
        try:
            u_res = media_api.get(f"/Users/{user_id}", timeout=5)
            if u_res.status_code == 200:
                target_name = u_res.json().get("Name", "")
        except Exception: pass

        img_data = None; c_type = "image/png"
        if url:
            from app.utils.url_validator import validate_url
            validation = validate_url(url, allow_internal=False)
            if not validation["valid"]:
                return {"status": "error", "message": f"URL 不安全: {validation['error']}"}
            d_res = network_client.get(url, timeout=10, allow_redirects=False, stream=True)
            if d_res.status_code == 200:
                img_data = d_res.content
                c_type = d_res.headers.get('Content-Type', 'image/png')
        elif file:
            img_data = await file.read()
            c_type = file.content_type or "image/jpeg"
        if not img_data: return {"status": "error", "message": "无图片数据"}
        # 🔒 尺寸 + magic bytes 校验，防止伪装 Content-Type 上传非图像
        if len(img_data) > 10 * 1024 * 1024:
            return {"status": "error", "message": "图片不能超过 10MB"}
        if not check_magic_bytes(img_data):
            return {"status": "error", "message": "文件头校验失败，请上传有效的图片文件"}
        b64 = base64.b64encode(img_data)
        media_api.delete(f"/Users/{user_id}/Images/Primary")
        media_api.post(f"/Users/{user_id}/Images/Primary", data=b64, headers={"Content-Type": c_type})

        # 记录审计日志
        source = "URL" if url else "文件上传"
        add_audit_log(
            admin_id=admin_user.get("id", ""),
            admin_name=admin_name,
            action="修改用户头像",
            target_user_id=user_id,
            target_user_name=target_name,
            details=f"来源:{source}",
            ip_address=ip_address
        )

        return {"status": "success"}
    except Exception as e: return {"status": "error", "message": safe_error_message(e)}

# ==========================================
# C 端用户自助 API(修改头像 / 修改密码)
# ==========================================
class UserPasswordChangeModel(BaseModel):
    old_password: str
    new_password: str

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
        if not check_magic_bytes(img_data):
            return {"status": "error", "message": "文件头校验失败，请上传有效的图片文件"}
        c_type = file.content_type or "image/jpeg"
        b64 = base64.b64encode(img_data)
        media_api.delete(f"/Users/{user_id}/Images/Primary")
        media_api.post(f"/Users/{user_id}/Images/Primary", data=b64, headers={"Content-Type": c_type})
        return {"status": "success", "message": "头像已更新"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e, "上传失败")}

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
    pw_valid, pw_error = validate_password_strength(data.new_password)
    if not pw_valid:
        return {"status": "error", "message": pw_error}
    try:
        # 先用旧密码验证身份
        auth_res = media_api.authenticate_by_name(user_name, data.old_password, timeout=8)
        if auth_res.status_code != 200:
            return {"status": "error", "message": "旧密码不正确"}
        # 验证通过,修改密码
        media_api.post(f"/Users/{user_id}/Password", json={"Id": user_id, "CurrentPw": data.old_password, "NewPw": data.new_password})
        return {"status": "success", "message": "密码已修改"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e, "修改失败")}


# ==================== 🔥 用户媒体库设置 ====================

@router.get("/api/user/libraries")
def api_get_user_libraries(request: Request):
    """获取所有媒体库 + 用户隐藏状态（过滤掉管理员已隐藏的）"""
    user = request.session.get("req_user")
    if not user or not user.get("Id"):
        return {"status": "error", "message": "请先登录"}
    user_id = user["Id"]

    try:
        # 获取所有媒体库
        libs_res = media_api.get("/Library/VirtualFolders", timeout=5)
        if libs_res.status_code != 200:
            return {"status": "error", "message": "媒体服务器无法连接"}
        libs = libs_res.json()
        all_guids = [lib["Guid"] for lib in libs if "Guid" in lib]

        # 获取用户当前权限
        user_res = media_api.get(f"/Users/{user_id}", timeout=5)
        if user_res.status_code != 200:
            return {"status": "error", "message": "用户信息获取失败"}
        user_data = user_res.json()
        policy = user_data.get("Policy", {})
        enable_all_folders = policy.get("EnableAllFolders", True)
        enabled_folders = policy.get("EnabledFolders", [])

        # 🔥 从本地数据库获取管理员初始设置的媒体库权限
        row = user_dao.get_user_library_settings(user_id)
        admin_enabled_folders_str = row["admin_enabled_folders"] if row and row["admin_enabled_folders"] else None
        user_hidden_str = row["hidden_libraries"] if row and row["hidden_libraries"] else None

        # 🔥 解析管理员允许的媒体库
        if admin_enabled_folders_str:
            admin_enabled_folders = set(g.strip() for g in admin_enabled_folders_str.split(",") if g.strip())
        else:
            admin_enabled_folders = None

        # 🔥 解析用户自己隐藏的媒体库
        if user_hidden_str:
            user_hidden_folders = set(g.strip() for g in user_hidden_str.split(",") if g.strip())
        else:
            user_hidden_folders = set()

        # 🔥 实时检测管理员是否又隐藏了新的媒体库
        # 如果当前 enabled_folders + 用户隐藏的 < admin_enabled_folders，说明管理员又隐藏了
        if admin_enabled_folders is not None:
            # 计算管理员当前允许的媒体库（从当前权限推断）
            # 当前 enabled_folders = 管理员允许的 - 用户隐藏的
            # 所以管理员当前允许的 = enabled_folders + 用户隐藏的（且在 admin_enabled_folders 中）
            current_admin_allowed = set(enabled_folders) | (user_hidden_folders & admin_enabled_folders)

            # 如果 current_admin_allowed 比 admin_enabled_folders 少，说明管理员又隐藏了新的
            if current_admin_allowed < admin_enabled_folders:
                # 更新 admin_enabled_folders
                admin_enabled_folders = current_admin_allowed
                try:
                    user_dao.save_user_admin_enabled_folders(user_id, ",".join(admin_enabled_folders))
                except:
                    pass

        # 构建返回数据（过滤掉管理员已隐藏的媒体库）
        result = []
        for lib in libs:
            guid = lib.get("Guid")
            name = lib.get("Name", "未知")

            # 🔥 如果管理员限制了媒体库，且该媒体库不在管理员允许列表中，则跳过
            if admin_enabled_folders is not None and guid not in admin_enabled_folders:
                continue  # 管理员已隐藏，不展示给用户

            # 判断用户是否自己隐藏了该媒体库
            is_hidden = guid in user_hidden_folders
            result.append({
                "id": guid,
                "name": name,
                "hidden": is_hidden
            })

        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


class HiddenLibrariesModel(BaseModel):
    hidden_libraries: List[str] = []  # 要隐藏的媒体库 Guid 列表


@router.post("/api/user/hidden_libraries")
def api_update_hidden_libraries(data: HiddenLibrariesModel, request: Request):
    """更新用户隐藏的媒体库，同步到 Emby 权限"""
    user = request.session.get("req_user")
    if not user or not user.get("Id"):
        return {"status": "error", "message": "请先登录"}
    user_id = user["Id"]

    try:
        # 获取所有媒体库
        libs_res = media_api.get("/Library/VirtualFolders", timeout=5)
        if libs_res.status_code != 200:
            return {"status": "error", "message": "媒体服务器无法连接"}
        libs = libs_res.json()
        all_guids = [lib["Guid"] for lib in libs if "Guid" in lib]

        # 🔥 获取管理员设置的默认权限
        row = user_dao.get_user_admin_enabled_folders(user_id)
        admin_enabled_folders_str = row["admin_enabled_folders"] if row and row["admin_enabled_folders"] else None

        # 🔥 解析管理员允许的媒体库
        if admin_enabled_folders_str:
            admin_enabled_folders = [g.strip() for g in admin_enabled_folders_str.split(",") if g.strip()]
        else:
            # 没有记录，说明管理员允许全部
            admin_enabled_folders = None

        # 🔥 计算用户可操作的媒体库范围
        if admin_enabled_folders is not None:
            # 用户只能操作管理员允许的媒体库
            user_available_guids = [g for g in all_guids if g in admin_enabled_folders]
        else:
            # 管理员允许全部，用户可以操作所有媒体库
            user_available_guids = all_guids

        # 🔥 计算用户选择隐藏的媒体库
        hidden_guids = [g for g in data.hidden_libraries if g in user_available_guids]
        enabled_guids = [g for g in user_available_guids if g not in hidden_guids]

        # 🔥 同步到 Emby，让播放器生效
        user_res = media_api.get(f"/Users/{user_id}", timeout=5)
        if user_res.status_code == 200:
            policy = user_res.json().get("Policy", {})
            policy["EnableAllFolders"] = False
            policy["EnabledFolders"] = enabled_guids
            media_api.post(f"/Users/{user_id}/Policy", json=policy, timeout=5)

        # 保存到本地数据库
        try:
            user_dao.save_user_hidden_libraries(user_id, ','.join(hidden_guids))
        except Exception as e:
            logging.warning(f"保存隐藏媒体库到本地失败: {e}")

        return {"status": "success", "message": "设置已保存"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


@router.post("/api/manage/invite/gen")
def api_gen_invite(data: InviteGenModelLocal, request: Request):
    if not request.session.get("user"): return {"status": "error"}
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    try:
        admin_user = request.session.get("user", {})
        admin_name = admin_user.get("name", admin_user.get("username", "未知"))
        ip_address = get_client_ip(request)

        count = data.count if data.count and data.count > 0 else 1
        code_type = data.type if data.type in ("register", "renew") else "register"
        routes = data.routes if data.routes else ""
        route_mode = data.route_mode if data.route_mode in ("allow", "block") else "block"
        req_free = data.req_free if data.req_free else 0
        req_free_count = data.req_free_count if data.req_free_count is not None else -1
        codes = [secrets.token_hex(4) for _ in range(count)]
        created_at = datetime.datetime.now().isoformat()
        invitation_dao.create_invitation_codes(
            codes,
            data.days,
            created_at,
            data.template_user_id,
            code_type,
            routes,
            route_mode,
            req_free,
            req_free_count,
        )

        # 记录审计日志
        type_str = "注册码" if code_type == "register" else "续费码"
        add_audit_log(
            admin_id=admin_user.get("id", ""),
            admin_name=admin_name,
            action="生成邀请码",
            target_count=count,
            details=f"类型:{type_str}, 天数:{data.days}, 线路:{routes or '无'}",
            ip_address=ip_address
        )

        # 构建邀请链接
        portal_url = get_user_portal_url().rstrip('/')
        links = [f"{portal_url}/invite/{code}" for code in codes] if portal_url and code_type == "register" else []
        return {"status": "success", "codes": codes, "type": code_type, "links": links, "portal_url": portal_url}
    except Exception as e: return {"status": "error", "message": safe_error_message(e)}

@router.get("/api/manage/invites")
def api_get_invites(request: Request, code_type: str = "all"):
    if not request.session.get("user"): return {"status": "error"}
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    try:
        rows = invitation_dao.list_admin_invitations(code_type)
        data = [dict(r) for r in rows] if rows else []
        # 添加邀请链接
        portal_url = get_user_portal_url().rstrip('/')
        for item in data:
            if item.get('type') == 'register' and item.get('code'):
                item['invite_link'] = f"{portal_url}/invite/{item['code']}" if portal_url else ""

        # 计算统计数据(按类型分组)
        stats = {"all": {"total": 0, "used": 0, "unused": 0}, "register": {"total": 0, "used": 0, "unused": 0}, "renew": {"total": 0, "used": 0, "unused": 0}}
        all_rows = invitation_dao.list_invitation_usage_stats()
        if all_rows:
            for r in all_rows:
                t = r['type'] or 'register'
                is_used = (r['used_count'] or 0) > 0 or r['used_by']
                stats['all']['total'] += 1
                stats[t]['total'] += 1
                if is_used:
                    stats['all']['used'] += 1
                    stats[t]['used'] += 1
                else:
                    stats['all']['unused'] += 1
                    stats[t]['unused'] += 1

        return {"status": "success", "data": data, "stats": stats}
    except Exception as e: return {"status": "error", "message": safe_error_message(e)}

@router.get("/api/manage/invites/export")
def api_export_invites(request: Request, code_type: str = "all"):
    """导出邀请码/续费码为CSV"""
    if not request.session.get("user"): return {"status": "error"}
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    try:
        rows = invitation_dao.list_invitation_export_rows(code_type)
        if not rows:
            return {"status": "error", "message": "无数据"}
        portal_url = get_user_portal_url().rstrip('/')
        lines = ["码,类型,天数,已用次数,最大次数,使用者,状态,生成时间,使用时间,求片权限,免费次数,邀请链接"]
        for r in rows:
            d = dict(r)
            status_str = "已用" if d.get("status") == 1 else "可用"
            type_str = "注册码" if d.get("type") == "register" else "续费码"
            link = f"{portal_url}/invite/{d['code']}" if portal_url and d.get("type") == "register" else ""
            req_free = d.get('req_free', 0) or 0
            req_free_count = d.get('req_free_count', -1) if req_free == 1 else ''
            req_free_text = "免费求片" if req_free == 1 else "跟随全局"
            lines.append(f"{d['code']},{type_str},{d['days']},{d['used_count']},{d['max_uses']},{d.get('used_by','')},{status_str},{d.get('created_at','')},{d.get('used_at','')},{req_free_text},{req_free_count},{link}")
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse("\n".join(lines), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=codes_{code_type}.csv"})
    except Exception as e: return {"status": "error", "message": safe_error_message(e)}

@router.post("/api/manage/invites/batch")
def api_manage_invites_batch(data: InviteBatchModelLocal, request: Request):
    if not request.session.get("user"): return {"status": "error"}
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    try:
        admin_user = request.session.get("user", {})
        admin_name = admin_user.get("name", admin_user.get("username", "未知"))
        ip_address = get_client_ip(request)

        if data.action == "delete":
            invitation_dao.delete_invitation_codes(data.codes)
            # 记录审计日志
            add_audit_log(
                admin_id=admin_user.get("id", ""),
                admin_name=admin_name,
                action="批量删除邀请码",
                target_count=len(data.codes),
                details=f"删除码: {', '.join(data.codes[:10])}{'...' if len(data.codes) > 10 else ''}",
                ip_address=ip_address
            )
        return {"status": "success", "message": "删除成功"}
    except Exception as e: return {"status": "error", "message": safe_error_message(e)}

@router.post("/api/manage/user/library")
def api_manage_user_library(data: UserUpdateModelEx, request: Request):
    """单独保存媒体库权限"""
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    # 🔒 Emby 不可用时拒绝，避免本地/远端权限错位
    if not media_api.health_check():
        return {"status": "error", "message": "Emby 服务不可用，请稍后重试"}
    user_service.invalidate_emby_users_cache()
    try:
        # 获取用户当前 Policy
        p_res = media_api.get(f"/Users/{data.user_id}")
        if p_res.status_code != 200:
            return {"status": "error", "message": "用户不存在"}

        p = p_res.json().get('Policy', {})

        # 获取旧的媒体库权限用于对比
        old_enable_all = p.get('EnableAllFolders', True)
        old_enabled_folders = set(p.get('EnabledFolders', []))

        # 设置新的媒体库权限
        new_enable_all = bool(data.enable_all_folders)
        new_enabled_folders = set([str(x) for x in data.enabled_folders]) if not new_enable_all and data.enabled_folders is not None else set()

        # 检测是否有变化
        library_changed = (old_enable_all != new_enable_all) or (old_enabled_folders != new_enabled_folders)

        if library_changed:
            p['EnableAllFolders'] = new_enable_all
            p['EnabledFolders'] = list(new_enabled_folders) if not new_enable_all else []

            # 同步更新 admin_enabled_folders，但保留用户的 hidden_libraries
            try:
                final_enabled = user_dao.sync_user_library_permissions(data.user_id, new_enable_all, new_enabled_folders)
                if final_enabled is not None:
                    p['EnabledFolders'] = final_enabled
            except Exception: pass

            # 更新 Emby Policy
            media_api.post(f"/Users/{data.user_id}/Policy", json=p)

        return {"status": "success", "message": "媒体库权限已保存"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

@router.post("/api/manage/user/update")
def api_manage_user_update(data: UserUpdateModelEx, request: Request):
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    # 🔒 Emby 不可用时拒绝
    if not media_api.health_check():
        return {"status": "error", "message": "Emby 服务不可用，请稍后重试"}
    # 🔥 清除用户缓存
    user_service.invalidate_emby_users_cache()
    try:
        exist = user_dao.get_user_meta(data.user_id)
        # 获取旧的 Emby Policy 用于对比变更
        old_policy = {}
        old_user_res = media_api.get(f"/Users/{data.user_id}", timeout=5)
        if old_user_res.status_code == 200:
            old_policy = old_user_res.json().get('Policy', {})
        v_exp = data.expire_date if data.expire_date else None
        v_max = data.max_concurrent
        v_vip = 1 if data.is_vip else 0
        v_remark = data.remark if data.remark else ""
        # 🔥 线路权限:只有明确传递了值才更新,否则保留原值
        # 🔥 线路权限:保留空字符串(表示清空),None 表示未传递
        v_allow_routes = data.allow_routes
        v_block_routes = data.block_routes
        v_req_free = data.req_free if data.req_free is not None else 0
        v_req_free_count = data.req_free_count if data.req_free_count is not None else -1
        v_tags = data.tags if data.tags is not None else ""

        user_dao.save_manage_user_meta(
            data.user_id,
            v_exp,
            v_max,
            v_vip,
            v_remark,
            v_allow_routes,
            v_block_routes,
            v_req_free,
            v_req_free_count,
            v_tags,
            datetime.datetime.now().isoformat(),
        )

        if data.password:
            media_api.post(f"/Users/{data.user_id}/Password", json={"Id": data.user_id, "NewPw": data.password})

        p_res = media_api.get(f"/Users/{data.user_id}")
        if p_res.status_code == 200:
            p = p_res.json().get('Policy', {})

            if data.apply_template_id:
                src_res = media_api.get(f"/Users/{data.apply_template_id}", timeout=5)
                if src_res.status_code == 200:
                    src_policy = src_res.json().get('Policy', {})
                    p = clone_policy(p, src_policy, data.copy_library, data.copy_policy, data.copy_parental)
                    # 🔥 应用模板时同步更新 admin_enabled_folders，但保留用户的 hidden_libraries
                    if data.copy_library:
                        try:
                            final_enabled = user_dao.sync_user_library_permissions(
                                data.user_id,
                                p.get('EnableAllFolders', True),
                                p.get('EnabledFolders', []),
                            )
                            if final_enabled is not None:
                                p['EnabledFolders'] = final_enabled
                        except Exception: pass

            if data.is_disabled is not None:
                p['IsDisabled'] = data.is_disabled
                if not data.is_disabled: p['LoginAttemptsBeforeLockout'] = -1
                # 设置 admin_disabled 标记
                try:
                    user_dao.set_user_admin_disabled(data.user_id, data.is_disabled)
                except Exception: pass
            if data.enable_all_folders is not None:
                # 🔥 检测媒体库权限是否真的有变化
                old_enable_all = old_policy.get('EnableAllFolders', True)
                old_enabled_folders = set(old_policy.get('EnabledFolders', []))
                new_enable_all = bool(data.enable_all_folders)
                new_enabled_folders = set([str(x) for x in data.enabled_folders]) if not new_enable_all and data.enabled_folders is not None else set()

                # 🔥 只有媒体库权限真的变化时才更新
                library_changed = (old_enable_all != new_enable_all) or (old_enabled_folders != new_enabled_folders)

                if library_changed:
                    p['EnableAllFolders'] = new_enable_all
                    p['EnabledFolders'] = list(new_enabled_folders) if not new_enable_all else []
                    # 🔥 同步更新 admin_enabled_folders，但保留用户的 hidden_libraries
                    try:
                        final_enabled = user_dao.sync_user_library_permissions(data.user_id, new_enable_all, new_enabled_folders)
                        if final_enabled is not None:
                            p['EnabledFolders'] = final_enabled
                    except Exception: pass
            if data.excluded_sub_folders is not None: p['ExcludedSubFolders'] = data.excluded_sub_folders
            if data.enable_downloading is not None: p['EnableContentDownloading'] = data.enable_downloading; p['EnableSyncTranscoding'] = data.enable_downloading
            if data.enable_video_transcoding is not None: p['EnableVideoPlaybackTranscoding'] = data.enable_video_transcoding; p['EnablePlaybackRemuxing'] = data.enable_video_transcoding
            if data.enable_audio_transcoding is not None: p['EnableAudioPlaybackTranscoding'] = data.enable_audio_transcoding
            if data.max_parental_rating is not None:
                # Emby 对"不限制"的处理:字段不存在或 null,而不是 0
                # 设置 MaxParentalRating = 0 仍会被 Emby 视为有限制
                if data.max_parental_rating == 0:
                    # 不限制:删除 MaxParentalRating 字段,同时删除 BlockUnratedItems
                    p.pop('MaxParentalRating', None)
                    p.pop('BlockUnratedItems', None)
                else:
                    p['MaxParentalRating'] = int(data.max_parental_rating)
                    # 只有在设置了分级限制时,才处理 block_unrated_items
                    if data.block_unrated_items is not None:
                        p['BlockUnratedItems'] = data.block_unrated_items
            if data.blocked_tags is not None:
                if data.blocked_tags.strip():
                    p['BlockedTags'] = [tag.strip() for tag in data.blocked_tags.split(',') if tag.strip()]
                else:
                    p.pop('BlockedTags', None)

            media_api.post(f"/Users/{data.user_id}/Policy", json=p)

        # 记录审计日志
        admin_user = request.session.get("user", {})
        admin_name = admin_user.get("name", "未知")
        ip_address = get_client_ip(request)
        # 获取目标用户名
        target_name = ""
        try:
            u_res = media_api.get(f"/Users/{data.user_id}", timeout=5)
            if u_res.status_code == 200:
                target_name = u_res.json().get("Name", "")
        except Exception: pass
        old_meta = exist or {}

        # 构建详细变更记录(只记录真正变更的字段)
        details_parts = []
        # 密码
        if data.password:
            details_parts.append("重置密码")
        # 禁用/启用状态(对比旧 Policy)
        old_disabled = old_policy.get('IsDisabled', False)
        if data.is_disabled is not None and data.is_disabled != old_disabled:
            details_parts.append("禁用账号" if data.is_disabled else "启用账号")
        # 过期日期(对比旧值)
        old_expire = old_meta.get("expire_date", "") or ""
        new_expire = data.expire_date or ""
        if new_expire != old_expire:
            details_parts.append(f"过期日期:{old_expire or '无'}→{new_expire or '无'}")
        # VIP状态(对比旧值)
        old_vip = bool(old_meta.get("is_vip", 0))
        if data.is_vip != old_vip:
            details_parts.append(f"VIP:{'VIP' if old_vip else '普通'}→{'VIP' if data.is_vip else '普通'}")
        # 备注(对比旧值)
        old_remark = old_meta.get("remark", "") or ""
        new_remark = data.remark or ""
        if new_remark != old_remark:
            details_parts.append(f"备注:{old_remark or '空'}→{new_remark or '空'}")
        # 最大并发数(对比旧值)
        old_max = old_meta.get("max_concurrent")
        new_max = data.max_concurrent
        if new_max != old_max:
            details_parts.append(f"并发数:{old_max or '无'}→{new_max or '无'}")
        # 线路设置(对比旧值)
        old_allow = old_meta.get("allow_routes", "") or ""
        new_allow = data.allow_routes or ""
        if new_allow != old_allow:
            details_parts.append(f"允许线路:{old_allow or '无'}→{new_allow or '无'}")
        old_block = old_meta.get("block_routes", "") or ""
        new_block = data.block_routes or ""
        if new_block != old_block:
            details_parts.append(f"屏蔽线路:{old_block or '无'}→{new_block or '无'}")
        # 库权限(对比旧 Policy)
        old_all_folders = old_policy.get('EnableAllFolders', True)
        if data.enable_all_folders is not None and data.enable_all_folders != old_all_folders:
            if data.enable_all_folders:
                details_parts.append("库权限:指定→全部媒体库")
            else:
                old_folders_count = len(old_policy.get('EnabledFolders', []))
                new_folders_count = len(data.enabled_folders) if data.enabled_folders else 0
                details_parts.append(f"库权限:全部→指定{new_folders_count}个库")
        elif data.enable_all_folders == False and data.enabled_folders:
            # 仍然是指定库,但库数量变了
            old_folders_count = len(old_policy.get('EnabledFolders', []))
            new_folders_count = len(data.enabled_folders)
            if old_folders_count != new_folders_count:
                details_parts.append(f"库权限:{old_folders_count}个→{new_folders_count}个库")
        # 下载权限(对比旧 Policy)
        old_download = old_policy.get('EnableContentDownloading', True)
        if data.enable_downloading is not None and data.enable_downloading != old_download:
            details_parts.append(f"下载权限:{'开启' if old_download else '关闭'}→{'开启' if data.enable_downloading else '关闭'}")
        # 视频转码(对比旧 Policy)
        old_video = old_policy.get('EnableVideoPlaybackTranscoding', True)
        if data.enable_video_transcoding is not None and data.enable_video_transcoding != old_video:
            details_parts.append(f"视频转码:{'开启' if old_video else '关闭'}→{'开启' if data.enable_video_transcoding else '关闭'}")
        # 音频转码(对比旧 Policy)
        old_audio = old_policy.get('EnableAudioPlaybackTranscoding', True)
        if data.enable_audio_transcoding is not None and data.enable_audio_transcoding != old_audio:
            details_parts.append(f"音频转码:{'开启' if old_audio else '关闭'}→{'开启' if data.enable_audio_transcoding else '关闭'}")
        # 分级控制(对比旧 Policy)
        old_rating = old_policy.get('MaxParentalRating')
        new_rating = data.max_parental_rating
        if new_rating is not None and new_rating != old_rating:
            if new_rating == -1:
                details_parts.append(f"分级控制:{old_rating or '无限制'}级→无限制")
            elif old_rating is None:
                details_parts.append(f"分级控制:无限制→最大{new_rating}级")
            else:
                details_parts.append(f"分级控制:{old_rating}级→{new_rating}级")
        # 应用模板
        if data.apply_template_id:
            details_parts.append("应用权限模板")
        # 排除子文件夹(对比旧 Policy)
        old_excluded = old_policy.get('ExcludedSubFolders', []) or []
        new_excluded = data.excluded_sub_folders or []
        if len(new_excluded) != len(old_excluded) or (new_excluded and set(new_excluded) != set(old_excluded)):
            details_parts.append(f"排除文件夹:{len(old_excluded)}个→{len(new_excluded)}个")

        details = ", ".join(details_parts) if details_parts else "无变更"
        add_audit_log(
            admin_id=admin_user.get("id", ""),
            admin_name=admin_name,
            action="修改用户",
            target_user_id=data.user_id,
            target_user_name=target_name,
            details=details,
            ip_address=ip_address
        )

        return {"status": "success", "message": "用户信息已更新"}
    except Exception as e: return {"status": "error", "message": safe_error_message(e)}

@router.post("/api/manage/user/new")
def api_manage_user_new(data: NewUserModelEx, request: Request):
    # 🔒 安全检查：必须管理员
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    # 🔒 Emby 不可用时拒绝创建
    if not media_api.health_check():
        return {"status": "error", "message": "Emby 服务不可用，请稍后重试"}
    # 🔥 清除用户缓存
    user_service.invalidate_emby_users_cache()
    try:
        res = media_api.post("/Users/New", json={"Name": data.name})
        if res.status_code != 200: return {"status": "error", "message": f"创建失败: {res.text}"}
        new_id = res.json()['Id']

        if data.password: media_api.post(f"/Users/{new_id}/Password", json={"Id": new_id, "NewPw": data.password})

        p = media_api.get(f"/Users/{new_id}").json().get('Policy', {})

        tpl_id = data.template_user_id or get_default_user_template_id()
        if tpl_id:
            src_res = media_api.get(f"/Users/{tpl_id}", timeout=5)
            if src_res.status_code == 200:
                src = src_res.json().get('Policy', {})
                p = clone_policy(p, src, data.copy_library, data.copy_policy, data.copy_parental)
        else:
            for k in ['BlockedMediaFolders','BlockedChannels','EnableAllChannels','EnabledChannels']: p.pop(k, None)

        media_api.post(f"/Users/{new_id}/Policy", json=p)

        v_exp = data.expire_date if data.expire_date else None
        v_max = data.max_concurrent
        v_vip = 1 if data.is_vip else 0
        v_remark = data.remark if data.remark else ""
        v_allow_routes = data.allow_routes if data.allow_routes else ""
        v_block_routes = data.block_routes if data.block_routes else ""
        v_req_free = data.req_free if data.req_free else 0
        v_req_free_count = data.req_free_count if data.req_free_count is not None else -1
        user_dao.create_user_meta(
            new_id,
            v_exp,
            v_max,
            v_vip,
            v_remark,
            v_allow_routes,
            v_block_routes,
            v_req_free,
            v_req_free_count,
            datetime.datetime.now().isoformat(),
        )

        # 记录审计日志
        admin_user = request.session.get("user", {})
        admin_name = admin_user.get("name", "未知")
        ip_address = get_client_ip(request)
        add_audit_log(
            admin_id=admin_user.get("id", ""),
            admin_name=admin_name,
            action="创建用户",
            target_user_id=new_id,
            target_user_name=data.name,
            ip_address=ip_address
        )

        return {"status": "success", "message": "用户创建成功"}
    except Exception as e: return {"status": "error", "message": safe_error_message(e)}

class DeleteWithPasswordModel(BaseModel):
    password: Optional[str] = None  # 批量删除必须传密码

@router.delete("/api/manage/user/{user_id}")
def api_manage_user_delete(user_id: str, request: Request):
    """删除单个用户 - 需要密码验证(首次验证后 30 分钟内有效,重启后失效)"""
    if not request.session.get("user"):
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    # 🔒 Emby 不可用时拒绝删除，避免本地标记与远端失步
    if not media_api.health_check():
        return {"status": "error", "message": "Emby 服务不可用，请稍后重试"}

    # 🔥 清除用户缓存
    user_service.invalidate_emby_users_cache()

    # 检查是否已验证
    verified = request.session.get("delete_verified", False)
    verified_time = request.session.get("delete_verified_time", "")

    # 验证有效期检查(30分钟 + 重启后失效)
    if verified and verified_time:
        try:
            verify_dt = datetime.datetime.fromisoformat(verified_time)
            # 超过30分钟
            if datetime.datetime.now() - verify_dt > datetime.timedelta(minutes=30):
                verified = False
                request.session["delete_verified"] = False
            # 验证时间在容器启动之前(重启后失效)
            elif verify_dt < datetime.datetime.fromisoformat(APP_START_TIME):
                verified = False
                request.session["delete_verified"] = False
        except:
            verified = False

    if not verified:
        return {"status": "error", "message": "需要验证密码", "need_password": True}

    # 获取当前管理员账号
    admin_user = request.session.get("user", {})
    admin_name = admin_user.get("name", admin_user.get("username", "未知管理员"))

    try:
        # 获取用户名用于日志
        user_name = ""
        try:
            user_res = media_api.get(f"/Users/{user_id}", timeout=5)
            if user_res.status_code == 200:
                user_name = user_res.json().get("Name", "")
        except:
            pass

        if media_api.delete(f"/Users/{user_id}").status_code in [200, 204]:
            user_dao.delete_user_meta(user_id)
            # 同步删除临时账号记录
            try:
                user_dao.delete_temp_account_by_emby_user(user_id)
            except:
                pass

            # 🔥 发送用户删除通知
            try:
                from app.infra.db.notification_dao import add_system_notification
                from app.domains.notifications import public_service as notification_service

                rule = notify_admin.get_notify_rule('user_delete')
                if rule and rule.get('enabled'):
                    channels = rule.get('channels', [])
                    msg = f"🗑️ <b>用户删除通知</b>\n\n👤 <b>用户:</b>{user_name}\n👮 <b>操作人:</b>{admin_name}\n🕒 <b>时间:</b>{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

                    # TG机器人/企业微信
                    if 'tg_bot' in channels or 'wecom' in channels:
                        platform = "all" if ('tg_bot' in channels and 'wecom' in channels) else ("tg" if 'tg_bot' in channels else "wecom")
                        notification_service.send_message("sys_notify", msg, platform=platform)

                    # Web通知中心
                    if 'web' in channels:
                        add_system_notification("user", f"用户删除: {user_name}", f"操作人: {admin_name}", "/users_manage")
            except Exception as e:
                pass

            # 记录审计日志
            ip_address = get_client_ip(request)
            add_audit_log(
                admin_id=admin_user.get("id", ""),
                admin_name=admin_name,
                action="删除用户",
                target_user_id=user_id,
                target_user_name=user_name,
                details="单个删除",
                ip_address=ip_address
            )
            return {"status": "success", "message": f"用户 {user_name} 已删除"}
        return {"status": "error", "message": "Emby 删除失败"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

@router.post("/api/manage/users/batch")
def api_manage_users_batch(data: BatchActionModelLocal, request: Request):
    if not request.session.get("user"): return {"status": "error"}
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    if len(data.user_ids) > 100:
        return {"status": "error", "message": "单次批量操作最多 100 个用户"}
    # 🔒 Emby 不可用时拒绝批量操作（一次校验，避免循环中放大请求）
    if not media_api.health_check():
        return {"status": "error", "message": "Emby 服务不可用，请稍后重试"}

    # 获取当前管理员账号
    admin_user = request.session.get("user", {})
    admin_name = admin_user.get("name", admin_user.get("username", "未知管理员"))

    try:
        # 批量删除需要账号和密码验证
        if data.action == "delete":
            if not data.username or not data.password:
                return {"status": "error", "message": "批量删除需要验证管理员账号和密码", "need_password": True}
            if not verify_emby_admin_password(data.username, data.password):
                return {"status": "error", "message": "账号或密码错误"}

        src_policy = {}; src_max_concurrent = None; src_is_vip = 0
        if data.action == "apply_template" and data.value:
            src_res = media_api.get(f"/Users/{data.value}", timeout=5)
            if src_res.status_code == 200:
                src_policy = src_res.json().get('Policy', {})
                t_meta = user_dao.get_user_policy_meta(data.value)
                src_max_concurrent = t_meta['max_concurrent'] if t_meta else None
                src_is_vip = t_meta['is_vip'] if t_meta and t_meta['is_vip'] else 0
            else:
                return {"status": "error", "message": "无法获取模板配置"}

        deleted_count = 0
        deleted_names = []
        # 其他操作的用户名列表
        operated_names = []

        for uid in data.user_ids:
            if data.action == "delete":
                # 获取用户名用于日志
                user_name = ""
                try:
                    user_res = media_api.get(f"/Users/{uid}", timeout=5)
                    if user_res.status_code == 200:
                        user_name = user_res.json().get("Name", "")
                except:
                    pass

                media_api.delete(f"/Users/{uid}")
                user_dao.delete_user_meta(uid)
                # 同步删除临时账号记录
                try:
                    user_dao.delete_temp_account_by_emby_user(uid)
                except:
                    pass
                deleted_count += 1
                if user_name:
                    deleted_names.append(user_name)
            elif data.action in ["enable", "disable"]:
                p_res = media_api.get(f"/Users/{uid}", timeout=5)
                if p_res.status_code == 200:
                    user_data = p_res.json()
                    user_name = user_data.get("Name", "")
                    if user_name:
                        operated_names.append(user_name)
                    p = user_data.get('Policy', {})
                    p['IsDisabled'] = (data.action == "disable")
                    if data.action == "enable": p['LoginAttemptsBeforeLockout'] = -1
                    media_api.post(f"/Users/{uid}/Policy", json=p)
                    # 设置 admin_disabled 标记
                    try:
                        user_dao.save_user_admin_disabled(uid, data.action == "disable", datetime.datetime.now().isoformat())
                    except Exception: pass
            elif data.action == "renew":
                # 获取用户名
                try:
                    user_res = media_api.get(f"/Users/{uid}", timeout=5)
                    if user_res.status_code == 200:
                        user_name = user_res.json().get("Name", "")
                        if user_name:
                            operated_names.append(user_name)
                except Exception: pass

                new_date = None
                if data.value.startswith('+'):
                    days_to_add = int(data.value[1:])
                    row = user_dao.get_user_meta(uid)
                    current_expire = row['expire_date'] if row and row['expire_date'] else None
                    if current_expire:
                        try:
                            base_date = datetime.datetime.strptime(current_expire, "%Y-%m-%d")
                            if base_date < datetime.datetime.now(): base_date = datetime.datetime.now()
                        except: base_date = datetime.datetime.now()
                    else: base_date = datetime.datetime.now()
                    new_date = (base_date + datetime.timedelta(days=days_to_add)).strftime("%Y-%m-%d")
                else: new_date = data.value if data.value else None

                user_dao.save_user_expire_preserve(uid, new_date, datetime.datetime.now().isoformat())
            elif data.action == "apply_template":
                p_res = media_api.get(f"/Users/{uid}", timeout=5)
                if p_res.status_code == 200:
                    user_data = p_res.json()
                    user_name = user_data.get("Name", "")
                    if user_name:
                        operated_names.append(user_name)
                    p = user_data.get('Policy', {})
                    p = clone_policy(p, src_policy, data.copy_library, data.copy_policy, data.copy_parental)

                    if data.copy_policy:
                        user_dao.save_user_policy_meta(uid, src_max_concurrent, src_is_vip, datetime.datetime.now().isoformat())

                    media_api.post(f"/Users/{uid}/Policy", json=p)
            elif data.action == "set_routes":
                # 批量设置用户线路权限
                allow_routes = data.allow_routes if data.allow_routes else ""
                block_routes = data.block_routes if data.block_routes else ""

                # 获取用户名
                try:
                    user_res = media_api.get(f"/Users/{uid}", timeout=5)
                    if user_res.status_code == 200:
                        user_name = user_res.json().get("Name", "")
                        if user_name:
                            operated_names.append(user_name)
                except Exception: pass

                user_dao.save_user_routes_preserve(uid, allow_routes, block_routes, datetime.datetime.now().isoformat())
            elif data.action == "set_req_free":
                # 批量设置求片权限
                req_free = data.req_free if data.req_free is not None else 0
                req_free_count = data.req_free_count if data.req_free_count is not None else -1

                # 获取用户名
                try:
                    user_res = media_api.get(f"/Users/{uid}", timeout=5)
                    if user_res.status_code == 200:
                        user_name = user_res.json().get("Name", "")
                        if user_name:
                            operated_names.append(user_name)
                except Exception: pass

                user_dao.save_user_req_permission(uid, req_free, req_free_count, datetime.datetime.now().isoformat())

        # 记录审计日志
        ip_address = get_client_ip(request)
        # 格式化用户名列表(最多显示10个)
        names_str = ', '.join(operated_names[:10]) + ('...' if len(operated_names) > 10 else '') if operated_names else ''

        if data.action == "delete" and deleted_count > 0:
            add_audit_log(
                admin_id=admin_user.get("id", ""),
                admin_name=admin_name,
                action="批量删除",
                target_count=deleted_count,
                details=f"删除用户: {', '.join(deleted_names[:10])}{'...' if len(deleted_names) > 10 else ''}",
                ip_address=ip_address
            )
        elif data.action == "enable":
            add_audit_log(
                admin_id=admin_user.get("id", ""),
                admin_name=admin_name,
                action="批量启用",
                target_count=len(data.user_ids),
                details=f"启用用户: {names_str or f'{len(data.user_ids)} 个'}",
                ip_address=ip_address
            )
        elif data.action == "disable":
            add_audit_log(
                admin_id=admin_user.get("id", ""),
                admin_name=admin_name,
                action="批量禁用",
                target_count=len(data.user_ids),
                details=f"禁用用户: {names_str or f'{len(data.user_ids)} 个'}",
                ip_address=ip_address
            )
        elif data.action == "apply_template":
            add_audit_log(
                admin_id=admin_user.get("id", ""),
                admin_name=admin_name,
                action="批量应用模板",
                target_count=len(data.user_ids),
                details=f"模板: {data.value}, 用户: {names_str or f'{len(data.user_ids)} 个'}",
                ip_address=ip_address
            )
        elif data.action == "renew":
            add_audit_log(
                admin_id=admin_user.get("id", ""),
                admin_name=admin_name,
                action="批量续期",
                target_count=len(data.user_ids),
                details=f"续期: {data.value}, 用户: {names_str or f'{len(data.user_ids)} 个'}",
                ip_address=ip_address
            )
        elif data.action == "set_routes":
            add_audit_log(
                admin_id=admin_user.get("id", ""),
                admin_name=admin_name,
                action="批量设置线路",
                target_count=len(data.user_ids),
                details=f"允许: {data.allow_routes or '无'}, 屏蔽: {data.block_routes or '无'}, 用户: {names_str or f'{len(data.user_ids)} 个'}",
                ip_address=ip_address
            )
        elif data.action == "set_req_free":
            req_mode = "免费求片" if data.req_free == 1 else "跟随全局"
            req_count_str = "无限次" if data.req_free_count == -1 else f"{data.req_free_count}次"
            add_audit_log(
                admin_id=admin_user.get("id", ""),
                admin_name=admin_name,
                action="批量设置求片权限",
                target_count=len(data.user_ids),
                details=f"模式: {req_mode}, 次数: {req_count_str}, 用户: {names_str or f'{len(data.user_ids)} 个'}",
                ip_address=ip_address
            )

        return {"status": "success", "message": f"成功操作了 {len(data.user_ids)} 个用户"}
    except Exception as e: return {"status": "error", "message": safe_error_message(e)}

router.include_router(template_router)

# ==================== 置顶用户功能 ====================

class PinUserModel(BaseModel):
    user_id: str
    pinned: bool


@router.post("/api/manage/user/pin")
def api_pin_user(data: PinUserModel, request: Request):
    """置顶/取消置顶用户"""
    if not request.session.get("user"):
        return {"status": "error", "message": "未登录"}

    user = request.session.get("user", {})
    if user.get("auth_type") != "emby" and user.get("role") != "admin":
        return {"status": "error", "message": "需要管理员权限"}

    try:
        user_dao.set_user_pinned(data.user_id, data.pinned, datetime.datetime.now().isoformat())

        action = "置顶用户" if data.pinned else "取消置顶"
        add_audit_log(
            admin_id=user.get("id", ""),
            admin_name=user.get("name", "管理员"),
            action=action,
            target_user_id=data.user_id,
            ip_address=get_client_ip(request)
        )

        return {"status": "success", "message": f"已{'置顶' if data.pinned else '取消置顶'}用户"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

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

# 审计日志页面路由已移除,改为用户管理页面弹窗

router.include_router(request_permission_router)
router.include_router(tag_router)
