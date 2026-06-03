import re
from fastapi import APIRouter, Request
from app.domains.media_requests import community_cache_service
from app.domains.media_requests.auth_router import (
    RequestLoginModel,
    check_auth,
    request_system_login,
    request_system_logout,
    router as auth_router,
    set_dependency_providers as set_auth_dependency_providers,
)
from app.domains.media_requests.cache_control_router import (
    clear_community_cache_api,
    refresh_community_cache_api,
    router as cache_control_router,
    set_dependency_providers as set_cache_control_dependency_providers,
    start_community_cache_refresh_loop,
    start_media_request_services,
    stop_community_cache_refresh_loop,
)
from app.domains.media_requests.discovery_router import (
    check_emby_exists,
    check_local_status,
    get_emby_admin,
    get_hub_data,
    get_item_info,
    get_tmdb_season_info,
    get_tmdb_trending,
    get_tv_details,
    router as discovery_router,
    search_tmdb,
    set_dependency_providers as set_discovery_dependency_providers,
)
from app.domains.media_requests.feedback_router import (
    BulkFeedbackActionModel,
    FeedbackActionModel,
    FeedbackSubmitModel,
    batch_feedback_action,
    get_all_feedback,
    get_my_feedback,
    manage_feedback_action,
    router as feedback_router,
    set_dependency_providers as set_feedback_dependency_providers,
    submit_feedback,
)
from app.domains.media_requests.management_router import (
    AdminActionModel,
    BulkAdminActionModel,
    batch_manage_action,
    get_all_requests,
    get_my_requests,
    get_pending_notify,
    manage_request_action,
    router as management_router,
    set_dependency_providers as set_management_dependency_providers,
)
from app.domains.media_requests.registration_router import (
    UserRegisterModel,
    _restore_invitation_code,
    router as registration_router,
    set_dependency_providers as set_registration_dependency_providers,
    user_community_register,
)
from app.domains.media_requests.safe_media_router import (
    get_safe_latest,
    get_safe_top_media,
    router as safe_media_router,
    set_dependency_providers as set_safe_media_dependency_providers,
)
from app.domains.media_requests.user_series_router import (
    _get_local_episodes,
    _get_tmdb_season_episodes,
    get_user_series,
    refresh_my_series_cache,
    router as user_series_router,
    set_dependency_providers as set_user_series_dependency_providers,
)
from app.domains.media_requests.update_router import (
    UpdateRequestModel,
    download_episodes_for_update,
    getRequestStatusTextSync,
    router as update_router,
    search_episodes_for_update,
    set_dependency_providers as set_update_dependency_providers,
    submit_update_request,
    submit_update_request_batch,
)
from app.domains.users import public_service as user_service
from app.core.security import validate_password_strength  # 🔒 统一密码强度校验
from typing import Optional, List

from app.core.config import REPORT_COVER_URL
from app.infra.clients.moviepilot_client import moviepilot_client
from app.infra.clients.tmdb_client import tmdb_client
from app.infra.config.request_portal_settings import get_pulse_url
from app.infra.db.notification_dao import add_system_notification
from app.domains.media_requests.media_request_dao import (
    claim_registration_invitation,
    create_media_feedback,
    decode_gap_cache,
    delete_media_request,
    ensure_media_request_schema,
    find_poster_for_feedback,
    get_media_request,
    get_pending_notify_data,
    get_update_cost_config,
    get_update_request_search_info,
    get_user_expire_date,
    get_user_password_hash,
    get_user_series_db_context,
    get_user_status_meta,
    list_all_feedback,
    list_all_requests,
    list_my_feedback,
    list_my_requests,
    list_request_status_notify_items,
    list_tg_bindings,
    restore_invitation_code,
    save_registered_user_meta,
    submit_batch_update_request_records,
    submit_new_media_request,
    submit_update_request_record,
    update_feedback_status,
    update_feedback_status_batch,
    update_media_request_status,
    update_user_password_hash,
)
from app.utils.proxy_helper import get_safe_proxies  # 🔒 SSRF 安全代理读取
# 🔥 补回丢失的这一行：引入基础数据模型
from app.schemas.models import MediaRequestSubmitModel as BaseSubmitModel
from app.domains.notifications import public_service as notification_service
from app.domains.notifications import notify_admin
from app.domains.playback import stats as playback_stats
# 🔥 引入媒体适配器用于创建用户
from app.infra.clients.media_server_client import media_api
from app.infra.config.media_server_settings import (
    get_media_server_main_public_url,
    get_media_server_main_public_or_host,
    get_media_server_user_routes,
    get_media_server_welcome_message,
)
from app.infra.config.moviepilot_settings import get_moviepilot_token, get_moviepilot_url
import logging
from app.core.security_utils import safe_error_message

