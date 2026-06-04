"""
EmbyPulse 用户 TG 机器人 (Pro 专属)
独立于管理员机器人，面向普通用户提供自助服务
"""
import threading
import time
import datetime
import secrets
import logging
import random
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from app.domains.media_requests import media_request_dao
from app.domains.points import point_dao
from app.domains.system import invitation_dao
from app.domains.users import user_dao
from app.domains.users import user_bot_dao
from app.bot.user_bot import user_bot_account_commands_service
from app.bot.user_bot import user_bot_basic_commands_service
from app.bot.user_bot import user_bot_binding_service
from app.bot.user_bot import user_bot_callback_dispatcher_service
from app.bot.user_bot import user_bot_channel_commands_service
from app.bot.user_bot import user_bot_code_commands_service
from app.bot.user_bot import user_bot_concurrency_service
from app.bot.user_bot import user_bot_dice_pk_commands_service
from app.bot.user_bot import user_bot_game_commands_service
from app.bot.user_bot import user_bot_lottery_draw_service
from app.bot.user_bot import user_bot_menu_service
from app.bot.user_bot import user_bot_message_cleanup_service
from app.bot.user_bot import user_bot_message_dispatcher_service
from app.bot.user_bot import user_bot_new_chat_member_service
from app.bot.user_bot import user_bot_open_registration_service
from app.bot.user_bot import user_bot_open_reg_notify_service
from app.bot.user_bot import user_bot_password_commands_service
from app.bot.user_bot import user_bot_pk_callback_service
from app.bot.user_bot import user_bot_pk_invitation_commands_service
from app.bot.user_bot import user_bot_polling_service
from app.bot.user_bot import user_bot_points_commands_service
from app.bot.user_bot import user_bot_points_game_commands_service
from app.bot.user_bot import user_bot_registration_queue_service
from app.bot.user_bot import user_bot_registration_quota_service
from app.bot.user_bot import user_bot_request_commands_service
from app.bot.user_bot import user_bot_restriction_service
from app.bot.user_bot import user_bot_scheduler_service
from app.bot.user_bot import user_bot_shop_commands_service
from app.bot.user_bot import user_bot_scratch_commands_service
from app.bot.user_bot import user_bot_service_info_commands_service
from app.bot.user_bot import user_bot_telegram_service
from app.bot.user_bot import user_bot_transfer_commands_service
from app.domains.playback import stats_queries
from app.utils.proxy_helper import get_safe_proxies  # 🔒 SSRF 安全代理读取
from app.infra.clients.media_server_client import media_api
from app.infra.clients.network_client import network_client
from app.infra.clients.telegram_client import telegram_client
from app.infra.config.user_bot_settings import (
    get_user_bot_allowed_groups,
    get_user_bot_allow_routes,
    get_user_bot_block_routes,
    get_user_bot_max_reg,
    get_user_bot_required_channels,
    get_user_bot_required_groups,
    is_user_bot_open_reg_enabled,
    is_user_bot_open_reg_notify_group_enabled,
    is_user_bot_open_reg_notify_user_enabled,
    set_user_bot_open_reg_enabled,
    set_user_bot_token,
    set_user_bot_allowed_groups,
    set_user_bot_allow_routes,
    set_user_bot_block_routes,
    set_user_bot_group_commands,
    set_user_bot_group_enabled,
    set_user_bot_open_reg_notify_group_enabled,
    set_user_bot_open_reg_notify_user_enabled,
    set_user_bot_portal_url,
    set_user_bot_reg_quota_mode,
    set_user_bot_registration_batch_used,
    set_user_bot_route_mode,
    set_user_bot_template_user,
    set_user_bot_welcome_msg,
    get_user_bot_portal_url,
    get_user_bot_reg_days,
    get_user_bot_reg_quota,
    get_user_bot_reg_quota_mode,
    get_user_bot_restriction_cache_ttl,
    get_user_bot_template_user,
    get_user_bot_token,
    get_user_bot_worker_count,
    get_user_bot_registration_batch_used,
    get_user_bot_group_commands,
    get_user_bot_group_enabled,
    get_user_bot_welcome_msg,
    is_user_bot_restriction_enabled,
)
from app.infra.config.media_server_settings import (
    get_media_server_main_public_url,
    get_media_server_user_routes,
)
from app.infra.config.notification_settings import get_tg_bot_token as get_notify_tg_bot_token
from app.infra.config.user_visibility_settings import get_hidden_users
from app.core.security import validate_password_strength  # 🔒 统一密码强度校验
from app.core.security_utils import safe_error_message  # 🔒 错误脱敏
from app.infra.clients.tmdb_client import tmdb_client

logger = logging.getLogger("uvicorn")

# 🔒 XSS 防护：HTML 转义函数（用于 Telegram 消息）
def escape_html(text):
    """转义 HTML 特殊字符，防止 XSS 攻击"""
    if not text:
        return ''
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

