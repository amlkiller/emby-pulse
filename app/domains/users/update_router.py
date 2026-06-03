import datetime
from typing import List, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.rate_limiter import get_client_ip
from app.core.security_utils import safe_error_message
from app.domains.users import public_service as user_service
from app.domains.users import user_dao
from app.domains.users.auth import is_admin_user
from app.infra.clients.media_server_client import media_api


router = APIRouter()


def _noop_audit_log(**_kwargs):
    return None


DANGEROUS_POLICY_KEYS = {'IsAdministrator', 'IsDisabled', 'LoginAttemptsBeforeLockout'}
LIBRARY_POLICY_KEYS = {'EnableAllFolders', 'EnabledFolders', 'ExcludedSubFolders', 'BlockedMediaFolders', 'BlockedChannels', 'EnableAllChannels', 'EnabledChannels'}
PARENTAL_POLICY_KEYS = {'MaxParentalRating', 'BlockUnratedItems', 'BlockedTags', 'AllowedTags'}


def _clone_policy(target_policy: dict, src_policy: dict, copy_lib: bool, copy_pol: bool, copy_par: bool):
    for k, v in src_policy.items():
        if k in DANGEROUS_POLICY_KEYS:
            continue
        is_lib = k in LIBRARY_POLICY_KEYS
        is_par = k in PARENTAL_POLICY_KEYS
        is_pol = not is_lib and not is_par

        if (copy_lib and is_lib) or (copy_par and is_par) or (copy_pol and is_pol):
            target_policy[k] = v
    return target_policy


_media_api_provider = lambda: media_api
_user_dao_provider = lambda: user_dao
_user_service_provider = lambda: user_service
_is_admin_user_provider = lambda: is_admin_user
_clone_policy_provider = lambda: _clone_policy
_safe_error_message_provider = lambda: safe_error_message
_client_ip_provider = lambda: get_client_ip
_audit_log_provider = lambda: _noop_audit_log
_datetime_provider = lambda: datetime


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


def set_dependency_providers(
    *,
    media_api_provider=None,
    user_dao_provider=None,
    user_service_provider=None,
    is_admin_user_provider=None,
    clone_policy_provider=None,
    safe_error_message_provider=None,
    client_ip_provider=None,
    audit_log_provider=None,
    datetime_provider=None,
):
    global _media_api_provider
    global _user_dao_provider
    global _user_service_provider
    global _is_admin_user_provider
    global _clone_policy_provider
    global _safe_error_message_provider
    global _client_ip_provider
    global _audit_log_provider
    global _datetime_provider

    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if user_dao_provider is not None:
        _user_dao_provider = user_dao_provider
    if user_service_provider is not None:
        _user_service_provider = user_service_provider
    if is_admin_user_provider is not None:
        _is_admin_user_provider = is_admin_user_provider
    if clone_policy_provider is not None:
        _clone_policy_provider = clone_policy_provider
    if safe_error_message_provider is not None:
        _safe_error_message_provider = safe_error_message_provider
    if client_ip_provider is not None:
        _client_ip_provider = client_ip_provider
    if audit_log_provider is not None:
        _audit_log_provider = audit_log_provider
    if datetime_provider is not None:
        _datetime_provider = datetime_provider


@router.post("/api/manage/user/update")
def api_manage_user_update(data: UserUpdateModelEx, request: Request):
    # 🔒 安全检查：必须管理员
    if not _is_admin_user_provider()(request): return {"status": "error", "message": "需要管理员权限"}
    # 🔒 Emby 不可用时拒绝
    if not _media_api_provider().health_check():
        return {"status": "error", "message": "Emby 服务不可用，请稍后重试"}
    # 🔥 清除用户缓存
    _user_service_provider().invalidate_emby_users_cache()
    try:
        media = _media_api_provider()
        dao = _user_dao_provider()
        dt = _datetime_provider()

        exist = dao.get_user_meta(data.user_id)
        # 获取旧的 Emby Policy 用于对比变更
        old_policy = {}
        old_user_res = media.get(f"/Users/{data.user_id}", timeout=5)
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

        dao.save_manage_user_meta(
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
            dt.datetime.now().isoformat(),
        )

        if data.password:
            media.post(f"/Users/{data.user_id}/Password", json={"Id": data.user_id, "NewPw": data.password})

        p_res = media.get(f"/Users/{data.user_id}")
        if p_res.status_code == 200:
            p = p_res.json().get('Policy', {})

            if data.apply_template_id:
                src_res = media.get(f"/Users/{data.apply_template_id}", timeout=5)
                if src_res.status_code == 200:
                    src_policy = src_res.json().get('Policy', {})
                    p = _clone_policy_provider()(p, src_policy, data.copy_library, data.copy_policy, data.copy_parental)
                    # 🔥 应用模板时同步更新 admin_enabled_folders，但保留用户的 hidden_libraries
                    if data.copy_library:
                        try:
                            final_enabled = dao.sync_user_library_permissions(
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
                    dao.set_user_admin_disabled(data.user_id, data.is_disabled)
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
                        final_enabled = dao.sync_user_library_permissions(data.user_id, new_enable_all, new_enabled_folders)
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

            media.post(f"/Users/{data.user_id}/Policy", json=p)

        # 记录审计日志
        admin_user = request.session.get("user", {})
        admin_name = admin_user.get("name", "未知")
        ip_address = _client_ip_provider()(request)
        # 获取目标用户名
        target_name = ""
        try:
            u_res = media.get(f"/Users/{data.user_id}", timeout=5)
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
        _audit_log_provider()(
            admin_id=admin_user.get("id", ""),
            admin_name=admin_name,
            action="修改用户",
            target_user_id=data.user_id,
            target_user_name=target_name,
            details=details,
            ip_address=ip_address
        )

        return {"status": "success", "message": "用户信息已更新"}
    except Exception as e: return {"status": "error", "message": _safe_error_message_provider()(e)}