logger = logging.getLogger("uvicorn")

router = APIRouter()

# ==================== 用户社区首页缓存 ====================
# Compatibility exports for existing router callers, tests, and diagnostics.
_community_cache = community_cache_service._community_cache
_community_cache_lock = community_cache_service._community_cache_lock
_community_refresh_started = False
_community_refresh_thread = None

COMMUNITY_CACHE_TTL = community_cache_service.COMMUNITY_CACHE_TTL
COMMUNITY_CACHE_TTL_HUB = community_cache_service.COMMUNITY_CACHE_TTL_HUB
COMMUNITY_CACHE_TTL_TOP = community_cache_service.COMMUNITY_CACHE_TTL_TOP
COMMUNITY_CACHE_TTL_LATEST = community_cache_service.COMMUNITY_CACHE_TTL_LATEST

_get_cache = community_cache_service._get_cache
_set_cache = community_cache_service._set_cache
_invalidate_cache = community_cache_service._invalidate_cache


def _sync_community_cache_task_state() -> None:
    global _community_refresh_started, _community_refresh_thread
    _community_refresh_started = community_cache_service._community_refresh_started
    _community_refresh_thread = community_cache_service._community_refresh_thread


def _refresh_community_cache():
    return community_cache_service._refresh_community_cache(admin_resolver=get_emby_admin)

def _check_user_exists(user_id: str) -> bool:
    """检查 Emby 用户是否仍然存在"""
    if not user_id:
        return False
    try:
        from app.infra.clients.media_server_client import media_api
        if media_api and media_api.host and media_api.api_key:
            res = media_api.get(f"/Users/{user_id}", timeout=5)
            return res.status_code == 200
    except:
        pass
    return True  # 网络异常时不误判，允许继续操作


set_auth_dependency_providers(
    media_api_provider=lambda: media_api,
    main_server_url_provider=lambda: get_media_server_main_public_or_host,
    user_routes_provider=lambda: get_media_server_user_routes,
    user_status_meta_provider=lambda: get_user_status_meta,
    user_password_hash_provider=lambda: get_user_password_hash,
    update_user_password_hash_provider=lambda: update_user_password_hash,
    user_expire_date_provider=lambda: get_user_expire_date,
    check_user_exists_provider=lambda: _check_user_exists,
)


set_feedback_dependency_providers(
    user_service_provider=lambda: user_service,
    media_api_provider=lambda: media_api,
    check_user_exists_provider=lambda: _check_user_exists,
    pulse_url_provider=lambda: get_pulse_url,
    report_cover_url_provider=lambda: REPORT_COVER_URL,
    find_poster_for_feedback_provider=lambda: find_poster_for_feedback,
    create_media_feedback_provider=lambda: create_media_feedback,
    list_my_feedback_provider=lambda: list_my_feedback,
    list_all_feedback_provider=lambda: list_all_feedback,
    update_feedback_status_provider=lambda: update_feedback_status,
    update_feedback_status_batch_provider=lambda: update_feedback_status_batch,
    notify_admin_provider=lambda: notify_admin,
    notification_service_provider=lambda: notification_service,
    system_notification_provider=lambda: add_system_notification,
    logger_provider=lambda: logger,
)


set_discovery_dependency_providers(
    user_service_provider=lambda: user_service,
    media_api_provider=lambda: media_api,
    tmdb_client_provider=lambda: tmdb_client,
    check_user_exists_provider=lambda: _check_user_exists,
    get_emby_admin_provider=lambda: get_emby_admin,
    check_emby_exists_provider=lambda: check_emby_exists,
    get_cache_provider=lambda: _get_cache,
    set_cache_provider=lambda: _set_cache,
    cache_ttl_hub_provider=lambda: COMMUNITY_CACHE_TTL_HUB,
    main_server_url_provider=lambda: get_media_server_main_public_or_host,
    safe_proxies_provider=lambda: get_safe_proxies,
    safe_error_message_provider=lambda: safe_error_message,
    logger_provider=lambda: logger,
)


set_management_dependency_providers(
    user_service_provider=lambda: user_service,
    list_my_requests_provider=lambda: list_my_requests,
    list_all_requests_provider=lambda: list_all_requests,
    tmdb_client_provider=lambda: tmdb_client,
    safe_proxies_provider=lambda: get_safe_proxies,
    get_media_request_provider=lambda: get_media_request,
    moviepilot_url_provider=lambda: get_moviepilot_url,
    moviepilot_token_provider=lambda: get_moviepilot_token,
    moviepilot_client_provider=lambda: moviepilot_client,
    update_media_request_status_provider=lambda: update_media_request_status,
    delete_media_request_provider=lambda: delete_media_request,
    notify_admin_provider=lambda: notify_admin,
    list_request_status_notify_items_provider=lambda: list_request_status_notify_items,
    list_tg_bindings_provider=lambda: list_tg_bindings,
    notification_service_provider=lambda: notification_service,
    get_pending_notify_data_provider=lambda: get_pending_notify_data,
    safe_error_message_provider=lambda: safe_error_message,
    logger_provider=lambda: logger,
    batch_manage_action_provider=lambda: batch_manage_action,
)