# 🚀 线程池：限制最大并发数，防止线程爆炸
MAX_CONCURRENT_TASKS = get_user_bot_worker_count()
_task_executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_TASKS, thread_name_prefix="userbot")
MAX_WAITING_TASKS = 200  # 最大等待任务数

# 频率限制：防刷
_rate_limit = defaultdict(float)  # tg_user_id -> last_action_time

# 🚀 绑定状态缓存（减少数据库查询）
_binding_cache = {}  # tg_user_id -> {"binding": dict, "cached_at": timestamp}
_BINDING_CACHE_TTL = 60  # 缓存60秒
_cache_lock = threading.Lock()  # 缓存锁

# 🚀 黑名单缓存
_blacklist_cache = {}  # tg_user_id -> {"blacklisted": bool, "cached_at": timestamp}
_BLACKLIST_CACHE_TTL = 300  # 缓存5分钟

# 🔥 使用限制检查缓存
_restriction_cache = {}  # tg_user_id -> {"passed": bool, "missing_channels": list, "missing_groups": list, "cached_at": timestamp}
_restriction_cache_lock = threading.Lock()

# 🚀 Emby 账号状态缓存
_emby_account_cache = {}  # user_id -> {"exists": bool, "cached_at": timestamp}
_EMBY_ACCOUNT_CACHE_TTL = 60  # 缓存60秒

# 🚀 用户名预占锁（防止并发注册时用户名冲突）
_username_locks = {}  # username_lower -> threading.Lock
_username_locks_lock = threading.Lock()  # 保护 _username_locks 字典
_USERNAME_LOCK_MAX_SIZE = 1000  # 最大锁数量，防止内存泄漏

# 🚀 注册并发控制（FIFO 排队 + 软预占）
MAX_CONCURRENT_REG = 20             # 实际并发上限：Emby /Users/New 同时处理量
REG_QUEUE_MAX_WAIT = 180            # 排队最长等待秒数，超时自动放弃
USER_COUNT_CACHE_TTL = 30           # Emby /Users 缓存秒数
USER_COUNT_NEAR_LIMIT_MARGIN = 3    # 临近 quota 时强制刷新缓存的安全边距
BATCH_FLUSH_INTERVAL = 10           # batch_used 落盘间隔（秒）
BATCH_FLUSH_THRESHOLD = 5           # 累计增量阈值触发落盘

user_bot_binding_service.set_dependency_providers(
    user_bot_dao_provider=lambda: user_bot_dao,
    media_api_provider=lambda: media_api,
    logger_provider=lambda: logger,
    time_provider=lambda: time,
    binding_cache_provider=lambda: _binding_cache,
    blacklist_cache_provider=lambda: _blacklist_cache,
    emby_account_cache_provider=lambda: _emby_account_cache,
    cache_lock_provider=lambda: _cache_lock,
    binding_cache_ttl_provider=lambda: _BINDING_CACHE_TTL,
    blacklist_cache_ttl_provider=lambda: _BLACKLIST_CACHE_TTL,
    emby_account_cache_ttl_provider=lambda: _EMBY_ACCOUNT_CACHE_TTL,
    get_binding_provider=lambda: user_bot_binding_service.get_binding,
)

user_bot_registration_quota_service.set_dependency_providers(
    media_api_provider=lambda: media_api,
    get_hidden_users_provider=lambda: get_hidden_users,
    get_registration_batch_used_provider=lambda: get_user_bot_registration_batch_used,
    set_registration_batch_used_provider=lambda: set_user_bot_registration_batch_used,
    set_open_reg_enabled_provider=lambda: set_user_bot_open_reg_enabled,
    send_open_reg_closed_notify_provider=lambda: user_bot_open_reg_notify_service.send_open_reg_closed_notify,
    logger_provider=lambda: logger,
    time_provider=lambda: time,
    threading_provider=lambda: threading,
    user_count_cache_ttl_provider=lambda: USER_COUNT_CACHE_TTL,
    user_count_near_limit_margin_provider=lambda: USER_COUNT_NEAR_LIMIT_MARGIN,
    batch_flush_interval_provider=lambda: BATCH_FLUSH_INTERVAL,
    batch_flush_threshold_provider=lambda: BATCH_FLUSH_THRESHOLD,
)

user_bot_registration_queue_service.set_dependency_providers(
    task_executor_provider=lambda: _task_executor,
    max_concurrent_tasks_provider=lambda: MAX_CONCURRENT_TASKS,
    max_waiting_tasks_provider=lambda: MAX_WAITING_TASKS,
    max_concurrent_reg_provider=lambda: MAX_CONCURRENT_REG,
    reg_queue_max_wait_provider=lambda: REG_QUEUE_MAX_WAIT,
    send_provider=lambda: user_bot_telegram_service.send,
    logger_provider=lambda: logger,
)

user_bot_concurrency_service.set_dependency_providers(
    rate_limit_provider=lambda: _rate_limit,
    username_locks_provider=lambda: _username_locks,
    username_locks_lock_provider=lambda: _username_locks_lock,
    username_lock_max_size_provider=lambda: _USERNAME_LOCK_MAX_SIZE,
    threading_provider=lambda: threading,
    time_provider=lambda: time,
    logger_provider=lambda: logger,
)

