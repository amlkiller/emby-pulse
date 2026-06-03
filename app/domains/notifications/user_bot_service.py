"""
EmbyPulse 用户 TG 机器人 (Pro 专属)
独立于管理员机器人，面向普通用户提供自助服务
"""
import threading
import time
import datetime
import secrets
import logging
import re
import random
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from app.domains.media_requests import media_request_dao
from app.domains.points import point_dao
from app.domains.system import invitation_dao
from app.domains.users import user_dao
from app.domains.users import user_bot_dao
from app.domains.notifications import user_bot_account_commands_service
from app.domains.notifications import user_bot_basic_commands_service
from app.domains.notifications import user_bot_binding_service
from app.domains.notifications import user_bot_channel_commands_service
from app.domains.notifications import user_bot_code_commands_service
from app.domains.notifications import user_bot_concurrency_service
from app.domains.notifications import user_bot_dice_pk_commands_service
from app.domains.notifications import user_bot_game_commands_service
from app.domains.notifications import user_bot_menu_service
from app.domains.notifications import user_bot_message_cleanup_service
from app.domains.notifications import user_bot_open_reg_notify_service
from app.domains.notifications import user_bot_password_commands_service
from app.domains.notifications import user_bot_pk_callback_service
from app.domains.notifications import user_bot_pk_invitation_commands_service
from app.domains.notifications import user_bot_points_commands_service
from app.domains.notifications import user_bot_points_game_commands_service
from app.domains.notifications import user_bot_registration_queue_service
from app.domains.notifications import user_bot_registration_quota_service
from app.domains.notifications import user_bot_request_commands_service
from app.domains.notifications import user_bot_restriction_service
from app.domains.notifications import user_bot_shop_commands_service
from app.domains.notifications import user_bot_scratch_commands_service
from app.domains.notifications import user_bot_service_info_commands_service
from app.domains.notifications import user_bot_telegram_service
from app.domains.notifications import user_bot_transfer_commands_service
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
_active_tasks = 0  # 当前活跃任务数
_active_tasks_lock = threading.Lock()
_waiting_count = 0  # 等待中的任务数
_waiting_count_lock = threading.Lock()
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

_reg_sema = threading.BoundedSemaphore(MAX_CONCURRENT_REG)
_reg_waiters_lock = threading.Lock()
_reg_waiters = 0                    # 含正在 acquire 等待的人数
_reg_active = 0                     # 已 acquire 进入临界区的人数

# quota 软预占：在调用 Emby 建号前先占槽，建号失败时回滚
_quota_lock = threading.Lock()
_quota_reserved = 0
_user_count_cache = {"count": None, "users": None, "ts": 0.0}

# batch_used 内存权威值 + 定时落盘到 cfg.json
_batch_used_lock = threading.Lock()
_batch_used_mem = None              # 懒初始化，None 表示未加载
_batch_used_dirty = 0               # 距上次 flush 的累计增量
_batch_flush_stop = threading.Event()
_batch_flush_thread = None


def _set_quota_reserved(value):
    global _quota_reserved
    _quota_reserved = value


def _set_batch_used_mem(value):
    global _batch_used_mem
    _batch_used_mem = value


def _set_batch_used_dirty(value):
    global _batch_used_dirty
    _batch_used_dirty = value


def _set_batch_flush_thread(value):
    global _batch_flush_thread
    _batch_flush_thread = value


def _set_active_tasks(value):
    global _active_tasks
    _active_tasks = value


def _set_waiting_count(value):
    global _waiting_count
    _waiting_count = value


def _set_reg_waiters(value):
    global _reg_waiters
    _reg_waiters = value


def _set_reg_active(value):
    global _reg_active
    _reg_active = value


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
    get_binding_provider=lambda: _get_binding,
)

user_bot_registration_quota_service.set_dependency_providers(
    media_api_provider=lambda: media_api,
    get_hidden_users_provider=lambda: get_hidden_users,
    get_registration_batch_used_provider=lambda: get_user_bot_registration_batch_used,
    set_registration_batch_used_provider=lambda: set_user_bot_registration_batch_used,
    set_open_reg_enabled_provider=lambda: set_user_bot_open_reg_enabled,
    send_open_reg_closed_notify_provider=lambda: _send_open_reg_closed_notify,
    logger_provider=lambda: logger,
    time_provider=lambda: time,
    threading_provider=lambda: threading,
    quota_lock_provider=lambda: _quota_lock,
    get_quota_reserved_provider=lambda: _quota_reserved,
    set_quota_reserved_callback=_set_quota_reserved,
    user_count_cache_provider=lambda: _user_count_cache,
    batch_used_lock_provider=lambda: _batch_used_lock,
    get_batch_used_mem_provider=lambda: _batch_used_mem,
    set_batch_used_mem_callback=_set_batch_used_mem,
    get_batch_used_dirty_provider=lambda: _batch_used_dirty,
    set_batch_used_dirty_callback=_set_batch_used_dirty,
    batch_flush_stop_provider=lambda: _batch_flush_stop,
    get_batch_flush_thread_provider=lambda: _batch_flush_thread,
    set_batch_flush_thread_callback=_set_batch_flush_thread,
    user_count_cache_ttl_provider=lambda: USER_COUNT_CACHE_TTL,
    user_count_near_limit_margin_provider=lambda: USER_COUNT_NEAR_LIMIT_MARGIN,
    batch_flush_interval_provider=lambda: BATCH_FLUSH_INTERVAL,
    batch_flush_threshold_provider=lambda: BATCH_FLUSH_THRESHOLD,
)

user_bot_registration_queue_service.set_dependency_providers(
    task_executor_provider=lambda: _task_executor,
    active_tasks_lock_provider=lambda: _active_tasks_lock,
    waiting_count_lock_provider=lambda: _waiting_count_lock,
    get_active_tasks_provider=lambda: _active_tasks,
    set_active_tasks_callback=_set_active_tasks,
    get_waiting_count_provider=lambda: _waiting_count,
    set_waiting_count_callback=_set_waiting_count,
    max_concurrent_tasks_provider=lambda: MAX_CONCURRENT_TASKS,
    max_waiting_tasks_provider=lambda: MAX_WAITING_TASKS,
    reg_sema_provider=lambda: _reg_sema,
    reg_waiters_lock_provider=lambda: _reg_waiters_lock,
    get_reg_waiters_provider=lambda: _reg_waiters,
    set_reg_waiters_callback=_set_reg_waiters,
    get_reg_active_provider=lambda: _reg_active,
    set_reg_active_callback=_set_reg_active,
    max_concurrent_reg_provider=lambda: MAX_CONCURRENT_REG,
    reg_queue_max_wait_provider=lambda: REG_QUEUE_MAX_WAIT,
    send_provider=lambda: _send,
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
    get_all_bot_users_provider=lambda: _get_all_bot_users(),
    send_provider=lambda: _send,
    logger_provider=lambda: logger,
    datetime_provider=lambda: datetime,
)

user_bot_basic_commands_service.set_dependency_providers(
    record_bot_user_provider=lambda: _record_bot_user,
    get_binding_provider=lambda: _get_binding,
    bind_user_provider=lambda: _bind_user,
    is_blacklisted_provider=lambda: _is_blacklisted,
    send_provider=lambda: _send,
    main_menu_keyboard_provider=lambda: _main_menu_keyboard,
    media_api_provider=lambda: media_api,
    open_reg_enabled_provider=lambda: is_user_bot_open_reg_enabled(),
    user_state_provider=lambda: _user_state,
    safe_error_message_provider=lambda: safe_error_message,
    logger_provider=lambda: logger,
)

user_bot_code_commands_service.set_dependency_providers(
    clear_restriction_cache_provider=lambda: _clear_restriction_cache,
    check_user_restrictions_provider=lambda: _check_user_restrictions,
    format_restriction_message_provider=lambda: _format_restriction_message,
    send_provider=lambda: _send,
    get_binding_provider=lambda: _get_binding,
    invitation_dao_provider=lambda: invitation_dao,
    user_state_provider=lambda: _user_state,
    safe_error_message_provider=lambda: safe_error_message,
    logger_provider=lambda: logger,
    enter_reg_queue_provider=lambda: _enter_reg_queue,
    leave_reg_queue_provider=lambda: _leave_reg_queue,
    get_username_lock_provider=lambda: _get_username_lock,
    media_api_provider=lambda: media_api,
    restore_invitation_code_provider=lambda: _restore_invitation_code,
    bind_user_provider=lambda: _bind_user,
    secrets_provider=lambda: secrets,
    datetime_provider=lambda: datetime,
    invalidate_users_cache_provider=lambda: _invalidate_users_cache_after_code_registration,
    send_registration_notifications_provider=lambda: _send_code_registration_notifications,
)

user_bot_points_commands_service.set_dependency_providers(
    get_binding_provider=lambda: _get_binding,
    check_emby_account_provider=lambda: _check_emby_account,
    unbind_user_provider=lambda: _unbind_user,
    reply_provider=lambda: _reply,
    send_provider=lambda: _send,
    main_menu_keyboard_provider=lambda: _main_menu_keyboard,
    delete_messages_later_provider=lambda: _delete_messages_later,
    point_dao_provider=lambda: point_dao,
    safe_error_message_provider=lambda: safe_error_message,
    logger_provider=lambda: logger,
)

user_bot_points_game_commands_service.set_dependency_providers(
    get_binding_provider=lambda: _get_binding,
    send_provider=lambda: _send,
    point_dao_provider=lambda: point_dao,
    user_bot_dao_provider=lambda: user_bot_dao,
    media_api_provider=lambda: media_api,
    safe_error_message_provider=lambda: safe_error_message,
    logger_provider=lambda: logger,
)