set_registration_dependency_providers(
    validate_password_strength_provider=lambda: validate_password_strength,
    media_api_provider=lambda: media_api,
    claim_registration_invitation_provider=lambda: claim_registration_invitation,
    restore_invitation_code_provider=lambda: restore_invitation_code,
    save_registered_user_meta_provider=lambda: save_registered_user_meta,
    user_service_provider=lambda: user_service,
    notify_admin_provider=lambda: notify_admin,
    notification_service_provider=lambda: notification_service,
    user_routes_provider=lambda: get_media_server_user_routes,
    main_server_url_provider=lambda: get_media_server_main_public_or_host,
    welcome_message_provider=lambda: get_media_server_welcome_message,
    safe_error_message_provider=lambda: safe_error_message,
    logger_provider=lambda: logger,
)


set_safe_media_dependency_providers(
    media_api_provider=lambda: media_api,
    playback_stats_provider=lambda: playback_stats,
    logger_provider=lambda: logger,
    check_user_exists_provider=lambda: _check_user_exists,
    get_cache_provider=lambda: _get_cache,
    set_cache_provider=lambda: _set_cache,
    cache_ttl_top_provider=lambda: COMMUNITY_CACHE_TTL_TOP,
    cache_ttl_latest_provider=lambda: COMMUNITY_CACHE_TTL_LATEST,
    safe_error_message_provider=lambda: safe_error_message,
)


set_cache_control_dependency_providers(
    community_cache_service_provider=lambda: community_cache_service,
    refresh_community_cache_provider=lambda: _refresh_community_cache,
    invalidate_cache_provider=lambda: _invalidate_cache,
    sync_task_state_provider=lambda: _sync_community_cache_task_state,
    ensure_schema_provider=lambda: ensure_media_request_schema,
    user_service_provider=lambda: user_service,
)


set_user_series_dependency_providers(
    media_api_provider=lambda: media_api,
    get_emby_admin_provider=lambda: get_emby_admin,
    tmdb_client_provider=lambda: tmdb_client,
    safe_proxies_provider=lambda: get_safe_proxies,
    get_user_series_db_context_provider=lambda: get_user_series_db_context,
    decode_gap_cache_provider=lambda: decode_gap_cache,
    get_update_cost_config_provider=lambda: get_update_cost_config,
    safe_error_message_provider=lambda: safe_error_message,
)


set_update_dependency_providers(
    user_service_provider=lambda: user_service,
    check_user_exists_provider=lambda: _check_user_exists,
    get_tmdb_season_info_provider=lambda: get_tmdb_season_info,
    submit_update_request_record_provider=lambda: submit_update_request_record,
    submit_batch_update_request_records_provider=lambda: submit_batch_update_request_records,
    safe_proxies_provider=lambda: get_safe_proxies,
    tmdb_client_provider=lambda: tmdb_client,
    system_notification_provider=lambda: add_system_notification,
    notification_service_provider=lambda: notification_service,
    pulse_url_provider=lambda: get_pulse_url,
    media_server_public_url_provider=lambda: get_media_server_main_public_url,
    report_cover_url_provider=lambda: REPORT_COVER_URL,
    get_update_request_search_info_provider=lambda: get_update_request_search_info,
    update_media_request_status_provider=lambda: update_media_request_status,
    safe_error_message_provider=lambda: safe_error_message,
)


class MediaRequestSubmitModel(BaseSubmitModel):
    seasons: List[int] = [0] 
    overview: Optional[str] = ""

router.include_router(auth_router)

router.include_router(discovery_router)