user_bot_menu_service.set_dependency_providers(
    portal_url_provider=lambda: get_user_bot_portal_url(),
)

user_bot_message_cleanup_service.set_dependency_providers(
    threading_provider=lambda: threading,
    time_provider=lambda: time,
    token_provider=lambda: get_user_bot_token(),
    telegram_client_provider=lambda: telegram_client,
    safe_proxies_provider=lambda: get_safe_proxies(),
)

user_bot_open_reg_notify_service.set_dependency_providers(
    notify_user_enabled_provider=lambda: is_user_bot_open_reg_notify_user_enabled(),
    notify_group_enabled_provider=lambda: is_user_bot_open_reg_notify_group_enabled(),
    allowed_groups_provider=lambda: get_user_bot_allowed_groups(),
    get_all_bot_users_provider=lambda: user_bot_binding_service.get_all_bot_users(),
    send_provider=lambda: user_bot_telegram_service.send,
    logger_provider=lambda: logger,
    datetime_provider=lambda: datetime,
)

user_bot_basic_commands_service.set_dependency_providers(
    record_bot_user_provider=lambda: user_bot_binding_service.record_bot_user,
    get_binding_provider=lambda: user_bot_binding_service.get_binding,
    bind_user_provider=lambda: user_bot_binding_service.bind_user,
    is_blacklisted_provider=lambda: user_bot_binding_service.is_blacklisted,
    send_provider=lambda: user_bot_telegram_service.send,
    main_menu_keyboard_provider=lambda: user_bot_menu_service.main_menu_keyboard,
    media_api_provider=lambda: media_api,
    open_reg_enabled_provider=lambda: is_user_bot_open_reg_enabled(),
    user_state_provider=lambda: _user_state,
    safe_error_message_provider=lambda: safe_error_message,
    logger_provider=lambda: logger,
)

user_bot_open_registration_service.set_dependency_providers(
    enter_reg_queue_provider=lambda: user_bot_registration_queue_service.enter_reg_queue,
    leave_reg_queue_provider=lambda: user_bot_registration_queue_service.leave_reg_queue,
    open_reg_enabled_provider=lambda: is_user_bot_open_reg_enabled(),
    send_provider=lambda: user_bot_telegram_service.send,
    reg_quota_mode_provider=lambda: get_user_bot_reg_quota_mode(),
    reg_quota_provider=lambda: get_user_bot_reg_quota(),
    reserve_quota_slot_provider=lambda: user_bot_registration_quota_service.reserve_quota_slot,
    release_quota_slot_provider=lambda: user_bot_registration_quota_service.release_quota_slot,
    set_open_reg_enabled_provider=lambda: set_user_bot_open_reg_enabled,
    send_open_reg_closed_notify_provider=lambda: user_bot_open_reg_notify_service.send_open_reg_closed_notify,
    max_reg_provider=lambda: get_user_bot_max_reg(),
    user_bot_dao_provider=lambda: user_bot_dao,
    user_state_provider=lambda: _user_state,
    secrets_provider=lambda: secrets,
    get_username_lock_provider=lambda: user_bot_concurrency_service.get_username_lock,
    get_users_list_cached_provider=lambda: user_bot_registration_quota_service.get_users_list_cached,
    quota_lock_provider=lambda: user_bot_registration_quota_service._quota_lock,
    refresh_user_count_cache_locked_provider=lambda: user_bot_registration_quota_service.refresh_user_count_cache_locked,
    user_count_cache_provider=lambda: user_bot_registration_quota_service._user_count_cache,
    media_api_provider=lambda: media_api,
    template_user_provider=lambda: get_user_bot_template_user(),
    datetime_provider=lambda: datetime,
    reg_days_provider=lambda: get_user_bot_reg_days(),
    allow_routes_provider=lambda: get_user_bot_allow_routes(),
    block_routes_provider=lambda: get_user_bot_block_routes(),
    user_dao_provider=lambda: user_dao,
    bind_user_provider=lambda: user_bot_binding_service.bind_user,
    main_menu_keyboard_provider=lambda: user_bot_menu_service.main_menu_keyboard,
    safe_error_message_provider=lambda: safe_error_message,
    logger_provider=lambda: logger,
)

user_bot_code_commands_service.set_dependency_providers(
    clear_restriction_cache_provider=lambda: user_bot_restriction_service.clear_restriction_cache,
    check_user_restrictions_provider=lambda: user_bot_restriction_service.check_user_restrictions,
    format_restriction_message_provider=lambda: user_bot_restriction_service.format_restriction_message,
    send_provider=lambda: user_bot_telegram_service.send,
    get_binding_provider=lambda: user_bot_binding_service.get_binding,
    invitation_dao_provider=lambda: invitation_dao,
    user_state_provider=lambda: _user_state,
    safe_error_message_provider=lambda: safe_error_message,
    logger_provider=lambda: logger,
    enter_reg_queue_provider=lambda: user_bot_registration_queue_service.enter_reg_queue,
    leave_reg_queue_provider=lambda: user_bot_registration_queue_service.leave_reg_queue,
    get_username_lock_provider=lambda: user_bot_concurrency_service.get_username_lock,
    media_api_provider=lambda: media_api,
    restore_invitation_code_provider=lambda: user_bot_code_commands_service.restore_invitation_code,
    bind_user_provider=lambda: user_bot_binding_service.bind_user,
    secrets_provider=lambda: secrets,
    datetime_provider=lambda: datetime,
    invalidate_users_cache_provider=lambda: _invalidate_users_cache_after_code_registration,
    send_registration_notifications_provider=lambda: _send_code_registration_notifications,
)