user_bot_game_commands_service.set_dependency_providers(
    get_binding_provider=lambda: _get_binding,
    send_provider=lambda: _send,
    delete_messages_later_provider=lambda: _delete_messages_later,
    point_dao_provider=lambda: point_dao,
    datetime_provider=lambda: datetime,
    logger_provider=lambda: logger,
)

user_bot_scratch_commands_service.set_dependency_providers(
    get_binding_provider=lambda: _get_binding,
    send_provider=lambda: _send,
    delete_messages_later_provider=lambda: _delete_messages_later,
    tg_api_provider=lambda: _tg_api,
    point_dao_provider=lambda: point_dao,
    media_api_provider=lambda: media_api,
    random_provider=lambda: random,
    logger_provider=lambda: logger,
    cmd_scratch_impl_provider=lambda: _cmd_scratch_impl,
    update_scratch_message_provider=lambda: _update_scratch_message,
    scratch_draw_result_provider=lambda: _scratch_draw_result,
)

user_bot_pk_invitation_commands_service.set_dependency_providers(
    get_binding_provider=lambda: _get_binding,
    get_binding_by_emby_id_provider=lambda: _get_binding_by_emby_id,
    send_provider=lambda: _send,
    point_dao_provider=lambda: point_dao,
    user_bot_dao_provider=lambda: user_bot_dao,
    media_api_provider=lambda: media_api,
    safe_error_message_provider=lambda: safe_error_message,
    logger_provider=lambda: logger,
)

user_bot_pk_callback_service.set_dependency_providers(
    get_binding_provider=lambda: _get_binding,
    tg_api_provider=lambda: _tg_api,
    edit_provider=lambda: _edit,
    send_provider=lambda: _send,
    point_dao_provider=lambda: point_dao,
    datetime_provider=lambda: datetime,
    sleep_provider=lambda: time.sleep,
    logger_provider=lambda: logger,
)

user_bot_shop_commands_service.set_dependency_providers(
    get_binding_provider=lambda: _get_binding,
    check_emby_account_provider=lambda: _check_emby_account,
    unbind_user_provider=lambda: _unbind_user,
    reply_provider=lambda: _reply,
    send_provider=lambda: _send,
    tg_api_provider=lambda: _tg_api,
    main_menu_keyboard_provider=lambda: _main_menu_keyboard,
    point_dao_provider=lambda: point_dao,
    media_api_provider=lambda: media_api,
    safe_error_message_provider=lambda: safe_error_message,
    logger_provider=lambda: logger,
)

user_bot_request_commands_service.set_dependency_providers(
    get_binding_provider=lambda: _get_binding,
    check_emby_account_provider=lambda: _check_emby_account,
    unbind_user_provider=lambda: _unbind_user,
    reply_provider=lambda: _reply,
    send_provider=lambda: _send,
    tg_api_provider=lambda: _tg_api,
    main_menu_keyboard_provider=lambda: _main_menu_keyboard,
    tmdb_client_provider=lambda: tmdb_client,
    get_safe_proxies_provider=lambda: get_safe_proxies,
    media_request_dao_provider=lambda: media_request_dao,
    submit_request_provider=lambda: _submit_request,
    portal_url_provider=lambda: get_user_bot_portal_url,
    media_server_main_public_url_provider=lambda: get_media_server_main_public_url,
    safe_error_message_provider=lambda: safe_error_message,
    logger_provider=lambda: logger,
)

user_bot_transfer_commands_service.set_dependency_providers(
    get_binding_provider=lambda: _get_binding,
    send_provider=lambda: _send,
    delete_messages_later_provider=lambda: _delete_messages_later,
    point_dao_provider=lambda: point_dao,
    user_bot_dao_provider=lambda: user_bot_dao,
    media_api_provider=lambda: media_api,
    logger_provider=lambda: logger,
)

user_bot_dice_pk_commands_service.set_dependency_providers(
    get_binding_provider=lambda: _get_binding,
    send_provider=lambda: _send,
    tg_api_provider=lambda: _tg_api,
    delete_messages_later_provider=lambda: _delete_messages_later,
    point_dao_provider=lambda: point_dao,
    random_provider=lambda: random,
    sleep_provider=lambda: time.sleep,
    logger_provider=lambda: logger,
)

user_bot_account_commands_service.set_dependency_providers(
    get_binding_provider=lambda: _get_binding,
    check_emby_account_provider=lambda: _check_emby_account,
    unbind_user_provider=lambda: _unbind_user,
    send_provider=lambda: _send,
    reply_provider=lambda: _reply,
    main_menu_keyboard_provider=lambda: _main_menu_keyboard,
    user_dao_provider=lambda: user_dao,
    stats_queries_provider=lambda: stats_queries,
    media_api_provider=lambda: media_api,
    datetime_provider=lambda: datetime,
    safe_error_message_provider=lambda: safe_error_message,
    logger_provider=lambda: logger,
)

user_bot_channel_commands_service.set_dependency_providers(
    get_binding_provider=lambda: _get_binding,
    bind_channel_provider=lambda: _bind_channel,
    unbind_channel_provider=lambda: _unbind_channel,
    send_provider=lambda: _send,
    safe_error_message_provider=lambda: safe_error_message,
    logger_provider=lambda: logger,
)

user_bot_password_commands_service.set_dependency_providers(
    get_binding_provider=lambda: _get_binding,
    check_emby_account_provider=lambda: _check_emby_account,
    unbind_user_provider=lambda: _unbind_user,
    send_provider=lambda: _send,
    main_menu_keyboard_provider=lambda: _main_menu_keyboard,
    user_state_provider=lambda: _user_state,
    validate_password_strength_provider=lambda: validate_password_strength,
    media_api_provider=lambda: media_api,
    user_bot_dao_provider=lambda: user_bot_dao,
    safe_error_message_provider=lambda: safe_error_message,
    logger_provider=lambda: logger,
)

user_bot_service_info_commands_service.set_dependency_providers(
    get_binding_provider=lambda: _get_binding,
    check_emby_account_provider=lambda: _check_emby_account,
    unbind_user_provider=lambda: _unbind_user,
    reply_provider=lambda: _reply,
    send_provider=lambda: _send,
    main_menu_keyboard_provider=lambda: _main_menu_keyboard,
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
    tg_api_provider=lambda: _tg_api,
    send_provider=lambda: _send,
    edit_provider=lambda: _edit,
)

user_bot_restriction_service.set_dependency_providers(
    tg_api_provider=lambda: _tg_api,
    restriction_enabled_provider=lambda: is_user_bot_restriction_enabled,
    required_channels_provider=lambda: get_user_bot_required_channels,
    required_groups_provider=lambda: get_user_bot_required_groups,
    restriction_cache_ttl_provider=lambda: get_user_bot_restriction_cache_ttl,
    restriction_cache_provider=lambda: _restriction_cache,
    restriction_cache_lock_provider=lambda: _restriction_cache_lock,
    check_user_in_chat_provider=lambda: _check_user_in_chat,
    logger_provider=lambda: logger,
    time_provider=lambda: time,
)


def _submit_task(func, *args, **kwargs):
    return user_bot_registration_queue_service.submit_task(func, *args, **kwargs)


def _get_queue_status():
    return user_bot_registration_queue_service.get_queue_status()


def _enter_reg_queue(chat_id):
    return user_bot_registration_queue_service.enter_reg_queue(chat_id)


def _leave_reg_queue():
    return user_bot_registration_queue_service.leave_reg_queue()


def _ensure_user_bot_tables():
    try:
        user_bot_dao.ensure_user_bot_tables()
    except Exception as e:
        logger.error(f"用户机器人表初始化失败: {e}")


def _tg_api(method, data=None, token=None):
    return user_bot_telegram_service.tg_api(method, data=data, token=token)


def _check_user_in_chat(user_id: str, chat_id: str) -> bool:
    return user_bot_restriction_service.check_user_in_chat(user_id, chat_id)


def _check_user_restrictions(tg_user_id: str) -> dict:
    return user_bot_restriction_service.check_user_restrictions(tg_user_id)


def _clear_restriction_cache(tg_user_id: str):
    return user_bot_restriction_service.clear_restriction_cache(tg_user_id)


def _format_restriction_message(check_result: dict) -> str:
    return user_bot_restriction_service.format_restriction_message(check_result)


def _send(chat_id, text, reply_markup=None):
    return user_bot_telegram_service.send(chat_id, text, reply_markup=reply_markup)


def _edit(chat_id, message_id, text, reply_markup=None):
    return user_bot_telegram_service.edit(chat_id, message_id, text, reply_markup=reply_markup)


def _reply(chat_id, text, reply_markup=None, msg_id=None):
    return user_bot_telegram_service.reply(chat_id, text, reply_markup=reply_markup, msg_id=msg_id)


# 用户会话状态（用于多步交互，如注册输入用户名）
_user_state = {}  # tg_user_id -> {"action": "register_name", ...}


def _send_open_reg_closed_notify(reason=""):
    return user_bot_open_reg_notify_service.send_open_reg_closed_notify(reason)


def _unbind_user(tg_user_id):
    return user_bot_binding_service.unbind_user(tg_user_id)


def _get_binding_by_emby_id(emby_user_id):
    return user_bot_binding_service.get_binding_by_emby_id(emby_user_id)


def _get_binding(tg_user_id):
    return user_bot_binding_service.get_binding(tg_user_id)


def _get_channel_binding(channel_id):
    return user_bot_binding_service.get_channel_binding(channel_id)


def _bind_channel(channel_id, tg_user_id, channel_title=""):
    return user_bot_binding_service.bind_channel(channel_id, tg_user_id, channel_title)