@router.post("/api/requests/submit")
async def submit_media_request(request: Request):
    user = request.session.get("req_user")
    if not user: return {"status": "error", "message": "请先绑定 Emby 账号"}
    
    # 检查 Emby 账号是否仍然存在
    if not _check_user_exists(user.get("Id")):
        request.session.pop("req_user", None)
        return {"status": "error", "message": "账号已被删除，请重新登录", "account_deleted": True}
    
    uid = user['Id']
    uname = user['Name']

    try:
        data = await request.json()
        tmdb_id = int(data.get("tmdb_id") or 0)
        # 兼容前端发 seasons(数组) 或 season(单数)
        seasons_raw = data.get("seasons")
        if seasons_raw is None:
            seasons_raw = [data.get("season")] if data.get("season") is not None else []
        # 过滤掉无效季数（0或负数）
        seasons = [int(s) for s in seasons_raw if int(s) > 0] if isinstance(seasons_raw, list) else ([int(seasons_raw)] if int(seasons_raw) > 0 else [])
        media_type = data.get("media_type")
        
        # 🔒 XSS 防护：过滤 title 中的危险字符
        title_raw = data.get("title", "")
        title = re.sub(r'<[^>]*>', '', title_raw)  # 移除 HTML 标签
        title = title[:200]  # 限制长度
        
        year = data.get("year")
        
        # 🔒 XSS 防护：过滤 poster_path
        poster_path_raw = data.get("poster_path", "")
        poster_path = poster_path_raw[:500] if poster_path_raw else ""

        # 验证季数
        if media_type == "tv" and not seasons:
            return {"status": "error", "message": "请选择有效的季数"}

        # 电影没有季数概念，设置为0以便插入数据库
        if media_type == "movie" and not seasons:
            seasons = [0]

        result = submit_new_media_request(uid, uname, tmdb_id, media_type, title, year, poster_path, seasons)
        if not result.get("ok"):
            return {"status": "error", "message": result.get("message", "提交失败")}

        try:
            season_str = f" 第 {','.join(str(s) for s in seasons)} 季" if media_type == "tv" and any(s > 0 for s in seasons) else ""
            msg = f"🎬 <b>收到新求片心愿</b>\n\n👤 <b>用户：</b>{uname}\n📺 <b>内容：</b>{title} ({year}){season_str}\n\n请及时前往后台审批处理。"
            
            admin_url = get_pulse_url() or get_media_server_main_public_url() or "http://127.0.0.1:10307"
            # 构建季数字符串用于回调（多季用逗号分隔）
            season_str_cb = ",".join(str(s) for s in seasons) if media_type == "tv" and any(s > 0 for s in seasons) else "0"
            # 标题需要编码以便在 callback_data 中使用（替换下划线）
            title_safe = title.replace("_", "-")
            
            # 检查影巢插件是否启用
            hdhive_enabled = False
            try:
                from app.plugins import get_plugin
                hdhive_plugin = get_plugin("hdhive")
                hdhive_enabled = hdhive_plugin and hdhive_plugin.enabled
            except:
                pass
            
            # 构建按钮：影巢搜索按钮（如果插件启用）
            if hdhive_enabled:
                keyboard = {"inline_keyboard": [
                    [{"text": "🚀 推送 MP", "callback_data": f"req_approve_{tmdb_id}"}, {"text": "✋ 手动接单", "callback_data": f"req_manual_{tmdb_id}"}],
                    [{"text": "🔍 影巢搜索", "callback_data": f"req_hdhive_{tmdb_id}_{media_type}_{season_str_cb}_{title_safe}"}, {"text": "❌ 拒绝求片", "callback_data": f"req_reject_menu_{tmdb_id}"}],
                    [{"text": "💻 网页审批", "url": f"{admin_url.rstrip('/')}/requests_admin"}]
                ]}
            else:
                keyboard = {"inline_keyboard": [
                    [{"text": "🚀 推送 MP", "callback_data": f"req_approve_{tmdb_id}"}, {"text": "✋ 手动接单", "callback_data": f"req_manual_{tmdb_id}"}],
                    [{"text": "❌ 拒绝求片", "callback_data": f"req_reject_menu_{tmdb_id}"}, {"text": "💻 网页审批", "url": f"{admin_url.rstrip('/')}/requests_admin"}]
                ]}
            
            # 🔥 使用 notify_rules 配置控制通知渠道
            rule = notify_admin.get_notify_rule('request_new')
            if rule and rule.get('enabled'):
                channels = rule.get('channels', [])
                platform = "none"
                if 'tg_bot' in channels and 'wecom' in channels:
                    platform = "all"
                elif 'tg_bot' in channels:
                    platform = "tg"
                elif 'wecom' in channels:
                    platform = "wecom"
                
                if platform != "none":
                    notification_service.send_photo("sys_notify", f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else REPORT_COVER_URL, msg, reply_markup=keyboard, platform=platform)
                
                # Web 通知中心 - 只有勾选 web 才发送
                if 'web' in channels:
                    add_system_notification("request", f"收到新求片: {title}", f"用户 {uname} 提交了新的心愿单", "/requests_admin")
            # else: 关闭状态不发送任何通知
        except Exception as e:
            logger.error(f"[求片通知] 发送失败: {e}")

        return {"status": "success", "message": "心愿已提交！系统将尽快处理您的请求。"}
        
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e, "提交失败")}

router.include_router(management_router)

router.include_router(feedback_router)

router.include_router(safe_media_router)


router.include_router(cache_control_router)

router.include_router(user_series_router)

router.include_router(update_router)

router.include_router(registration_router)
