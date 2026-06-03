from fastapi import APIRouter
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
from app.domains.media_requests.submit_router import (
    MediaRequestSubmitModel,
    router as submit_router,
    set_dependency_providers as set_submit_dependency_providers,
    submit_media_request,
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


set_submit_dependency_providers(
    check_user_exists_provider=lambda: _check_user_exists,
    submit_new_media_request_provider=lambda: submit_new_media_request,
    pulse_url_provider=lambda: get_pulse_url,
    media_server_public_url_provider=lambda: get_media_server_main_public_url,
    notify_admin_provider=lambda: notify_admin,
    notification_service_provider=lambda: notification_service,
    system_notification_provider=lambda: add_system_notification,
    report_cover_url_provider=lambda: REPORT_COVER_URL,
    safe_error_message_provider=lambda: safe_error_message,
    logger_provider=lambda: logger,
)

router.include_router(auth_router)

router.include_router(discovery_router)

router.include_router(submit_router)

router.include_router(management_router)

router.include_router(feedback_router)

router.include_router(safe_media_router)


router.include_router(cache_control_router)

router.include_router(user_series_router)

router.include_router(update_router)

router.include_router(registration_router)