def _unbind_channel(channel_id):
    return user_bot_binding_service.unbind_channel(channel_id)


def _get_all_bindings():
    return user_bot_binding_service.get_all_bindings()


def _record_bot_user(tg_user_id, tg_name=""):
    return user_bot_binding_service.record_bot_user(tg_user_id, tg_name)


def _get_all_bot_users():
    return user_bot_binding_service.get_all_bot_users()


def _bind_user(tg_user_id, emby_user_id, emby_username, init_password="", tg_username="", tg_display_name=""):
    return user_bot_binding_service.bind_user(
        tg_user_id,
        emby_user_id,
        emby_username,
        init_password,
        tg_username,
        tg_display_name,
    )


def _rate_check(tg_user_id, cooldown=3):
    return user_bot_concurrency_service.rate_check(tg_user_id, cooldown=cooldown)


def _is_blacklisted(tg_user_id):
    return user_bot_binding_service.is_blacklisted(tg_user_id)


def _add_to_blacklist(tg_user_id, reason=""):
    return user_bot_binding_service.add_to_blacklist(tg_user_id, reason)


def _check_emby_account(binding):
    return user_bot_binding_service.check_emby_account(binding)


def _get_username_lock(username_lower):
    return user_bot_concurrency_service.get_username_lock(username_lower)

# ==========================================
# 可视化卡片菜单
# ==========================================

def _main_menu_keyboard(binding=None):
    return user_bot_menu_service.main_menu_keyboard(binding)


def cmd_start(chat_id, tg_user_id, tg_name):
    return user_bot_basic_commands_service.cmd_start(chat_id, tg_user_id, tg_name)


def cmd_help(chat_id, tg_user_id):
    return user_bot_basic_commands_service.cmd_help(chat_id, tg_user_id)


def cmd_bind(chat_id, tg_user_id, args, tg_username="", tg_display_name=""):
    return user_bot_basic_commands_service.cmd_bind(
        chat_id,
        tg_user_id,
        args,
        tg_username=tg_username,
        tg_display_name=tg_display_name,
    )


def cmd_register(chat_id, tg_user_id, tg_name):
    return user_bot_basic_commands_service.cmd_register(chat_id, tg_user_id, tg_name)


# ==========================================
# 注册 quota 软预占 / 用户数缓存 / batch_used 落盘
# ==========================================

def _load_batch_used_from_cfg():
    return user_bot_registration_quota_service.load_batch_used_from_cfg()


def _flush_batch_used(force=False):
    return user_bot_registration_quota_service.flush_batch_used(force=force)


def _batch_flush_loop():
    """Compatibility wrapper for the service-owned batch flush loop."""
    # Lifecycle contract retained by service: _batch_flush_stop.wait(BATCH_FLUSH_INTERVAL)
    # Retry backoff contract retained by service: _batch_flush_stop.wait(5)
    return user_bot_registration_quota_service.batch_flush_loop()


def _start_batch_flush_thread():
    return user_bot_registration_quota_service.start_batch_flush_thread(loop_target=_batch_flush_loop)


def _stop_batch_flush_thread():
    return user_bot_registration_quota_service.stop_batch_flush_thread()


def get_batch_used_snapshot():
    return user_bot_registration_quota_service.get_batch_used_snapshot()


def _refresh_user_count_cache_locked(force=False, quota=0):
    return user_bot_registration_quota_service.refresh_user_count_cache_locked(force=force, quota=quota)


def _invalidate_user_count_cache():
    return user_bot_registration_quota_service.invalidate_user_count_cache()


def get_cached_user_count_for_api(force=False):
    return user_bot_registration_quota_service.get_cached_user_count_for_api(force=force)


def get_users_list_cached(max_age=USER_COUNT_CACHE_TTL):
    return user_bot_registration_quota_service.get_users_list_cached(max_age=max_age)


def _reserve_quota_slot(quota_mode, quota):
    return user_bot_registration_quota_service.reserve_quota_slot(quota_mode, quota)


def _release_quota_slot(committed, quota_mode, quota):
    return user_bot_registration_quota_service.release_quota_slot(committed, quota_mode, quota)


def _inc_batch_used(quota):
    return user_bot_registration_quota_service.inc_batch_used(quota)


def _do_register(chat_id, tg_user_id, custom_name, tg_username="", tg_display_name=""):
    """执行注册逻辑"""
    # 🚀 进入注册队列（FIFO 排队，超出 MAX_CONCURRENT_REG 时阻塞等待）
    if not _enter_reg_queue(chat_id):
        return

    reserved = False
    committed = False
    quota_mode = "total"
    quota = 0
    try:
        # 检查开放注册是否开启
        if not is_user_bot_open_reg_enabled():
            _send(chat_id, "❌ 开放注册已关闭，请联系管理员获取注册码后使用 /code 注册码")
            return

        # 🎯 支持两种名额模式
        quota_mode = get_user_bot_reg_quota_mode()
        quota = get_user_bot_reg_quota()

        # 🔒 软预占 quota（在调用 Emby 建号前先占槽，杜绝并发超额）
        if quota > 0:
            ok, reason = _reserve_quota_slot(quota_mode, quota)
            if not ok:
                if reason == "batch_full":
                    _send(chat_id, "❌ 本次开放注册名额已用完，请联系管理员")
                    try:
                        set_user_bot_open_reg_enabled(False)
                    except Exception:
                        pass
                    _send_open_reg_closed_notify("批次名额已满")
                elif reason == "total_full":
                    _send(chat_id, "❌ 用户数量已达上限，开放注册已自动关闭")
                    try:
                        set_user_bot_open_reg_enabled(False)
                    except Exception:
                        pass
                    _send_open_reg_closed_notify("用户总数已达上限")
                else:
                    _send(chat_id, "❌ 暂时无法检查注册名额，请稍后重试")
                return
            reserved = True

        max_reg = get_user_bot_max_reg()
        if max_reg > 0 and quota <= 0:
            try:
                count = user_bot_dao.count_bindings()
                if count >= max_reg:
                    _send(chat_id, "❌ 注册名额已满，请联系管理员")
                    return
            except Exception: pass

        # 验证用户名格式
        # 检查用户名长度限制
        if len(custom_name) > 16:
            _send(chat_id, f"❌ 用户名最多 16 个字符，当前 {len(custom_name)} 个字符")
            return
        
        safe_name = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fa5_\-.@]', '', custom_name)
        
        if safe_name != custom_name:
            invalid_chars = set(re.findall(r'[^a-zA-Z0-9\u4e00-\u9fa5_\-.@]', custom_name))
            invalid_str = ', '.join(f"'{c}'" for c in list(invalid_chars)[:5])
            _send(chat_id, f"❌ 用户名包含不支持的字符: {invalid_str}\n\n只允许字母、数字、中文、下划线(_)、连字符(-)、@ 和 .")
            return
        
        if not safe_name:
            _send(chat_id, "❌ 用户名无效，请使用字母、数字、中文、下划线(_)、连字符(-)、@ 或 .")
            return
        
        password = secrets.token_urlsafe(8)

        # 🚀 获取用户名锁
        username_lock = _get_username_lock(safe_name.lower())
        
        with username_lock:
            try:
                # 优先复用缓存的用户列表（减少 Emby /Users 调用）
                users = get_users_list_cached() or []
                if any(u.get('Name', '').lower() == safe_name.lower() for u in users):
                    # 缓存可能过时，force 拉一次确认
                    with _quota_lock:
                        _refresh_user_count_cache_locked(force=True)
                        users = _user_count_cache.get("users") or []
                    if any(u.get('Name', '').lower() == safe_name.lower() for u in users):
                        _send(chat_id, f"❌ 用户名 <b>{safe_name}</b> 已被占用，请换一个")
                        _user_state[str(tg_user_id)] = {"action": "register_name"}
                        return

                create_res = media_api.post("/Users/New", json={"Name": safe_name}, timeout=10)
                if create_res.status_code not in [200, 201]:
                    _send(chat_id, "❌ 创建账号失败，请稍后重试")
                    return
                new_user = create_res.json()
                uid = new_user.get("Id")
                media_api.post(f"/Users/{uid}/Password", json={"NewPw": password}, timeout=5)

                template_id = get_user_bot_template_user()
                if template_id:
                    try:
                        tpl = media_api.get(f"/Users/{template_id}", timeout=5).json()
                        if tpl.get("Policy"):
                            policy = tpl["Policy"]
                            policy["IsAdministrator"] = False
                            policy["IsDisabled"] = False
                            media_api.post(f"/Users/{uid}/Policy", json=policy, timeout=5)
                    except Exception: pass
                else:
                    try:
                        media_api.post(f"/Users/{uid}/Policy", json={"IsDisabled": False}, timeout=3)
                    except Exception: pass

                reg_days = get_user_bot_reg_days()
                expire = (datetime.date.today() + datetime.timedelta(days=reg_days)).strftime("%Y-%m-%d")

                allow_routes = get_user_bot_allow_routes()
                block_routes = get_user_bot_block_routes()

                if allow_routes or block_routes:
                    user_dao.save_user_expire_routes(uid, expire, allow_routes, block_routes)
                else:
                    template_routes = None
                    if template_id:
                        try:
                            template_meta = user_dao.get_user_routes(template_id)
                            if template_meta and (template_meta.get('allow_routes') or template_meta.get('block_routes')):
                                template_routes = template_meta
                        except Exception: pass

                    if template_routes:
                        user_dao.save_user_expire_routes(uid, expire, template_routes.get('allow_routes', ''), template_routes.get('block_routes', ''))
                    else:
                        user_dao.save_user_expire(uid, expire)

                _bind_user(tg_user_id, uid, safe_name, init_password=password, tg_username=tg_username or tg_display_name, tg_display_name=tg_display_name or str(tg_user_id))

                try:
                    user_bot_dao.create_registration_log(tg_user_id, safe_name, uid, "open")
                except Exception as e:
                    logger.error(f"记录注册日志失败: {e}")

                # ✅ 标记为已提交：finally 中将调用 _release_quota_slot(committed=True, ...)
                committed = True

                _send(chat_id, f"🎉 <b>注册成功！</b>\n\n"
                      f"👤 用户名：<code>{safe_name}</code>\n"
                      f"🔑 密码：<code>{password}</code>\n"
                      f"📅 有效期至：{expire}\n\n"
                      f"💡 密码可在「个人中心」随时查看",
                      reply_markup=_main_menu_keyboard({"emby_user_id": uid, "emby_username": safe_name}))
            except Exception as e:
                logger.error(f"[注册] 执行异常: {e}")
                _send(chat_id, f"❌ 注册异常：{safe_error_message(e, '注册操作异常，请稍后重试')}")
    finally:
        if reserved:
            try:
                _release_quota_slot(committed, quota_mode, quota)
            except Exception:
                logger.exception("[UserBot] 释放 quota 预占失败")
        _leave_reg_queue()