user_bot_points_commands_service.set_dependency_providers(
    get_binding_provider=lambda: user_bot_binding_service.get_binding,
    check_emby_account_provider=lambda: user_bot_binding_service.check_emby_account,
    unbind_user_provider=lambda: user_bot_binding_service.unbind_user,
    reply_provider=lambda: user_bot_telegram_service.reply,
    send_provider=lambda: user_bot_telegram_service.send,
    main_menu_keyboard_provider=lambda: user_bot_menu_service.main_menu_keyboard,
    delete_messages_later_provider=lambda: user_bot_message_cleanup_service.delete_messages_later,
    point_dao_provider=lambda: point_dao,
    safe_error_message_provider=lambda: safe_error_message,
    logger_provider=lambda: logger,
)

user_bot_points_game_commands_service.set_dependency_providers(
    get_binding_provider=lambda: user_bot_binding_service.get_binding,
    send_provider=lambda: user_bot_telegram_service.send,
    point_dao_provider=lambda: point_dao,
    user_bot_dao_provider=lambda: user_bot_dao,
    media_api_provider=lambda: media_api,
    safe_error_message_provider=lambda: safe_error_message,
    logger_provider=lambda: logger,
)

user_bot_game_commands_service.set_dependency_providers(
    get_binding_provider=lambda: user_bot_binding_service.get_binding,
    send_provider=lambda: user_bot_telegram_service.send,
    delete_messages_later_provider=lambda: user_bot_message_cleanup_service.delete_messages_later,
    point_dao_provider=lambda: point_dao,
    datetime_provider=lambda: datetime,
    logger_provider=lambda: logger,
)

user_bot_scratch_commands_service.set_dependency_providers(
    get_binding_provider=lambda: user_bot_binding_service.get_binding,
    send_provider=lambda: user_bot_telegram_service.send,
    delete_messages_later_provider=lambda: user_bot_message_cleanup_service.delete_messages_later,
    tg_api_provider=lambda: user_bot_telegram_service.tg_api,
    point_dao_provider=lambda: point_dao,
    media_api_provider=lambda: media_api,
    random_provider=lambda: random,
    logger_provider=lambda: logger,
    cmd_scratch_impl_provider=lambda: user_bot_scratch_commands_service._cmd_scratch_impl,
    update_scratch_message_provider=lambda: user_bot_scratch_commands_service._update_scratch_message,
    scratch_draw_result_provider=lambda: user_bot_scratch_commands_service._scratch_draw_result,
)

user_bot_pk_invitation_commands_service.set_dependency_providers(
    get_binding_provider=lambda: user_bot_binding_service.get_binding,
    get_binding_by_emby_id_provider=lambda: user_bot_binding_service.get_binding_by_emby_id,
    send_provider=lambda: user_bot_telegram_service.send,
    point_dao_provider=lambda: point_dao,
    user_bot_dao_provider=lambda: user_bot_dao,
    media_api_provider=lambda: media_api,
    safe_error_message_provider=lambda: safe_error_message,
    logger_provider=lambda: logger,
)

user_bot_pk_callback_service.set_dependency_providers(
    get_binding_provider=lambda: user_bot_binding_service.get_binding,
    tg_api_provider=lambda: user_bot_telegram_service.tg_api,
    edit_provider=lambda: user_bot_telegram_service.edit,
    send_provider=lambda: user_bot_telegram_service.send,
    point_dao_provider=lambda: point_dao,
    datetime_provider=lambda: datetime,
    sleep_provider=lambda: time.sleep,
    logger_provider=lambda: logger,
)

user_bot_shop_commands_service.set_dependency_providers(
    get_binding_provider=lambda: user_bot_binding_service.get_binding,
    check_emby_account_provider=lambda: user_bot_binding_service.check_emby_account,
    unbind_user_provider=lambda: user_bot_binding_service.unbind_user,
    reply_provider=lambda: user_bot_telegram_service.reply,
    send_provider=lambda: user_bot_telegram_service.send,
    tg_api_provider=lambda: user_bot_telegram_service.tg_api,
    main_menu_keyboard_provider=lambda: user_bot_menu_service.main_menu_keyboard,
    point_dao_provider=lambda: point_dao,
    media_api_provider=lambda: media_api,
    safe_error_message_provider=lambda: safe_error_message,
    logger_provider=lambda: logger,
)

