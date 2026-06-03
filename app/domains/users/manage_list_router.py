import datetime

from fastapi import APIRouter, Request

from app.core.security_utils import safe_error_message
from app.domains.users import public_service as user_service
from app.domains.users import user_bot_dao, user_dao
from app.domains.users.auth import is_admin_user
from app.infra.clients.media_server_client import media_api
from app.infra.config.media_server_settings import get_media_server_public_host


router = APIRouter()

_media_api_provider = lambda: media_api
_user_dao_provider = lambda: user_dao
_user_bot_dao_provider = lambda: user_bot_dao
_user_service_provider = lambda: user_service
_is_admin_user_provider = lambda: is_admin_user
_public_host_provider = lambda: get_media_server_public_host()
_safe_error_message_provider = lambda: safe_error_message
_datetime_provider = lambda: datetime
_check_expired_users_provider = None


def set_dependency_providers(
    *,
    media_api_provider=None,
    user_dao_provider=None,
    user_bot_dao_provider=None,
    user_service_provider=None,
    is_admin_user_provider=None,
    public_host_provider=None,
    safe_error_message_provider=None,
    datetime_provider=None,
    check_expired_users_provider=None,
):
    global _media_api_provider
    global _user_dao_provider
    global _user_bot_dao_provider
    global _user_service_provider
    global _is_admin_user_provider
    global _public_host_provider
    global _safe_error_message_provider
    global _datetime_provider
    global _check_expired_users_provider

    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if user_dao_provider is not None:
        _user_dao_provider = user_dao_provider
    if user_bot_dao_provider is not None:
        _user_bot_dao_provider = user_bot_dao_provider
    if user_service_provider is not None:
        _user_service_provider = user_service_provider
    if is_admin_user_provider is not None:
        _is_admin_user_provider = is_admin_user_provider
    if public_host_provider is not None:
        _public_host_provider = public_host_provider
    if safe_error_message_provider is not None:
        _safe_error_message_provider = safe_error_message_provider
    if datetime_provider is not None:
        _datetime_provider = datetime_provider
    if check_expired_users_provider is not None:
        _check_expired_users_provider = check_expired_users_provider


def check_expired_users():
    """检查过期用户并自动禁用(标记为过期禁用,非管理员禁用)"""
    try:
        dao = _user_dao_provider()
        media = _media_api_provider()
        dt = _datetime_provider()

        rows = dao.list_users_with_expire_date_for_check()
        if not rows: return
        now_str = dt.datetime.now().strftime("%Y-%m-%d")
        for row in rows:
            if row['expire_date'] < now_str:
                uid = row['user_id']
                try:
                    u_res = media.get(f"/Users/{uid}", timeout=5)
                    if u_res.status_code == 200:
                        user = u_res.json()
                        policy = user.get('Policy', {})
                        if not policy.get('IsDisabled', False):
                            policy['IsDisabled'] = True
                            media.post(f"/Users/{uid}/Policy", json=policy)
                            # 标记为过期禁用(非管理员禁用)
                            try:
                                dao.set_user_admin_disabled(uid, False)
                            except Exception: pass
                except Exception as e: pass
    except Exception as e: pass


@router.get("/api/manage/users")
def api_manage_users(request: Request, refresh: bool = False):
    # 🔒 安全检查：必须管理员
    if not _is_admin_user_provider()(request): return {"status": "error", "message": "需要管理员权限"}

    if _check_expired_users_provider is None:
        check_expired_users()
    else:
        _check_expired_users_provider()()

    # 如果请求强制刷新,清除缓存
    service = _user_service_provider()
    if refresh:
        service.invalidate_emby_users_cache()

    public_host = _public_host_provider()
    if public_host.endswith('/'): public_host = public_host[:-1]

    try:
        # 🔥 使用缓存的用户列表
        emby_users = service.get_emby_users_cached()
        if emby_users is None:
            return {"status": "error", "message": "媒体服务器无法连接"}
        meta_rows = _user_dao_provider().list_all_user_meta()
        meta_map = {r['user_id']: dict(r) for r in meta_rows} if meta_rows else {}

        # 查询 TG 绑定关系 (emby_user_id -> tg_user_id)
        tg_bindings = {}
        try:
            rows = _user_bot_dao_provider().list_emby_tg_user_bindings()
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
    except Exception as e: return {"status": "error", "message": _safe_error_message_provider()(e)}