def cmd_check(chat_id, tg_user_id):
    return user_bot_code_commands_service.cmd_check(chat_id, tg_user_id)


def cmd_code(chat_id, tg_user_id, args):
    return user_bot_code_commands_service.cmd_code(chat_id, tg_user_id, args)


def _restore_invitation_code(code):
    return user_bot_code_commands_service.restore_invitation_code(code)


def _invalidate_users_cache_after_code_registration():
    try:
        from app.domains.users import public_service as user_service
        user_service.invalidate_emby_users_cache()
    except:
        pass


def _send_code_registration_notifications(safe_name, days, code, tg_user_id):
    try:
        from app.domains.notifications.bot_service import bot
        from app.infra.db.notification_dao import add_system_notification
        days_display = "永久" if (days == -1 or days == 0 or days >= 36500) else f"{days} 天"
        msg = f"🎟️ <b>新用户注册</b>\n\n👤 {safe_name}\n📅 有效期：{days_display}\n🔗 邀请码：{code}\n📱 注册渠道：TG机器人\n🆔 TG：{tg_user_id}"
        bot.notifier.send_message("sys_notify", msg, platform="all")
        add_system_notification("user", f"新用户注册: {safe_name}", f"TG机器人注册，有效期 {days_display}", "/users_manage")
    except Exception:
        pass


def _do_code_register(chat_id, tg_user_id, custom_name, code, days, tpl_id, routes=None, route_mode=None, tg_username="", tg_display_name=""):
    return user_bot_code_commands_service.do_code_register(
        chat_id,
        tg_user_id,
        custom_name,
        code,
        days,
        tpl_id,
        routes=routes,
        route_mode=route_mode,
        tg_username=tg_username,
        tg_display_name=tg_display_name,
    )


def cmd_renew(chat_id, tg_user_id, args):
    return user_bot_code_commands_service.cmd_renew(chat_id, tg_user_id, args)


def cmd_checkin(chat_id, tg_user_id, msg_id=None, is_group=False, group_name="", user_msg_id=None):
    return user_bot_points_commands_service.cmd_checkin(
        chat_id,
        tg_user_id,
        msg_id=msg_id,
        is_group=is_group,
        group_name=group_name,
        user_msg_id=user_msg_id,
    )


def _delete_messages_later(chat_id, message_ids, delay_seconds=30):
    return user_bot_message_cleanup_service.delete_messages_later(
        chat_id,
        message_ids,
        delay_seconds=delay_seconds,
    )


def cmd_points(chat_id, tg_user_id, msg_id=None, is_group=False):
    return user_bot_points_commands_service.cmd_points(chat_id, tg_user_id, msg_id=msg_id, is_group=is_group)

# ==================== 🔥 新增群聊积分命令 ====================

def cmd_rank(chat_id, tg_user_id, is_group=False):
    return user_bot_points_game_commands_service.cmd_rank(chat_id, tg_user_id, is_group=is_group)

def cmd_rob(chat_id, tg_user_id, text, is_group=False, entities=None):
    return user_bot_points_game_commands_service.cmd_rob(
        chat_id,
        tg_user_id,
        text,
        is_group=is_group,
        entities=entities,
    )

# PK命令代码片段 - 需要追加到 user_bot_service.py


def _handle_pk_accept_callback(chat_id, tg_user_id, invite_id, cq_id, msg_id):
    return user_bot_pk_callback_service._handle_pk_accept_callback(chat_id, tg_user_id, invite_id, cq_id, msg_id)


def _handle_pk_reject_callback(chat_id, tg_user_id, invite_id, cq_id, msg_id):
    return user_bot_pk_callback_service._handle_pk_reject_callback(chat_id, tg_user_id, invite_id, cq_id, msg_id)

def cmd_pk_invite(chat_id, tg_user_id, text, is_group=False, entities=None, user_msg_id=None):
    return user_bot_pk_invitation_commands_service.cmd_pk_invite(
        chat_id,
        tg_user_id,
        text,
        is_group=is_group,
        entities=entities,
        user_msg_id=user_msg_id,
    )

def cmd_pk_accept(chat_id, tg_user_id, text, is_group=False):
    return user_bot_pk_invitation_commands_service.cmd_pk_accept(chat_id, tg_user_id, text, is_group=is_group)

def cmd_pk_reject(chat_id, tg_user_id, text, is_group=False):
    return user_bot_pk_invitation_commands_service.cmd_pk_reject(chat_id, tg_user_id, text, is_group=is_group)

def cmd_transfer(chat_id, tg_user_id, text, is_group=False, entities=None):
    return user_bot_transfer_commands_service.cmd_transfer(
        chat_id,
        tg_user_id,
        text,
        is_group=is_group,
        entities=entities,
    )

def cmd_redpacket(chat_id, tg_user_id, text, is_group=False, tg_name="", user_msg_id=None):
    return user_bot_transfer_commands_service.cmd_redpacket(
        chat_id,
        tg_user_id,
        text,
        is_group=is_group,
        tg_name=tg_name,
        user_msg_id=user_msg_id,
    )

def cmd_pk(chat_id, tg_user_id, text, is_group=False, tg_name="", user_msg_id=None):
    return user_bot_dice_pk_commands_service.cmd_pk(
        chat_id,
        tg_user_id,
        text,
        is_group=is_group,
        tg_name=tg_name,
        user_msg_id=user_msg_id,
    )

def cmd_grab(chat_id, tg_user_id, text, is_group=False, tg_name="", user_msg_id=None):
    return user_bot_game_commands_service.cmd_grab(
        chat_id,
        tg_user_id,
        text,
        is_group=is_group,
        tg_name=tg_name,
        user_msg_id=user_msg_id,
    )

def cmd_lottery(chat_id, tg_user_id, text, is_group=False, user_msg_id=None):
    return user_bot_game_commands_service.cmd_lottery(
        chat_id,
        tg_user_id,
        text,
        is_group=is_group,
        user_msg_id=user_msg_id,
    )

def cmd_scratch(chat_id, tg_user_id, text, is_group=False, tg_name="", user_msg_id=None):
    return user_bot_scratch_commands_service.cmd_scratch(
        chat_id,
        tg_user_id,
        text,
        is_group=is_group,
        tg_name=tg_name,
        user_msg_id=user_msg_id,
    )


def _cmd_scratch_impl(chat_id, tg_user_id, text, is_group=False, tg_name="", user_msg_id=None):
    return user_bot_scratch_commands_service._cmd_scratch_impl(
        chat_id,
        tg_user_id,
        text,
        is_group=is_group,
        tg_name=tg_name,
        user_msg_id=user_msg_id,
    )


def _handle_scratch(chat_id, tg_user_id, card_id, slot_number, tg_name=""):
    return user_bot_scratch_commands_service._handle_scratch(chat_id, tg_user_id, card_id, slot_number, tg_name=tg_name)


def _update_scratch_message(chat_id, msg_id, card_id):
    return user_bot_scratch_commands_service._update_scratch_message(chat_id, msg_id, card_id)


def _scratch_draw_result(chat_id, card_id):
    return user_bot_scratch_commands_service._scratch_draw_result(chat_id, card_id)


def cmd_shop(chat_id, tg_user_id, msg_id=None):
    return user_bot_shop_commands_service.cmd_shop(chat_id, tg_user_id, msg_id=msg_id)


def cmd_redeem_callback(chat_id, tg_user_id, item_id, cq_id):
    return user_bot_shop_commands_service.cmd_redeem_callback(chat_id, tg_user_id, item_id, cq_id)


def cmd_request(chat_id, tg_user_id, args):
    return user_bot_request_commands_service.cmd_request(chat_id, tg_user_id, args)


def cmd_request_callback(chat_id, tg_user_id, media_type, tmdb_id, cq_id):
    return user_bot_request_commands_service.cmd_request_callback(chat_id, tg_user_id, media_type, tmdb_id, cq_id)


def _submit_request(chat_id, tg_user_id, media_type, tmdb_id, season):
    return user_bot_request_commands_service._submit_request(chat_id, tg_user_id, media_type, tmdb_id, season)


# 🔥 追新功能已删除 - 请使用用户社区追新功能

def cmd_myrequests(chat_id, tg_user_id, msg_id=None):
    return user_bot_request_commands_service.cmd_myrequests(chat_id, tg_user_id, msg_id=msg_id)