user_bot_request_commands_service.set_dependency_providers(
    get_binding_provider=lambda: user_bot_binding_service.get_binding,
    check_emby_account_provider=lambda: user_bot_binding_service.check_emby_account,
    unbind_user_provider=lambda: user_bot_binding_service.unbind_user,
    reply_provider=lambda: user_bot_telegram_service.reply,
    send_provider=lambda: user_bot_telegram_service.send,
    tg_api_provider=lambda: user_bot_telegram_service.tg_api,
    main_menu_keyboard_provider=lambda: user_bot_menu_service.main_menu_keyboard,
    tmdb_client_provider=lambda: tmdb_client,
    get_safe_proxies_provider=lambda: get_safe_proxies,
    media_request_dao_provider=lambda: media_request_dao,
    submit_request_provider=lambda: user_bot_request_commands_service._submit_request,
    portal_url_provider=lambda: get_user_bot_portal_url,
    media_server_main_public_url_provider=lambda: get_media_server_main_public_url,
    safe_error_message_provider=lambda: safe_error_message,
    logger_provider=lambda: logger,
)

user_bot_transfer_commands_service.set_dependency_providers(
    get_binding_provider=lambda: user_bot_binding_service.get_binding,
    send_provider=lambda: user_bot_telegram_service.send,
    delete_messages_later_provider=lambda: user_bot_message_cleanup_service.delete_messages_later,
    point_dao_provider=lambda: point_dao,
    user_bot_dao_provider=lambda: user_bot_dao,
    media_api_provider=lambda: media_api,
    logger_provider=lambda: logger,
)

user_bot_dice_pk_commands_service.set_dependency_providers(
    get_binding_provider=lambda: user_bot_binding_service.get_binding,
    send_provider=lambda: user_bot_telegram_service.send,
    tg_api_provider=lambda: user_bot_telegram_service.tg_api,
    delete_messages_later_provider=lambda: user_bot_message_cleanup_service.delete_messages_later,
    point_dao_provider=lambda: point_dao,
    random_provider=lambda: random,
    sleep_provider=lambda: time.sleep,
    logger_provider=lambda: logger,
)

user_bot_account_commands_service.set_dependency_providers(
    get_binding_provider=lambda: user_bot_binding_service.get_binding,
    check_emby_account_provider=lambda: user_bot_binding_service.check_emby_account,
    unbind_user_provider=lambda: user_bot_binding_service.unbind_user,
    send_provider=lambda: user_bot_telegram_service.send,
    reply_provider=lambda: user_bot_telegram_service.reply,
    main_menu_keyboard_provider=lambda: user_bot_menu_service.main_menu_keyboard,
    user_dao_provider=lambda: user_dao,
    stats_queries_provider=lambda: stats_queries,
    media_api_provider=lambda: media_api,
    datetime_provider=lambda: datetime,
    safe_error_message_provider=lambda: safe_error_message,
    logger_provider=lambda: logger,
)

user_bot_channel_commands_service.set_dependency_providers(
    get_binding_provider=lambda: user_bot_binding_service.get_binding,
    bind_channel_provider=lambda: user_bot_binding_service.bind_channel,
    unbind_channel_provider=lambda: user_bot_binding_service.unbind_channel,
    send_provider=lambda: user_bot_telegram_service.send,
    safe_error_message_provider=lambda: safe_error_message,
    logger_provider=lambda: logger,
)

user_bot_password_commands_service.set_dependency_providers(
    get_binding_provider=lambda: user_bot_binding_service.get_binding,
    check_emby_account_provider=lambda: user_bot_binding_service.check_emby_account,
    unbind_user_provider=lambda: user_bot_binding_service.unbind_user,
    send_provider=lambda: user_bot_telegram_service.send,
    main_menu_keyboard_provider=lambda: user_bot_menu_service.main_menu_keyboard,
    user_state_provider=lambda: _user_state,
    validate_password_strength_provider=lambda: validate_password_strength,
    media_api_provider=lambda: media_api,
    user_bot_dao_provider=lambda: user_bot_dao,
    safe_error_message_provider=lambda: safe_error_message,
    logger_provider=lambda: logger,
)

user_bot_service_info_commands_service.set_dependency_providers(
    get_binding_provider=lambda: user_bot_binding_service.get_binding,
    check_emby_account_provider=lambda: user_bot_binding_service.check_emby_account,
    unbind_user_provider=lambda: user_bot_binding_service.unbind_user,
    reply_provider=lambda: user_bot_telegram_service.reply,
    send_provider=lambda: user_bot_telegram_service.send,
    main_menu_keyboard_provider=lambda: user_bot_menu_service.main_menu_keyboard,
    get_media_server_user_routes_provider=lambda: get_media_server_user_routes,
    network_client_provider=lambda: network_client,
    media_api_provider=lambda: media_api,
    time_provider=lambda: time,
    logger_provider=lambda: logger,
)

user_bot_telegram_service.set_dependency_providers(
    telegram_client_provider=lambda: telegram_client,
    get_token_provider=lambda: get_user_bot_token,
    get_safe_proxies_provider=lambda: get_safe_proxies,
    tg_api_provider=lambda: user_bot_telegram_service.tg_api,
    send_provider=lambda: user_bot_telegram_service.send,
    edit_provider=lambda: user_bot_telegram_service.edit,
)

user_bot_restriction_service.set_dependency_providers(
    tg_api_provider=lambda: user_bot_telegram_service.tg_api,
    restriction_enabled_provider=lambda: is_user_bot_restriction_enabled,
    required_channels_provider=lambda: get_user_bot_required_channels,
    required_groups_provider=lambda: get_user_bot_required_groups,
    restriction_cache_ttl_provider=lambda: get_user_bot_restriction_cache_ttl,
    restriction_cache_provider=lambda: _restriction_cache,
    restriction_cache_lock_provider=lambda: _restriction_cache_lock,
    check_user_in_chat_provider=lambda: user_bot_restriction_service.check_user_in_chat,
    logger_provider=lambda: logger,
    time_provider=lambda: time,
)

user_bot_polling_service.set_dependency_providers(
    telegram_client_provider=lambda: telegram_client,
    get_safe_proxies_provider=lambda: get_safe_proxies,
    submit_task_provider=lambda: user_bot_registration_queue_service.submit_task,
    send_provider=lambda: user_bot_telegram_service.send,
    logger_provider=lambda: logger,
)

user_bot_callback_dispatcher_service.set_dependency_providers(
    rate_check_provider=lambda: user_bot_concurrency_service.rate_check,
    tg_api_provider=lambda: user_bot_telegram_service.tg_api,
    check_user_restrictions_provider=lambda: user_bot_restriction_service.check_user_restrictions,
    format_restriction_message_provider=lambda: user_bot_restriction_service.format_restriction_message,
    send_provider=lambda: user_bot_telegram_service.send,
    edit_provider=lambda: user_bot_telegram_service.edit,
    get_binding_provider=lambda: user_bot_binding_service.get_binding,
    check_emby_account_provider=lambda: user_bot_binding_service.check_emby_account,
    unbind_user_provider=lambda: user_bot_binding_service.unbind_user,
    add_to_blacklist_provider=lambda: user_bot_binding_service.add_to_blacklist,
    main_menu_keyboard_provider=lambda: user_bot_menu_service.main_menu_keyboard,
    user_state_provider=lambda: _user_state,
    cmd_register_provider=lambda: user_bot_basic_commands_service.cmd_register,
    cmd_library_provider=lambda: user_bot_service_info_commands_service.cmd_library,
    cmd_server_provider=lambda: user_bot_service_info_commands_service.cmd_server,
    cmd_checkin_provider=lambda: user_bot_points_commands_service.cmd_checkin,
    cmd_points_provider=lambda: user_bot_points_commands_service.cmd_points,
    cmd_profile_provider=lambda: user_bot_account_commands_service.cmd_profile,
    cmd_shop_provider=lambda: user_bot_shop_commands_service.cmd_shop,
    handle_pk_accept_callback_provider=lambda: user_bot_pk_callback_service._handle_pk_accept_callback,
    handle_pk_reject_callback_provider=lambda: user_bot_pk_callback_service._handle_pk_reject_callback,
    cmd_redeem_callback_provider=lambda: user_bot_shop_commands_service.cmd_redeem_callback,
    cmd_request_callback_provider=lambda: user_bot_request_commands_service.cmd_request_callback,
    submit_request_provider=lambda: user_bot_request_commands_service._submit_request,
    cmd_myrequests_provider=lambda: user_bot_request_commands_service.cmd_myrequests,
    handle_scratch_provider=lambda: user_bot_scratch_commands_service._handle_scratch,
)

user_bot_new_chat_member_service.set_dependency_providers(
    user_bot_token_provider=lambda: get_user_bot_token(),
    welcome_msg_provider=lambda: get_user_bot_welcome_msg(),
    send_provider=lambda: user_bot_telegram_service.send,
)