def cmd_profile(chat_id, tg_user_id, msg_id=None):
    return user_bot_account_commands_service.cmd_profile(chat_id, tg_user_id, msg_id=msg_id)


def cmd_unbind(chat_id, tg_user_id):
    return user_bot_account_commands_service.cmd_unbind(chat_id, tg_user_id)


def cmd_unbind_confirm(chat_id, tg_user_id):
    return user_bot_account_commands_service.cmd_unbind_confirm(chat_id, tg_user_id)


def cmd_bind_channel(chat_id, tg_user_id, args):
    return user_bot_channel_commands_service.cmd_bind_channel(chat_id, tg_user_id, args)


def cmd_unbind_channel(chat_id, tg_user_id, args):
    return user_bot_channel_commands_service.cmd_unbind_channel(chat_id, tg_user_id, args)


def cmd_password(chat_id, tg_user_id, args):
    return user_bot_password_commands_service.cmd_password(chat_id, tg_user_id, args)


def cmd_server(chat_id, tg_user_id, msg_id=None):
    return user_bot_service_info_commands_service.cmd_server(chat_id, tg_user_id, msg_id=msg_id)


def cmd_library(chat_id, tg_user_id, msg_id=None):
    return user_bot_service_info_commands_service.cmd_library(chat_id, tg_user_id, msg_id=msg_id)