user_bot_message_dispatcher_service.set_dependency_providers(
    logger_provider=lambda: logger,
    get_channel_binding_provider=lambda: user_bot_binding_service.get_channel_binding,
    send_provider=lambda: user_bot_telegram_service.send,
    rate_check_provider=lambda: user_bot_concurrency_service.rate_check,
    group_enabled_provider=lambda: get_user_bot_group_enabled,
    allowed_groups_provider=lambda: get_user_bot_allowed_groups,
    group_commands_provider=lambda: get_user_bot_group_commands,
    delete_messages_later_provider=lambda: user_bot_message_cleanup_service.delete_messages_later,
    new_chat_members_handler_provider=lambda: user_bot_new_chat_member_service.handle_new_chat_members,
    get_binding_provider=lambda: user_bot_binding_service.get_binding,
    check_user_restrictions_provider=lambda: user_bot_restriction_service.check_user_restrictions,
    format_restriction_message_provider=lambda: user_bot_restriction_service.format_restriction_message,
    user_state_provider=lambda: _user_state,
    main_menu_keyboard_provider=lambda: user_bot_menu_service.main_menu_keyboard,
    check_emby_account_provider=lambda: user_bot_binding_service.check_emby_account,
    unbind_user_provider=lambda: user_bot_binding_service.unbind_user,
    do_register_provider=lambda: user_bot_open_registration_service.do_register,
    do_code_register_provider=lambda: user_bot_code_commands_service.do_code_register,
    cmd_checkin_provider=lambda: user_bot_points_commands_service.cmd_checkin,
    cmd_points_provider=lambda: user_bot_points_commands_service.cmd_points,
    cmd_rank_provider=lambda: user_bot_points_game_commands_service.cmd_rank,
    cmd_transfer_provider=lambda: user_bot_transfer_commands_service.cmd_transfer,
    cmd_rob_provider=lambda: user_bot_points_game_commands_service.cmd_rob,
    cmd_pk_invite_provider=lambda: user_bot_pk_invitation_commands_service.cmd_pk_invite,
    cmd_redpacket_provider=lambda: user_bot_transfer_commands_service.cmd_redpacket,
    cmd_grab_provider=lambda: user_bot_game_commands_service.cmd_grab,
    cmd_pk_provider=lambda: user_bot_dice_pk_commands_service.cmd_pk,
    cmd_lottery_provider=lambda: user_bot_game_commands_service.cmd_lottery,
    cmd_scratch_provider=lambda: user_bot_scratch_commands_service.cmd_scratch,
    cmd_check_provider=lambda: user_bot_code_commands_service.cmd_check,
    cmd_start_provider=lambda: user_bot_basic_commands_service.cmd_start,
    cmd_help_provider=lambda: user_bot_basic_commands_service.cmd_help,
    cmd_bind_channel_provider=lambda: user_bot_channel_commands_service.cmd_bind_channel,
    cmd_bind_provider=lambda: user_bot_basic_commands_service.cmd_bind,
    cmd_register_provider=lambda: user_bot_basic_commands_service.cmd_register,
    cmd_code_provider=lambda: user_bot_code_commands_service.cmd_code,
    cmd_unbind_channel_provider=lambda: user_bot_channel_commands_service.cmd_unbind_channel,
    cmd_unbind_provider=lambda: user_bot_account_commands_service.cmd_unbind,
    cmd_profile_provider=lambda: user_bot_account_commands_service.cmd_profile,
    cmd_renew_provider=lambda: user_bot_code_commands_service.cmd_renew,
    cmd_calendar_provider=lambda: user_bot_service_info_commands_service.cmd_calendar,
    cmd_shop_provider=lambda: user_bot_shop_commands_service.cmd_shop,
    cmd_request_provider=lambda: user_bot_request_commands_service.cmd_request,
    cmd_myrequests_provider=lambda: user_bot_request_commands_service.cmd_myrequests,
    cmd_server_provider=lambda: user_bot_service_info_commands_service.cmd_server,
    cmd_library_provider=lambda: user_bot_service_info_commands_service.cmd_library,
    cmd_password_provider=lambda: user_bot_password_commands_service.cmd_password,
    cmd_pk_accept_provider=lambda: user_bot_pk_invitation_commands_service.cmd_pk_accept,
    cmd_pk_reject_provider=lambda: user_bot_pk_invitation_commands_service.cmd_pk_reject,
)

user_bot_lottery_draw_service.set_dependency_providers(
    datetime_provider=lambda: datetime,
    random_provider=lambda: random,
    point_dao_provider=lambda: point_dao,
    media_api_provider=lambda: media_api,
    allowed_groups_provider=lambda: get_user_bot_allowed_groups(),
    get_binding_by_emby_id_provider=lambda: user_bot_binding_service.get_binding_by_emby_id,
    user_bot_dao_provider=lambda: user_bot_dao,
    send_provider=lambda: user_bot_telegram_service.send,
    logger_provider=lambda: logger,
)

user_bot_scheduler_service.set_dependency_providers(
    point_dao_provider=lambda: point_dao,
    datetime_provider=lambda: datetime,
    tg_api_provider=lambda: user_bot_telegram_service.tg_api,
    do_lottery_draw_provider=lambda: user_bot_lottery_draw_service.do_lottery_draw,
    logger_provider=lambda: logger,
)


def _ensure_user_bot_tables():
    try:
        user_bot_dao.ensure_user_bot_tables()
    except Exception as e:
        logger.error(f"用户机器人表初始化失败: {e}")


# 用户会话状态（用于多步交互，如注册输入用户名）
_user_state = {}  # tg_user_id -> {"action": "register_name", ...}


def _invalidate_users_cache_after_code_registration():
    try:
        from app.domains.users import public_service as user_service
        user_service.invalidate_emby_users_cache()
    except:
        pass


def _send_code_registration_notifications(safe_name, days, code, tg_user_id):
    try:
        from app.bot.notification_bot.bot_service import bot
        from app.infra.db.notification_dao import add_system_notification
        days_display = "永久" if (days == -1 or days == 0 or days >= 36500) else f"{days} 天"
        msg = f"🎟️ <b>新用户注册</b>\n\n👤 {safe_name}\n📅 有效期：{days_display}\n🔗 邀请码：{code}\n📱 注册渠道：TG机器人\n🆔 TG：{tg_user_id}"
        bot.notifier.send_message("sys_notify", msg, platform="all")
        add_system_notification("user", f"新用户注册: {safe_name}", f"TG机器人注册，有效期 {days_display}", "/users_manage")
    except Exception:
        pass


def _is_pro():
    """检查是否为 Pro 用户"""
    return True


# ==========================================
# 用户机器人主类
# ==========================================
class UserBot:
    def __init__(self):
        self.running = False
        self.poll_thread = None
        self.scheduler_thread = None  # 🔥 定时任务线程
        self.offset = 0
        self._stop_event = threading.Event()

    def start(self):
        if not _is_pro():
            logger.info("🤖 [UserBot] 非 Pro 用户，用户机器人未启动")
            return
        token = (get_user_bot_token() or "").strip()
        if not token:
            return
        notify_token = (get_notify_tg_bot_token() or "").strip()
        if notify_token and notify_token == token:
            logger.warning("[UserBot] 用户机器人 Token 与管理员机器人 Token 相同，两个 polling 服务会互相抢更新；请使用单独的 BotFather token")
        if self.running:
            return
        for attr in ("poll_thread", "scheduler_thread"):
            thread = getattr(self, attr)
            if thread and thread.is_alive():
                return
            if thread:
                setattr(self, attr, None)
        self._stop_event.clear()
        self.running = True
        self._clear_webhook()
        self._set_commands()
        self.poll_thread = threading.Thread(
            target=self._polling_loop,
            daemon=True,
            name="user-bot-polling",
        )
        self.poll_thread.start()
        # 🔥 启动定时任务线程
        self.scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            daemon=True,
            name="user-bot-scheduler",
        )
        self.scheduler_thread.start()
        # 🔒 加载 batch_used 内存值 + 启动定时落盘线程
        user_bot_registration_quota_service.load_batch_used_from_cfg()
        user_bot_registration_quota_service.start_batch_flush_thread()
        logger.info("🤖 [Pro] 用户 TG 机器人已启动")

    def _clear_webhook(self):
        result = user_bot_telegram_service.tg_api("deleteWebhook", {"drop_pending_updates": False})
        if not result or not result.get("ok"):
            logger.warning("[UserBot] 清理 Telegram webhook 失败，polling 可能无法收到更新；请检查 token、代理或 Telegram API 连通性")
            return
        logger.info("[UserBot] Telegram webhook 已清理，使用 polling 接收消息")

    def stop(self):
        self.running = False
        self._stop_event.set()
        # 同步 flush 一次防止丢失增量
        user_bot_registration_quota_service.stop_batch_flush_thread()
        try:
            user_bot_registration_quota_service.flush_batch_used(force=True)
        except Exception:
            logger.exception("[UserBot] stop 时 flush batch_used 失败")
        for attr in ("poll_thread", "scheduler_thread"):
            thread = getattr(self, attr)
            if thread and thread.is_alive():
                thread.join(timeout=1)
            if not thread or not thread.is_alive():
                setattr(self, attr, None)

    def _set_commands(self):
        cmds = [
            {"command": "start", "description": "开始使用"},
            {"command": "menu", "description": "主菜单"},
            {"command": "help", "description": "帮助菜单"},
            {"command": "bind", "description": "绑定 Emby 账号"},
            {"command": "unbind", "description": "解绑账号"},
            {"command": "profile", "description": "个人中心"},
            {"command": "register", "description": "注册新账号"},
            {"command": "code", "description": "使用注册码"},
            {"command": "renew", "description": "使用续期码"},
            {"command": "checkin", "description": "每日签到"},
            {"command": "points", "description": "查看积分"},
            {"command": "shop", "description": "积分商城"},
            {"command": "request", "description": "求片"},
            {"command": "myrequests", "description": "我的求片"},
            {"command": "server", "description": "服务器状态"},
            {"command": "library", "description": "媒体库统计"},
            {"command": "calendar", "description": "今日更新"},
            {"command": "password", "description": "修改密码"},
        ]
        user_bot_telegram_service.tg_api("setMyCommands", {"commands": cmds})

    def _polling_loop(self):
        return user_bot_polling_service.run_polling_loop(
            get_user_bot_token(),
            lambda: self.running,
            self._stop_event,
            lambda: self.offset,
            lambda offset: setattr(self, "offset", offset),
            lambda: user_bot_message_dispatcher_service.handle_message,
            lambda: user_bot_callback_dispatcher_service.handle_callback,
        )

    def _scheduler_loop(self):
        return user_bot_scheduler_service.run_scheduler_loop(
            lambda: self.running,
            self._stop_event,
        )


user_bot = UserBot()


def start_user_bot_services():
    _ensure_user_bot_tables()
    if get_user_bot_token():
        user_bot.start()