def cmd_calendar(chat_id, tg_user_id, msg_id=None):
    return user_bot_service_info_commands_service.cmd_calendar(chat_id, tg_user_id, msg_id=msg_id)


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
        token = get_user_bot_token()
        if not token:
            return
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
        _load_batch_used_from_cfg()
        _start_batch_flush_thread()
        logger.info("🤖 [Pro] 用户 TG 机器人已启动")

    def stop(self):
        self.running = False
        self._stop_event.set()
        # 同步 flush 一次防止丢失增量
        _stop_batch_flush_thread()
        try:
            _flush_batch_used(force=True)
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
        _tg_api("setMyCommands", {"commands": cmds})

    def _polling_loop(self):
        token = get_user_bot_token()
        while self.running and not self._stop_event.is_set():
            try:
                # 使用 long polling，timeout=30 秒
                res = telegram_client.get_updates(token, params={"offset": self.offset, "timeout": 30}, proxies=get_safe_proxies(), timeout=35)
                if res.status_code == 200:
                    updates = res.json().get("result", [])
                    for u in updates:
                        self.offset = u["update_id"] + 1
                        try:
                            if "message" in u:
                                # 使用线程池处理消息，支持排队
                                if not _submit_task(self._on_message, u["message"]):
                                    # 等待队列也满了，提示系统繁忙
                                    chat_id = str(u["message"].get("chat", {}).get("id", ""))
                                    if chat_id:
                                        _send(chat_id, "⏳ 当前请求人数过多，请稍后再试...")
                            elif "callback_query" in u:
                                if not _submit_task(self._on_callback, u["callback_query"]):
                                    # callback 队列满，静默忽略
                                    pass
                        except Exception as e:
                            logger.error(f"[UserBot] 处理消息异常: {e}")
                else:
                    if self._stop_event.wait(3):
                        return
            except Exception as e:
                logger.debug(f"[UserBot] polling 异常: {e}")
                if self._stop_event.wait(5):
                    return

    def _scheduler_loop(self):
        """定时任务循环"""
        if self._stop_event.wait(30):  # 等待服务完全启动
            return
        
        while self.running and not self._stop_event.is_set():
            try:
                # 检查是否需要执行彩票开奖
                config = point_dao.get_point_config()
                
                if int(config.get('enable_lottery', 0)) == 1:
                    draw_hour = int(config.get('lottery_draw_hour', 20))
                    now = datetime.datetime.now()
                    current_hour = now.hour
                    current_minute = now.minute
                    
                    # 检查是否到了开奖时间（整点后5分钟内执行）
                    if current_hour == draw_hour and current_minute < 5:
                        # 检查今天是否已开奖
                        today = now.strftime('%Y-%m-%d')
                        result = point_dao.get_lottery_winning_numbers(today)
                        
                        if not result or not result["winning_numbers"]:
                            logger.info(f"[彩票] 到达开奖时间 {draw_hour}:00，执行自动开奖...")
                            do_lottery_draw()
                
                # 🔥 处理过期的 PK 邀请
                try:
                    # 获取刚过期的邀请（有消息ID的）
                    expired_invites = point_dao.list_expired_pending_pk_invites_with_messages()
                    
                    for invite in expired_invites:
                        invite_id = invite["id"]
                        chat_id = invite["chat_id"]
                        msg_id = invite["message_id"]
                        challenger_name = invite["challenger_tg_name"] or '用户'
                        target_name = invite["target_tg_name"] or '用户'
                        
                        # 编辑消息显示已过期
                        try:
                            _tg_api("editMessageText", {
                                "chat_id": chat_id,
                                "message_id": msg_id,
                                "text": f"⏰ <b>PK邀请已过期</b>\n\n{challenger_name} 向 {target_name} 发起的PK邀请已过期",
                                "parse_mode": "HTML"
                            })
                        except:
                            pass
                        
                        # 更新状态
                        point_dao.mark_pk_invitation_expired(invite_id)
                    
                    if expired_invites:
                        logger.info(f"[PK] 已处理 {len(expired_invites)} 个过期邀请")
                except Exception as e:
                    logger.error(f"[PK] 处理过期邀请失败: {e}")
                
                # 每60秒检查一次
                if self._stop_event.wait(60):
                    return
                
            except Exception as e:
                logger.error(f"[UserBot] 定时任务异常: {e}")
                if self._stop_event.wait(60):
                    return

    def _on_message(self, msg):
        text = (msg.get("text") or "").strip()
        chat = msg.get("chat", {})
        chat_id = str(chat["id"])
        chat_type = chat.get("type", "")
        
        # 🔥 处理频道身份发送的消息
        sender_chat = msg.get("sender_chat")
        from_user = msg.get("from")
        
        # 频道身份发送的消息
        if sender_chat and not from_user:
            channel_id = str(sender_chat["id"])
            channel_title = sender_chat.get("title", "频道")
            logger.info(f"[UserBot] 频道身份消息: channel_id={channel_id}, title={channel_title}, text={text[:50]}")
            
            # 检查频道是否绑定到用户
            channel_binding = _get_channel_binding(channel_id)
            if channel_binding:
                # 使用绑定的用户身份
                tg_user_id = channel_binding["bound_tg_user_id"]
                logger.info(f"[UserBot] 频道绑定用户: tg_user_id={tg_user_id}")
            else:
                # 频道未绑定，提示用户
                _send(chat_id, f"❌ 频道 <b>{channel_title}</b> 未绑定账号\n\n💡 请先私聊机器人发送 /bind_channel {channel_id} 绑定频道")
                return
        else:
            # 普通消息，确保 from 字段存在
            if not from_user:
                logger.info(f"[UserBot] 消息缺少 from 字段，跳过")
                return
            
            tg_user_id = str(from_user["id"])
        
        tg_name = from_user.get("first_name", "用户") if from_user else "频道用户"
        # 获取完整的 TG 显示名称（first_name + last_name）
        tg_last_name = msg["from"].get("last_name", "")
        tg_display_name = f"{tg_name} {tg_last_name}".strip() if tg_last_name else tg_name
        group_name = chat.get("title", "")  # 群名称
        user_msg_id = msg.get("message_id")  # 用户消息ID，用于群聊删除
        entities = msg.get("entities", [])  # 消息实体，用于获取@用户信息

        # 频道消息直接忽略
        if chat_type == "channel":
            return

        if not _rate_check(tg_user_id):
            return

        # ========== 群聊处理 ==========
        if chat_type in ["group", "supergroup"]:
            # 检查群聊功能是否启用
            if not get_user_bot_group_enabled():
                return
            
            # 检查群是否在白名单中
            allowed_groups = get_user_bot_allowed_groups()
            if allowed_groups:
                allowed_list = [g.strip() for g in allowed_groups.split("\n") if g.strip()]
                if chat_id not in allowed_list and f"@{chat.get('username', '')}" not in allowed_list:
                    return  # 不在白名单，忽略
            
            # 获取群内允许的指令
            group_commands = get_user_bot_group_commands()
            allowed_cmds = [c.strip().lower() for c in group_commands.split(",") if c.strip()]
            logger.info(f"[群聊] allowed_cmds={allowed_cmds}, text={text}")
            
            # 解析指令
            cmd = text.split()[0].lower().lstrip("/") if text else ""
            cmd_name = cmd.split("@")[0] if "@" in cmd else cmd  # 处理 /cmd@botname 格式
            logger.info(f"[群聊] cmd={cmd}, cmd_name={cmd_name}")
            
            # 群内只响应白名单指令
            if cmd_name in ["checkin", "签到", "qd"] and "checkin" in allowed_cmds:
                cmd_checkin(chat_id, tg_user_id, is_group=True, group_name=group_name, user_msg_id=user_msg_id)
                return
            elif cmd_name in ["help", "帮助"] and "help" in allowed_cmds:
                result = _send(chat_id, "🤖 <b>群内可用指令</b>\n\n"
                      "✅ /checkin 或 /签到 - 每日签到获取积分\n"
                      "✅ /points 或 /积分 - 查看积分余额\n"
                      "✅ /rank 或 /排行 - 积分排行榜\n"
                      "✅ /transfer 或 /转赠 - 转赠积分\n"
                      "✅ /rob 或 /打劫 - 打劫好友积分\n"
                      "✅ /hb 或 /红包 - 发积分红包\n"
                      "✅ /grab 或 /抢 - 抢红包\n\n"
                      "💡 更多功能请私聊机器人使用")
                # 帮助消息也30秒后删除
                if result and user_msg_id:
                    bot_msg_id = result.get("result", {}).get("message_id")
                    if bot_msg_id:
                        _delete_messages_later(chat_id, [bot_msg_id, user_msg_id], 30)
                return
            elif cmd_name in ["points", "积分", "jf"] and "points" in allowed_cmds:
                result = cmd_points(chat_id, tg_user_id, is_group=True, msg_id=None)
                # 积分查询30秒后删除
                if result and user_msg_id:
                    bot_msg_id = result.get("result", {}).get("message_id")
                    if bot_msg_id:
                        _delete_messages_later(chat_id, [bot_msg_id, user_msg_id], 30)
                return
            # 🔥 新增：排行榜
            elif cmd_name in ["rank", "排行", "ph"] and "rank" in allowed_cmds:
                result = cmd_rank(chat_id, tg_user_id, is_group=True)
                if result and user_msg_id:
                    bot_msg_id = result.get("result", {}).get("message_id")
                    if bot_msg_id:
                        _delete_messages_later(chat_id, [bot_msg_id, user_msg_id], 30)
                return
            # 🔥 新增：转赠
            elif cmd_name in ["transfer", "转赠", "zz"] and "transfer" in allowed_cmds:
                cmd_transfer(chat_id, tg_user_id, text, is_group=True, entities=entities)
                return
            # 🔥 新增：打劫
            elif cmd_name in ["rob", "打劫", "dj"] and "rob" in allowed_cmds:
                cmd_rob(chat_id, tg_user_id, text, is_group=True, entities=entities)
                return
            # 🔥 用户PK命令
            elif cmd_name in ["upk", "用户pk"] and "upk" in allowed_cmds:
                cmd_pk_invite(chat_id, tg_user_id, text, is_group=True, entities=entities, user_msg_id=user_msg_id)
                return
            # 🔥 新增：红包
            elif cmd_name in ["hb", "红包", "redpacket"] and "redpacket" in allowed_cmds:
                cmd_redpacket(chat_id, tg_user_id, text, is_group=True, tg_name=tg_display_name, user_msg_id=user_msg_id)
                return
            # 🔥 新增：抢红包
            elif cmd_name in ["grab", "抢", "q"] and "grab" in allowed_cmds:
                cmd_grab(chat_id, tg_user_id, text, is_group=True, tg_name=tg_display_name, user_msg_id=user_msg_id)
                return
            # 🔥 新增：PK
            elif cmd_name in ["pk", "PK", "骰子", "tz"] and "pk" in allowed_cmds:
                cmd_pk(chat_id, tg_user_id, text, is_group=True, tg_name=tg_display_name, user_msg_id=user_msg_id)
                return
            # 🔥 新增：彩票
            elif cmd_name in ["lottery", "彩票", "cp"] and "lottery" in allowed_cmds:
                logger.info(f"[彩票] 群聊命令匹配成功，调用 cmd_lottery")
                cmd_lottery(chat_id, tg_user_id, text, is_group=True, user_msg_id=user_msg_id)
                return
            # 🔥 新增：刮刮乐
            elif cmd_name in ["scratch", "刮刮乐", "ggl"] and "scratch" in allowed_cmds:
                cmd_scratch(chat_id, tg_user_id, text, is_group=True, tg_name=tg_display_name, user_msg_id=user_msg_id)
                return
            else:
                # 处理新成员入群欢迎
                if "new_chat_members" in msg:
                    self._on_new_chat_members(chat_id, msg.get("new_chat_members", []), group_name)
                    return
                # 其他消息忽略
                return

        # ========== 私聊处理（原有逻辑）==========
        binding = _get_binding(tg_user_id)

        # 🔥 /check 命令用于手动刷新限制检查（在限制检查之前处理）
        if text.startswith("/check") or text.startswith("/验证"):
            cmd_check(chat_id, tg_user_id)
            return

        # 🔥 所有其他命令都需要检查使用限制
        restriction_check = _check_user_restrictions(tg_user_id)
        if not restriction_check["passed"]:
            _send(chat_id, _format_restriction_message(restriction_check))
            return

        # 未绑定用户只能执行这些命令
        if text.startswith("/start"): cmd_start(chat_id, tg_user_id, tg_name); return
        if text.startswith("/help") or text.startswith("/帮助"): cmd_help(chat_id, tg_user_id); return
        if text.startswith("/menu") or text.startswith("/菜单"): cmd_start(chat_id, tg_user_id, tg_name); return
        # 🔥 bind_channel 要在 bind 前面，避免被 bind 匹配
        if text.startswith("/bind_channel"): cmd_bind_channel(chat_id, tg_user_id, text.split(None, 1)[1] if len(text.split()) > 1 else ""); return
        if text.startswith("/bind") or text.startswith("/绑定"): cmd_bind(chat_id, tg_user_id, text.split(None, 1)[1] if len(text.split()) > 1 else "", tg_username=msg["from"].get("username", ""), tg_display_name=tg_display_name); return
        if text.startswith("/register") or text.startswith("/注册"): cmd_register(chat_id, tg_user_id, tg_name); return
        if text.startswith("/code") or text.startswith("/注册码"): cmd_code(chat_id, tg_user_id, text.split(None, 1)[1] if len(text.split()) > 1 else ""); return

        # 以下功能需要绑定
        if not binding:
            # 先检查是否有待处理的注册状态（用户正在输入用户名）
            state = _user_state.get(tg_user_id)
            if state and state.get("action") == "register_name" and not text.startswith('/'):
                del _user_state[tg_user_id]
                _do_register(chat_id, tg_user_id, text, tg_username=msg["from"].get("username", ""), tg_display_name=tg_display_name)
                return
            # 检查注册码激活时输入用户名的状态
            if state and state.get("action") == "code_input_name" and not text.startswith('/'):
                del _user_state[tg_user_id]
                _do_code_register(chat_id, tg_user_id, text, state.get("code"), state.get("days"), state.get("tpl_id"), state.get("routes"), state.get("route_mode"), tg_username=msg["from"].get("username", ""), tg_display_name=tg_display_name)
                return
            _send(chat_id, "🔒 请先绑定或注册账号后才能使用此功能", reply_markup=_main_menu_keyboard(None))
            return

        # 检查 Emby 账号是否还存在
        if not _check_emby_account(binding):
            _unbind_user(tg_user_id)
            _send(chat_id, "⚠️ 你的 Emby 账号已被管理员删除，绑定已自动解除。", reply_markup=_main_menu_keyboard(None))
            return

        # 🔥 unbind_channel 要在 unbind 前面
        if text.startswith("/unbind_channel"): cmd_unbind_channel(chat_id, tg_user_id, text.split(None, 1)[1] if len(text.split()) > 1 else ""); return
        if text.startswith("/unbind") or text.startswith("/解绑"): cmd_unbind(chat_id, tg_user_id); return
        if text.startswith("/profile") or text.startswith("/个人中心"): cmd_profile(chat_id, tg_user_id); return
        if text.startswith("/renew") or text.startswith("/续期"): cmd_renew(chat_id, tg_user_id, text.split(None, 1)[1] if len(text.split()) > 1 else ""); return
        if text.startswith("/checkin") or text.startswith("/签到"): cmd_checkin(chat_id, tg_user_id); return
        if text.startswith("/calendar") or text.startswith("/今日更新"): cmd_calendar(chat_id, tg_user_id); return
        if text.startswith("/points") or text.startswith("/积分"): cmd_points(chat_id, tg_user_id); return
        if text.startswith("/shop") or text.startswith("/商城"): cmd_shop(chat_id, tg_user_id); return
        if text.startswith("/request") or text.startswith("/求片"): cmd_request(chat_id, tg_user_id, text.split(None, 1)[1] if len(text.split()) > 1 else ""); return
        if text.startswith("/myrequests") or text.startswith("/我的求片"): cmd_myrequests(chat_id, tg_user_id); return
        if text.startswith("/server") or text.startswith("/服务器"): cmd_server(chat_id, tg_user_id); return
        if text.startswith("/library") or text.startswith("/媒体库"): cmd_library(chat_id, tg_user_id); return
        if text.startswith("/password") or text.startswith("/密码"): cmd_password(chat_id, tg_user_id, text.split(None, 1)[1] if len(text.split()) > 1 else ""); return
        # 和机器人PK（掷骰子比大小）
        if text.startswith("/pk ") or text.startswith("/PK "): cmd_pk(chat_id, tg_user_id, text, tg_name=tg_display_name); return
        if text.startswith("/骰子") or text.startswith("/tz"): cmd_pk(chat_id, tg_user_id, text, tg_name=tg_display_name); return
        # 用户PK（挑战其他用户）
        if text.startswith("/upk") or text.startswith("/用户pk") or text.startswith("/用户PK"): cmd_pk_invite(chat_id, tg_user_id, text, entities=entities); return
        if text.startswith("/lottery") or text.startswith("/彩票") or text.startswith("/cp"): cmd_lottery(chat_id, tg_user_id, text); return
        if text.startswith("/scratch") or text.startswith("/刮刮乐") or text.startswith("/ggl"): cmd_scratch(chat_id, tg_user_id, text, tg_name=tg_display_name); return
        if text.startswith("/rob") or text.startswith("/打劫") or text.startswith("/dj"): cmd_rob(chat_id, tg_user_id, text, entities=entities); return
        # 🔥 用户PK命令
        if text.startswith("/upk") or text.startswith("/用户pk") or text.startswith("/用户PK"): cmd_pk_invite(chat_id, tg_user_id, text, entities=entities); return
        if text.startswith("/accept") or text.startswith("/接受"): cmd_pk_accept(chat_id, tg_user_id, text); return
        if text.startswith("/reject") or text.startswith("/拒绝"): cmd_pk_reject(chat_id, tg_user_id, text); return

        # 非命令消息
        if not text.startswith('/'):
            # 检查是否有待处理的会话状态
            state = _user_state.get(tg_user_id)
            if state and state.get("action") == "register_name":
                del _user_state[tg_user_id]
                _do_register(chat_id, tg_user_id, text, tg_username=msg["from"].get("username", ""), tg_display_name=tg_display_name)
                return
            _send(chat_id, "💡 请从菜单中选择服务，或发送 /help 查看命令列表", reply_markup=_main_menu_keyboard(binding))

    def _on_callback(self, cq):
        data = cq.get("data", "")
        chat_id = str(cq["message"]["chat"]["id"])
        msg_id = cq["message"]["message_id"]
        tg_user_id = str(cq["from"]["id"])
        tg_name = cq["from"].get("first_name", "用户")
        cq_id = cq["id"]

        if not _rate_check(tg_user_id, cooldown=1):
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id})
            return

        # 🔥 所有按钮都需要检查使用限制
        restriction_check = _check_user_restrictions(tg_user_id)
        if not restriction_check["passed"]:
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id, "text": "请先关注频道/加入群聊", "show_alert": True})
            _send(chat_id, _format_restriction_message(restriction_check))
            return

        binding = _get_binding(tg_user_id)

        # 未绑定用户的菜单按钮
        if data == "ub_menu_bind":
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id})
            _edit(chat_id, msg_id, "📝 <b>绑定账号</b>\n\n请发送命令（用户名和密码用空格隔开）：\n<code>/bind 用户名 密码</code>\n\n⚠️ 密码仅用于验证身份，不会被存储",
                  reply_markup={"inline_keyboard": [[{"text": "🔙 返回", "callback_data": "ub_back_menu"}]]})
            return
        if data == "ub_menu_register":
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id})
            cmd_register(chat_id, tg_user_id, tg_name)
            return
        if data == "ub_menu_code":
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id})
            _edit(chat_id, msg_id, "🎟️ <b>注册码激活</b>\n\n请发送命令：\n<code>/code 你的注册码</code>",
                  reply_markup={"inline_keyboard": [[{"text": "🔙 返回", "callback_data": "ub_back_menu"}]]})
            return
        if data == "ub_back_menu":
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id})
            _user_state.pop(tg_user_id, None)
            binding = _get_binding(tg_user_id)
            if binding:
                _edit(chat_id, msg_id, f"👋 欢迎回来，<b>{binding['emby_username']}</b>！\n\n🎬 EmbyPulse 用户自助服务\n请选择你需要的服务：", reply_markup=_main_menu_keyboard(binding))
            else:
                _edit(chat_id, msg_id, f"👋 你好 <b>{tg_name}</b>！\n\n🎬 这是 <b>EmbyPulse</b> 用户自助服务机器人\n\n请先完成绑定或注册：", reply_markup=_main_menu_keyboard(None))
            return
        if data == "ub_cancel_state":
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id, "text": "已取消"})
            _user_state.pop(tg_user_id, None)
            binding = _get_binding(tg_user_id)
            _edit(chat_id, msg_id, "❌ 已取消操作", reply_markup=_main_menu_keyboard(binding))
            return

        # 媒体库统计 - 不需要绑定即可访问
        if data == "ub_menu_library":
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id})
            cmd_library(chat_id, tg_user_id, msg_id=msg_id)
            return
        
        # 服务器状态 - 不需要绑定即可访问
        if data == "ub_menu_server":
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id, "text": "检测中..."})
            cmd_server(chat_id, tg_user_id, msg_id=msg_id)
            return

        # 以下按钮需要绑定
        if not binding:
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id, "text": "请先绑定账号", "show_alert": True})
            return

        # 检查 Emby 账号是否还存在
        if not _check_emby_account(binding):
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id})
            _unbind_user(tg_user_id)
            _edit(chat_id, msg_id, "⚠️ 你的 Emby 账号已被管理员删除，绑定已自动解除。", reply_markup=_main_menu_keyboard(None))
            return

        if data == "ub_menu_checkin":
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id, "text": "签到中..."})
            cmd_checkin(chat_id, tg_user_id, msg_id=msg_id)
        elif data == "ub_menu_points":
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id})
            cmd_points(chat_id, tg_user_id, msg_id=msg_id)
        elif data == "ub_menu_profile":
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id})
            cmd_profile(chat_id, tg_user_id, msg_id=msg_id)
        elif data == "ub_menu_shop":
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id})
            cmd_shop(chat_id, tg_user_id, msg_id=msg_id)
        elif data == "ub_menu_request":
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id})
            _edit(chat_id, msg_id, "🎬 <b>求片功能</b>\n\n请发送命令：\n<code>/request 影视名称</code>\n\n例如：<code>/request 沙丘</code>",
                  reply_markup={"inline_keyboard": [[{"text": "🔙 返回", "callback_data": "ub_back_menu"}]]})
        elif data == "ub_menu_password":
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id})
            _edit(chat_id, msg_id, "🔐 <b>修改密码</b>\n\n请发送命令（当前密码和新密码用空格隔开）：\n<code>/password 当前密码 新密码</code>\n\n例如：<code>/password 当前密码 NewPass1</code>\n\n⚠️ 新密码至少 8 位，需包含小写字母 + 大写字母或数字",
                  reply_markup={"inline_keyboard": [[{"text": "🔙 返回", "callback_data": "ub_back_menu"}]]})
        elif data == "ub_menu_renew":
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id})
            _edit(chat_id, msg_id, "🎟️ <b>续期功能</b>\n\n请发送命令：\n<code>/renew 你的续期码</code>",
                  reply_markup={"inline_keyboard": [[{"text": "🔙 返回", "callback_data": "ub_back_menu"}]]})
        elif data == "ub_menu_unbind":
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id})
            _edit(chat_id, msg_id, f"🔓 <b>确认解绑？</b>\n\n当前绑定：<b>{binding['emby_username']}</b>\n\n解绑后将无法使用签到、商城等功能。",
                  reply_markup={"inline_keyboard": [
                      [{"text": "✅ 确认解绑", "callback_data": "ub_unbind_confirm"}, {"text": "❌ 取消", "callback_data": "ub_back_menu"}]
                  ]})
        elif data == "ub_unbind_confirm":
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id, "text": "已解绑"})
            _unbind_user(tg_user_id)
            _add_to_blacklist(tg_user_id, "用户主动解绑")
            _edit(chat_id, msg_id, "✅ 已成功解绑账号。\n\n如需重新使用，请联系管理员或使用注册码注册。", reply_markup=_main_menu_keyboard(None))
        # 🔥 用户PK回调
        elif data.startswith("pk_accept:"):
            invite_id = data.split(":")[1]
            _handle_pk_accept_callback(chat_id, tg_user_id, invite_id, cq_id, msg_id)
        elif data.startswith("pk_reject:"):
            invite_id = data.split(":")[1]
            _handle_pk_reject_callback(chat_id, tg_user_id, invite_id, cq_id, msg_id)
        # 商城兑换
        elif data.startswith("ub_redeem_"):
            item_id = data.replace("ub_redeem_", "")
            cmd_redeem_callback(chat_id, tg_user_id, item_id, cq_id)
        # 求片选择
        elif data.startswith("ub_req_"):
            parts = data.split("_")
            if len(parts) >= 4:
                media_type = parts[2]
                tmdb_id = parts[3]
                cmd_request_callback(chat_id, tg_user_id, media_type, tmdb_id, cq_id)
        # 求片选季
        elif data.startswith("ub_reqsn_"):
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id, "text": "提交中..."})
            parts = data.split("_")
            # 格式: ub_reqsn_TMDBID_SEASON，需要4个部分
            if len(parts) >= 4:
                try:
                    tmdb_id = parts[2]
                    season = int(parts[3])
                    # 验证季数必须大于0
                    if season > 0:
                        _submit_request(chat_id, tg_user_id, "tv", tmdb_id, season)
                    else:
                        _send(chat_id, "❌ 无效的季数选择")
                except (ValueError, IndexError):
                    _send(chat_id, "❌ 求片参数错误，请重新选择")
        # 我的求片
        elif data == "ub_menu_myrequests":
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id})
            cmd_myrequests(chat_id, tg_user_id, msg_id=msg_id)
        # 🔥 刮刮乐
        elif data.startswith("scratch_"):
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id})
            parts = data.split("_")
            # scratch_{card_id}_{slot_number} 或 scratch_done_{card_id}_{slot_number}
            if len(parts) >= 3:
                if parts[1] == "done":
                    # 已刮的格子，提示用户
                    _send(chat_id, "❌ 这个格子已经被刮过了")
                else:
                    card_id = int(parts[1])
                    slot_number = int(parts[2])
                    _handle_scratch(chat_id, tg_user_id, card_id, slot_number, tg_name)
        else:
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id})

    def _on_new_chat_members(self, chat_id, new_members, group_name):
        """处理新成员入群"""
        for member in new_members:
            # 检查是否是机器人自己被加入群
            if member.get("is_bot") and str(member.get("id")) == str(get_user_bot_token().split(":")[0] if ":" in get_user_bot_token() else ""):
                # 机器人被加入群，发送欢迎消息
                welcome_msg = get_user_bot_welcome_msg()
                if welcome_msg:
                    _send(chat_id, welcome_msg)
                else:
                    _send(chat_id, f"👋 你好！我是 EmbyPulse 用户机器人，已加入 <b>{group_name}</b>\n\n"
                          "✅ 发送 /checkin 或 /签到 获取积分\n"
                          "✅ 发送 /help 查看群内可用指令\n\n"
                          "💡 更多功能请私聊机器人使用")
                break


user_bot = UserBot()


def start_user_bot_services():
    _ensure_user_bot_tables()
    if get_user_bot_token():
        user_bot.start()

def do_lottery_draw():
    """执行彩票开奖（由定时任务调用）"""
    try:
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        draw_context = point_dao.get_lottery_draw_context(today)
        if draw_context["already_drawn"]:
            logger.info(f"[彩票] 今天已开奖: {draw_context['winning_numbers']}")
            return
        
        # 生成中奖号码
        winning_numbers = ''.join([str(random.randint(0, 9)) for _ in range(4)])

        total_pool = draw_context["total_pool"]
        raw_tickets = draw_context["tickets"]

        # 过滤已删除的账号
        tickets = []
        for ticket in raw_tickets:
            ticket_id = ticket["id"]
            user_id = ticket["user_id"]
            username = ticket["username"]
            numbers = ticket["numbers"]
            try:
                user_info = media_api.get(f"/Users/{user_id}", timeout=3)
                if user_info.status_code == 200:
                    tickets.append((ticket_id, user_id, username, numbers))
                else:
                    logger.warning(f"[彩票] 用户 {user_id}({username}) 已被删除，跳过")
            except:
                tickets.append((ticket_id, user_id, username, numbers))  # 检查失败时保留
        
        if not tickets:
            logger.info(f"[彩票] 今天没有彩票，跳过开奖")
            return
        
        # 计算中奖
        winners = {1: [], 2: [], 3: [], 4: []}  # 一等奖、二等奖、三等奖、安慰奖
        
        for ticket_id, user_id, username, numbers in tickets:
            # 计算匹配位数
            match_count = sum(1 for i in range(4) if numbers[i] == winning_numbers[i])
            
            if match_count == 4:
                winners[1].append((ticket_id, user_id, username))
            elif match_count == 3:
                winners[2].append((ticket_id, user_id, username))
            elif match_count == 2:
                # 检查是否连续
                if numbers[0:2] == winning_numbers[0:2] or numbers[1:3] == winning_numbers[1:3] or numbers[2:4] == winning_numbers[2:4]:
                    winners[3].append((ticket_id, user_id, username))
                else:
                    winners[4].append((ticket_id, user_id, username))
        
        # 🔥 奖池分配比例（从配置读取）
        config = point_dao.get_point_config()
        prize_pool_ratios = {
            1: int(config.get('lottery_pool_ratio_1', 50)) / 100,  # 一等奖
            2: int(config.get('lottery_pool_ratio_2', 20)) / 100,  # 二等奖
            3: int(config.get('lottery_pool_ratio_3', 10)) / 100,  # 三等奖
            4: int(config.get('lottery_pool_ratio_4', 5)) / 100,   # 安慰奖
        }
        
        # 🔥 幸运奖配置
        lucky_count = int(config.get('lottery_lucky_count', 0))  # 幸运奖人数
        lucky_ratio = int(config.get('lottery_lucky_ratio', 5)) / 100  # 幸运奖奖池比例
        
        # 计算每个奖项的总奖金池
        prize_pools = {}
        for level, ratio in prize_pool_ratios.items():
            prize_pools[level] = int(total_pool * ratio)
        
        # 🔥 幸运奖奖池
        if lucky_count > 0:
            prize_pools[5] = int(total_pool * lucky_ratio)  # 幸运奖用 key=5
        
        winners_by_level = {
            level: [
                {"ticket_id": ticket_id, "user_id": user_id, "username": username, "prize_amount": prize_pools[level] // len(winner_list) if prize_pools[level] > 0 else 0}
                for ticket_id, user_id, username in winner_list
            ]
            for level, winner_list in winners.items()
        }

        for level, winner_list in winners.items():
            if not winner_list or prize_pools[level] <= 0:
                continue
            
            # 每人奖金 = 该奖项奖池 / 中奖人数
            prize_per_person = prize_pools[level] // len(winner_list)
            if prize_per_person <= 0:
                prize_per_person = 1  # 最低1积分
            for winner in winners_by_level[level]:
                winner["prize_amount"] = prize_per_person
        
        # 🔥 幸运奖抽取（从所有购买彩票的人中随机抽取）
        lucky_winners = []
        if lucky_count > 0 and len(tickets) > 0 and prize_pools.get(5, 0) > 0:
            # 去重：每个用户只能中一次幸运奖
            unique_users = {}
            for ticket_id, user_id, username, numbers in tickets:
                if user_id not in unique_users:
                    unique_users[user_id] = (ticket_id, username)
            
            # 随机抽取
            user_list = list(unique_users.items())
            actual_lucky_count = min(lucky_count, len(user_list))
            if actual_lucky_count > 0:
                lucky_selected = random.sample(user_list, actual_lucky_count)
                prize_per_lucky = prize_pools[5] // actual_lucky_count
                if prize_per_lucky <= 0:
                    prize_per_lucky = 1
                
                for user_id, (ticket_id, username) in lucky_selected:
                    lucky_winners.append({"ticket_id": ticket_id, "user_id": user_id, "username": username, "prize_amount": prize_per_lucky})
                    logger.info(f"[彩票] 幸运奖: {username} 获得 {prize_per_lucky} 积分")

        # 计算剩余奖池并累积到下期
        total_distributed = 0
        for level, winner_list in winners.items():
            if winner_list and level in prize_pools and prize_pools[level] > 0:
                total_distributed += prize_pools[level]
        if lucky_winners and prize_pools.get(5, 0) > 0:
            total_distributed += prize_pools[5]

        remaining_pool = total_pool - total_distributed
        if remaining_pool < 0:
            remaining_pool = 0

        save_result = point_dao.save_lottery_draw_result(today, winning_numbers, winners_by_level, lucky_winners, remaining_pool)
        if save_result.get("status") != "success":
            logger.info(f"[彩票] 开奖已跳过: {save_result}")
            return

        logger.info(f"[彩票] 开奖完成: {winning_numbers}, 奖池: {total_pool}, 中奖人数: {sum(len(w) for w in winners_by_level.values())}")
        
        # 🔥 发送开奖结果到群
        # 获取允许彩票的群
        allowed_groups = get_user_bot_allowed_groups()
        logger.info(f"[彩票] 允许的群: {allowed_groups}")
        if allowed_groups:
            group_list = [g.strip() for g in allowed_groups.split("\n") if g.strip()]
            logger.info(f"[彩票] 群列表: {group_list}")
            
            # 构建开奖消息
            msg = f"🎰 <b>彩票开奖结果</b> ({today})\n\n"
            msg += f"🎲 中奖号码: <b>{winning_numbers}</b>\n"
            msg += f"💰 奖池: {total_pool} 积分\n\n"
            
            total_winners = sum(len(w) for w in winners_by_level.values()) + len(lucky_winners)
            if total_winners > 0:
                msg += "🏆 中奖名单:\n"
                level_names = {1: "一等奖", 2: "二等奖", 3: "三等奖", 4: "安慰奖"}
                for level, winner_list in winners_by_level.items():
                    if winner_list:
                        # 计算每人奖金
                        prize_per_person = prize_pools[level] // len(winner_list) if prize_pools[level] > 0 else 0
                        for winner in winner_list:
                            user_id = winner["user_id"]
                            emby_username = winner["username"]
                            # 获取TG名称
                            binding = _get_binding_by_emby_id(user_id)
                            display = ''
                            if binding and binding.get('tg_user_id'):
                                tg_name = user_bot_dao.get_bot_user_name(binding['tg_user_id'])
                                if tg_name:
                                    display = f"<a href='tg://user?id={binding['tg_user_id']}'>{tg_name}</a>"
                            # fallback: 显示 emby 用户名
                            if not display:
                                display = emby_username or f"用户{user_id}"
                            msg += f"• {display} - {level_names[level]} (+{winner['prize_amount']}积分)\n"
                if lucky_winners:
                    for winner in lucky_winners:
                        user_id = winner["user_id"]
                        emby_username = winner["username"]
                        amount = winner["prize_amount"]
                        binding = _get_binding_by_emby_id(user_id)
                        display = ''
                        if binding and binding.get('tg_user_id'):
                            tg_name = user_bot_dao.get_bot_user_name(binding['tg_user_id'])
                            if tg_name:
                                display = f"<a href='tg://user?id={binding['tg_user_id']}'>{tg_name}</a>"
                        # fallback: 显示 emby 用户名
                        if not display:
                            display = emby_username or f"用户{user_id}"
                        msg += f"• {display} - 幸运奖 (+{amount}积分)\n"
            else:
                msg += "😢 本期无人中奖，奖池累积到下期\n"
            
            msg += f"\n💡 发送 /彩票 奖池 查看当前奖池"
            msg += f"\n📊 剩余奖池: {remaining_pool} 积分已累积到下期"
            
            # 发送到所有允许的群
            for group_id in group_list:
                try:
                    logger.info(f"[彩票] 尝试发送到群: {group_id}")
                    result = _send(group_id, msg)
                    logger.info(f"[彩票] 发送结果: {result}")
                except Exception as e:
                    logger.error(f"[彩票] 发送开奖结果到群 {group_id} 失败: {e}")
        
        return {"status": "success", "winning_numbers": winning_numbers, "total_pool": total_pool}
        
    except Exception as e:
        logger.error(f"[彩票] 开奖失败: {e}")
        return {"status": "error", "message": str(e)}
