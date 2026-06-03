import threading
import time
import datetime
import logging
import urllib.parse
import json 
import re
from concurrent.futures import ThreadPoolExecutor
from app.core.config import REPORT_COVER_URL, FALLBACK_IMAGE_URL
from app.infra.db.notification_dao import add_system_notification
from app.domains.media_requests import gap_dao, media_request_dao
from app.domains.media_requests.public_service import remove_gap_from_scan_state
from app.domains.users import user_bot_dao
from app.domains.notifications import bot_service_dao, message_dao
from app.domains.notifications import notification_bot_auto_finish_request_service
from app.domains.notifications import notification_bot_callback_dispatcher_service
from app.domains.notifications import notification_bot_channel_service
from app.domains.notifications import notification_bot_check_command_service
from app.domains.notifications import notification_bot_command_registration_service
from app.domains.notifications import notification_bot_delivery_service
from app.domains.notifications import notification_bot_emby_restart_command_service
from app.domains.notifications import notification_bot_feedback_callback_service
from app.domains.notifications import notification_bot_fresh_episode_service
from app.domains.notifications import notification_bot_gap_clear_service
from app.domains.notifications import notification_bot_info_command_service
from app.domains.notifications import notification_bot_item_deleted_service
from app.domains.notifications import notification_bot_library_group_service
from app.domains.notifications import notification_bot_library_queue_service
from app.domains.notifications import notification_bot_library_new_episode_service
from app.domains.notifications import notification_bot_library_new_item_service
from app.domains.notifications import notification_bot_library_push_service
from app.domains.notifications import notification_bot_latest_command_service
from app.domains.notifications import notification_bot_message_dispatch_service
from app.domains.notifications import notification_bot_message_center_callback_service
from app.domains.notifications import notification_bot_media_helper_service
from app.domains.notifications import notification_bot_media_quality_service
from app.domains.notifications import notification_bot_pending_sync_service
from app.domains.notifications import notification_bot_playback_event_service
from app.domains.notifications import notification_bot_playback_command_service
from app.domains.notifications import notification_bot_plugin_callback_service
from app.domains.notifications import notification_bot_polling_service
from app.domains.notifications import notification_bot_request_admin_message_sync_service
from app.domains.notifications import notification_bot_request_approval_action_callback_service
from app.domains.notifications import notification_bot_request_approval_menu_callback_service
from app.domains.notifications import notification_bot_request_hdhive_search_callback_service
from app.domains.notifications import notification_bot_risk_alert_service
from app.domains.notifications import notification_bot_risk_ban_callback_service
from app.domains.notifications import notification_bot_search_command_service
from app.domains.notifications import notification_bot_stats_command_service
from app.domains.notifications import notification_bot_user_expiration_service
from app.domains.notifications import notification_bot_user_login_service
from app.domains.notifications import notification_bot_wecom_service
from app.domains.notifications import notification_bot_webhook_event_service
from app.domains.notifications import notification_bot_whois_command_service
from app.domains.notifications import notify_admin_dao, notify_rule_dao
from app.infra.db.playback_filters import get_base_filter
from app.domains.users import user_dao
from app.infra.db.local_playback_store import insert_bot_playback_history_record
from app.infra.db.playback_store import playback_store
from app.infra.clients.media_server_client import media_api
from app.infra.clients.moviepilot_client import moviepilot_client
from app.infra.clients.network_client import network_client
from app.infra.clients.telegram_client import telegram_client
from app.infra.clients.wecom_client import wecom_client
from app.infra.clients.tmdb_client import tmdb_client
from app.domains.playback import stats_queries
from app.domains.reports.report_service import report_gen, HAS_PIL
from app.utils.proxy_helper import get_safe_proxies, get_safe_wecom_base  # 🔒 SSRF 安全代理读取
from app.core.event_bus import bus
from app.infra.config.bot_settings import (
    get_bot_worker_count,
    get_library_notify_queue_max,
    get_tg_bot_token as get_bot_tg_token,
    get_tg_chat_id,
)
from app.infra.config.media_server_settings import (
    get_media_server_api_key,
    get_media_server_host,
    get_media_server_main_public_or_host,
    get_media_server_public_url,
)
from app.infra.config.moviepilot_settings import get_moviepilot_token, get_moviepilot_url
from app.infra.config.notification_settings import (
    get_enable_library_notify,
    get_enable_notify,
    get_library_notify_channels,
    get_notify_channels,
    get_notify_item_deleted,
    get_notify_user_login,
    get_pulse_url,
    get_tg_bot_token as get_notify_tg_bot_token,
    get_wecom_agentid,
    get_wecom_corpid,
    get_wecom_corpsecret,
    get_wecom_touser,
)
# 🔥 引入共享 IP 归属地工具
from app.utils.ip_location import get_location, get_isp

logger = logging.getLogger("uvicorn")

_BOT_WORKER_COUNT = get_bot_worker_count()
_bot_executor = ThreadPoolExecutor(max_workers=_BOT_WORKER_COUNT, thread_name_prefix="notify-bot")
_bot_executor_slots = threading.BoundedSemaphore(_BOT_WORKER_COUNT * 4)

notification_bot_request_admin_message_sync_service.set_dependency_providers(
    bot_service_dao_provider=lambda: bot_service_dao,
    telegram_client_provider=lambda: telegram_client,
    logger_provider=lambda: logger,
)

notification_bot_media_quality_service.set_dependency_providers(
    media_api_provider=lambda: media_api,
    logger_provider=lambda: logger,
    admin_id_provider=lambda: get_admin_id,
)

notification_bot_channel_service.set_dependency_providers(
    notify_channels_provider=lambda: get_notify_channels,
    tg_bot_token_provider=lambda: get_notify_tg_bot_token,
    safe_proxies_provider=lambda: get_safe_proxies,
    telegram_client_provider=lambda: telegram_client,
    logger_provider=lambda: logger,
)

notification_bot_wecom_service.set_dependency_providers(
    wecom_corpid_provider=lambda: get_wecom_corpid,
    wecom_corpsecret_provider=lambda: get_wecom_corpsecret,
    wecom_agentid_provider=lambda: get_wecom_agentid,
    safe_wecom_base_provider=lambda: get_safe_wecom_base,
    pulse_url_provider=lambda: get_pulse_url,
    media_server_main_public_or_host_provider=lambda: get_media_server_main_public_or_host,
    media_server_host_provider=lambda: get_media_server_host,
    media_server_api_key_provider=lambda: get_media_server_api_key,
    wecom_client_provider=lambda: wecom_client,
    media_api_provider=lambda: media_api,
    report_cover_url_provider=lambda: REPORT_COVER_URL,
    logger_provider=lambda: logger,
    time_provider=lambda: time,
)

notification_bot_delivery_service.set_dependency_providers(
    network_client_provider=lambda: network_client,
    telegram_client_provider=lambda: telegram_client,
    safe_proxies_provider=lambda: get_safe_proxies,
    tg_bot_token_provider=lambda: get_notify_tg_bot_token,
    tg_chat_id_provider=lambda: get_tg_chat_id,
    wecom_corpid_provider=lambda: get_wecom_corpid,
    wecom_touser_provider=lambda: get_wecom_touser,
    submit_bot_task_provider=lambda: _submit_bot_task,
    extract_request_tmdb_id_provider=lambda: _extract_request_tmdb_id,
    record_request_admin_message_provider=lambda: _record_request_admin_message,
    logger_provider=lambda: logger,
)

notification_bot_media_helper_service.set_dependency_providers(
    media_api_provider=lambda: media_api,
    get_isp_provider=lambda: get_isp,
    insert_playback_history_provider=lambda: insert_bot_playback_history_record,
    logger_provider=lambda: logger,
)

notification_bot_message_center_callback_service.set_dependency_providers(
    message_dao_provider=lambda: message_dao,
    telegram_client_provider=lambda: telegram_client,
    media_api_provider=lambda: media_api,
    logger_provider=lambda: logger,
)

notification_bot_whois_command_service.set_dependency_providers(
    user_bot_dao_provider=lambda: user_bot_dao,
    escape_html_provider=lambda: escape_html,
    logger_provider=lambda: logger,
)

notification_bot_check_command_service.set_dependency_providers(
    media_api_provider=lambda: media_api,
    network_client_provider=lambda: network_client,
    media_server_public_url_provider=lambda: get_media_server_public_url,
    logger_provider=lambda: logger,
    time_provider=lambda: time,
)

notification_bot_playback_command_service.set_dependency_providers(
    media_api_provider=lambda: media_api,
    playback_store_provider=lambda: playback_store,
)

notification_bot_emby_restart_command_service.set_dependency_providers(
    logger_provider=lambda: logger,
)

notification_bot_latest_command_service.set_dependency_providers(
    media_api_provider=lambda: media_api,
    admin_id_provider=lambda: get_admin_id,
    logger_provider=lambda: logger,
)

notification_bot_search_command_service.set_dependency_providers(
    media_api_provider=lambda: media_api,
    admin_id_provider=lambda: get_admin_id,
    media_server_main_public_or_host_provider=lambda: get_media_server_main_public_or_host,
    media_server_host_provider=lambda: get_media_server_host,
    report_cover_url_provider=lambda: REPORT_COVER_URL,
)

notification_bot_stats_command_service.set_dependency_providers(
    base_filter_provider=lambda: get_base_filter,
    playback_store_provider=lambda: playback_store,
    report_gen_provider=lambda: report_gen,
    has_pil_provider=lambda: HAS_PIL,
    report_cover_url_provider=lambda: REPORT_COVER_URL,
    logger_provider=lambda: logger,
)

notification_bot_info_command_service.set_dependency_providers(
    logger_provider=lambda: logger,
)

notification_bot_message_dispatch_service.set_dependency_providers(
    tg_chat_id_provider=lambda: get_tg_chat_id,
    bus_provider=lambda: bus,
    logger_provider=lambda: logger,
)

notification_bot_command_registration_service.set_dependency_providers(
    tg_bot_token_provider=lambda: get_notify_tg_bot_token,
    safe_proxies_provider=lambda: get_safe_proxies,
    telegram_client_provider=lambda: telegram_client,
)

notification_bot_polling_service.set_dependency_providers(
    tg_bot_token_provider=lambda: get_notify_tg_bot_token,
    tg_chat_id_provider=lambda: get_tg_chat_id,
    safe_proxies_provider=lambda: get_safe_proxies,
    telegram_client_provider=lambda: telegram_client,
    submit_bot_task_provider=lambda: _submit_bot_task,
)

notification_bot_risk_alert_service.set_dependency_providers(
    pulse_url_provider=lambda: get_pulse_url,
    media_server_main_public_or_host_provider=lambda: get_media_server_main_public_or_host,
    add_system_notification_provider=lambda: add_system_notification,
    logger_provider=lambda: logger,
)

notification_bot_user_login_service.set_dependency_providers(
    notify_rule_provider=lambda: get_notify_rule,
    notify_user_login_provider=lambda: get_notify_user_login,
    location_provider=lambda: get_location,
    add_system_notification_provider=lambda: add_system_notification,
    datetime_provider=lambda: datetime,
    quote_provider=lambda: urllib.parse.quote,
    logger_provider=lambda: logger,
)

notification_bot_item_deleted_service.set_dependency_providers(
    notify_item_deleted_provider=lambda: get_notify_item_deleted,
    time_provider=lambda: time,
    datetime_provider=lambda: datetime,
    tmdb_client_provider=lambda: tmdb_client,
    safe_proxies_provider=lambda: get_safe_proxies,
    report_cover_url_provider=lambda: REPORT_COVER_URL,
    logger_provider=lambda: logger,
)

notification_bot_library_new_episode_service.set_dependency_providers(
    enable_library_notify_provider=lambda: get_enable_library_notify,
    media_quality_info_provider=lambda: get_media_quality_info,
    media_server_main_public_or_host_provider=lambda: get_media_server_main_public_or_host,
    media_server_host_provider=lambda: get_media_server_host,
    notify_channels_provider=lambda: get_notify_channels,
    get_plugin_provider=lambda: get_plugin,
    report_cover_url_provider=lambda: REPORT_COVER_URL,
    datetime_provider=lambda: datetime,
    re_provider=lambda: re,
    logger_provider=lambda: logger,
)

notification_bot_library_new_item_service.set_dependency_providers(
    enable_library_notify_provider=lambda: get_enable_library_notify,
    media_quality_info_provider=lambda: get_media_quality_info,
    media_server_main_public_or_host_provider=lambda: get_media_server_main_public_or_host,
    media_server_host_provider=lambda: get_media_server_host,
    notify_channels_provider=lambda: get_notify_channels,
    get_plugin_provider=lambda: get_plugin,
    report_cover_url_provider=lambda: REPORT_COVER_URL,
    datetime_provider=lambda: datetime,
    re_provider=lambda: re,
    logger_provider=lambda: logger,
)

notification_bot_playback_event_service.set_dependency_providers(
    enable_notify_provider=lambda: get_enable_notify,
    media_api_provider=lambda: media_api,
    location_provider=lambda: get_location,
    media_server_main_public_or_host_provider=lambda: get_media_server_main_public_or_host,
    media_server_host_provider=lambda: get_media_server_host,
    get_plugin_provider=lambda: get_plugin,
    report_cover_url_provider=lambda: REPORT_COVER_URL,
    datetime_provider=lambda: datetime,
    re_provider=lambda: re,
    logger_provider=lambda: logger,
)

notification_bot_pending_sync_service.set_dependency_providers(
    media_request_dao_provider=lambda: media_request_dao,
    media_api_provider=lambda: media_api,
    admin_id_provider=lambda: get_admin_id,
    logger_provider=lambda: logger,
)

notification_bot_user_expiration_service.set_dependency_providers(
    user_dao_provider=lambda: user_dao,
    media_api_provider=lambda: media_api,
    datetime_provider=lambda: datetime,
)

notification_bot_auto_finish_request_service.set_dependency_providers(
    media_request_dao_provider=lambda: media_request_dao,
    notify_rule_provider=lambda: get_notify_rule,
    logger_provider=lambda: logger,
)

notification_bot_webhook_event_service.set_dependency_providers(
    bus_provider=lambda: bus,
    logger_provider=lambda: logger,
)

notification_bot_gap_clear_service.set_dependency_providers(
    gap_dao_provider=lambda: gap_dao,
    remove_gap_from_scan_state_provider=lambda: remove_gap_from_scan_state,
)

notification_bot_fresh_episode_service.set_dependency_providers(
    admin_id_provider=lambda: get_admin_id,
    datetime_provider=lambda: datetime,
    media_api_provider=lambda: media_api,
)

notification_bot_library_queue_service.set_dependency_providers(
    library_notify_queue_max_provider=lambda: get_library_notify_queue_max,
    logger_provider=lambda: logger,
)

notification_bot_library_push_service.set_dependency_providers(
    admin_id_provider=lambda: get_admin_id,
    bus_provider=lambda: bus,
    gap_dao_provider=lambda: gap_dao,
    media_api_provider=lambda: media_api,
)

notification_bot_library_group_service.set_dependency_providers(
    logger_provider=lambda: logger,
)

notification_bot_plugin_callback_service.set_dependency_providers(
    logger_provider=lambda: logger,
)

notification_bot_feedback_callback_service.set_dependency_providers(
    media_request_dao_provider=lambda: media_request_dao,
    telegram_client_provider=lambda: telegram_client,
)

notification_bot_risk_ban_callback_service.set_dependency_providers(
    telegram_client_provider=lambda: telegram_client,
    username_lookup_provider=lambda bot, user_id: bot._get_username(user_id),
)

notification_bot_request_approval_menu_callback_service.set_dependency_providers(
    media_request_dao_provider=lambda: media_request_dao,
    telegram_client_provider=lambda: telegram_client,
    pulse_url_provider=lambda: get_pulse_url,
    get_plugin_provider=lambda: get_plugin,
)

notification_bot_request_approval_action_callback_service.set_dependency_providers(
    media_request_dao_provider=lambda: media_request_dao,
    moviepilot_client_provider=lambda: moviepilot_client,
    moviepilot_url_provider=lambda: get_moviepilot_url,
    moviepilot_token_provider=lambda: get_moviepilot_token,
    telegram_client_provider=lambda: telegram_client,
    record_request_admin_message_provider=lambda: _record_request_admin_message,
    sync_request_admin_messages_provider=lambda: _sync_request_admin_messages,
)

notification_bot_request_hdhive_search_callback_service.set_dependency_providers(
    logger_provider=lambda: logger,
    telegram_client_provider=lambda: telegram_client,
)

notification_bot_callback_dispatcher_service.set_dependency_providers(
    notify_tg_bot_token_provider=lambda: get_notify_tg_bot_token(),
    safe_proxies_provider=lambda: get_safe_proxies(),
    telegram_client_provider=lambda: telegram_client,
    plugin_callback_service_provider=lambda: notification_bot_plugin_callback_service,
    emby_restart_command_service_provider=lambda: notification_bot_emby_restart_command_service,
    message_center_callback_service_provider=lambda: notification_bot_message_center_callback_service,
    risk_ban_callback_service_provider=lambda: notification_bot_risk_ban_callback_service,
    feedback_callback_service_provider=lambda: notification_bot_feedback_callback_service,
    request_hdhive_search_callback_service_provider=lambda: notification_bot_request_hdhive_search_callback_service,
    request_approval_menu_callback_service_provider=lambda: notification_bot_request_approval_menu_callback_service,
    request_approval_action_callback_service_provider=lambda: notification_bot_request_approval_action_callback_service,
)

def _submit_bot_task(fn, *args):
    if not _bot_executor_slots.acquire(blocking=False):
        logger.warning("[Bot] 后台任务队列已满，丢弃本次异步任务")
        return False
    future = _bot_executor.submit(fn, *args)
    future.add_done_callback(lambda _f: _bot_executor_slots.release())
    return True

def get_notify_rule(rule_type):
    from app.domains.notifications.notify_admin import get_notify_rule as _get_notify_rule

    return _get_notify_rule(rule_type)

def get_plugin(plugin_name):
    from app.plugins import get_plugin as _get_plugin

    return _get_plugin(plugin_name)

def _ensure_request_admin_messages_table():
    return notification_bot_request_admin_message_sync_service.ensure_request_admin_messages_table()

def _extract_request_tmdb_id(reply_markup):
    return notification_bot_request_admin_message_sync_service.extract_request_tmdb_id(reply_markup)

def _record_request_admin_message(tmdb_id, chat_id, message_id, is_caption, original_text):
    return notification_bot_request_admin_message_sync_service.record_request_admin_message(tmdb_id, chat_id, message_id, is_caption, original_text)

def _sync_request_admin_messages(tmdb_id, action_text, operator, token, proxies, fallback_text="", fallback_is_caption=True):
    return notification_bot_request_admin_message_sync_service.sync_request_admin_messages(
        tmdb_id,
        action_text,
        operator,
        token,
        proxies,
        fallback_text,
        fallback_is_caption,
    )

# 🔒 XSS 防护：HTML 转义函数（用于 Telegram 消息）
def escape_html(text):
    """转义 HTML 特殊字符，防止 XSS 攻击"""
    if not text:
        return ''
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def get_notify_channels(notify_type: str) -> list:
    """获取指定通知类型的启用渠道列表
    
    Args:
        notify_type: 通知类型，如 'library_new', 'user_register' 等
    
    Returns:
        启用的渠道列表，如 ['tg_bot', 'tg_channel', 'wecom']
    """
    # 🔥 入库通知优先从配置文件读取
    if notify_type == "library_new":
        try:
            channels_str = get_library_notify_channels()
            if channels_str:
                channels = json.loads(channels_str)
                if channels:
                    return channels
        except Exception as e:
            logger.error(f"获取入库通知渠道配置失败: {e}")
    
    # 从 notify_rules 表读取
    try:
        row = notify_admin_dao.get_notify_rule_row(notify_type)
        
        if row and row['enabled'] == 1:
            channels = json.loads(row['channels'] or '[]')
            return channels
    except Exception as e:
        logger.error(f"获取通知渠道失败: {e}")
    
    # 返回默认值：所有渠道
    return ['tg_bot', 'tg_channel', 'wecom']

def get_admin_id():
    return notification_bot_media_quality_service.get_admin_id()

def init_notify_rules_db():
    try:
        notify_rule_dao.ensure_bot_notify_mutes_table()
    except Exception as e:
        logger.error(f"Failed to create bot_notify_mutes table: {e}")

def get_media_quality_info(item_id: str) -> dict:
    return notification_bot_media_quality_service.get_media_quality_info(item_id)

class SystemDaemon:
    def __init__(self):
        self.running = False
        self.schedule_thread = None 
        self.library_queue = []
        self.library_lock = threading.Lock()
        self.library_thread = None
        self.last_check_min = -1
        self.last_sync_min = -1
        self._subscribed = False
        self._stop_event = threading.Event()
        
    def start(self):
        if self.running: return
        self._subscribe_events()
        self._stop_event.clear()
        self.running = True
        self.schedule_thread = threading.Thread(
            target=self._scheduler_loop,
            daemon=True,
            name="notification-daemon-scheduler",
        )
        self.schedule_thread.start()
        self.library_thread = threading.Thread(
            target=self._library_notify_loop,
            daemon=True,
            name="notification-daemon-library",
        )
        self.library_thread.start()
        print("🧠 System Daemon Started (Event Subsystem Online)")

    def stop(self):
        self.running = False
        self._stop_event.set()
        self._unsubscribe_events()
        schedule_thread = self.schedule_thread
        library_thread = self.library_thread
        if schedule_thread and schedule_thread.is_alive():
            schedule_thread.join(timeout=1)
        if library_thread and library_thread.is_alive():
            library_thread.join(timeout=1)
        if not schedule_thread or not schedule_thread.is_alive():
            self.schedule_thread = None
        if not library_thread or not library_thread.is_alive():
            self.library_thread = None

    def _subscribe_events(self):
        if self._subscribed:
            return
        bus.subscribe("webhook.received", self.on_webhook_event)
        self._subscribed = True

    def _unsubscribe_events(self):
        if not self._subscribed:
            return
        bus.unsubscribe("webhook.received", self.on_webhook_event)
        self._subscribed = False

    def on_webhook_event(self, event: str, data: dict):
        return notification_bot_webhook_event_service.handle_webhook_event(self, event, data)

    def _auto_finish_request(self, tmdb_id, season=None):
        return notification_bot_auto_finish_request_service.auto_finish_request(self, tmdb_id, season)
    
    def _notify_request_status_change(self, tmdb_id, requests_info, users_info, action, reject_reason=None):
        return notification_bot_auto_finish_request_service.notify_request_status_change(
            tmdb_id,
            requests_info,
            users_info,
            action,
            reject_reason,
        )

    def _clear_gap_record_async(self, item: dict):
        return notification_bot_gap_clear_service.clear_gap_record(item)

    def add_library_task(self, item):
        return notification_bot_library_queue_service.add_library_task(self, item)

    def _library_notify_loop(self):
        while self.running and not self._stop_event.is_set():
            try:
                with self.library_lock: has_data = len(self.library_queue) > 0
                if not has_data:
                    if self._stop_event.wait(2): return
                    continue

                idle_time = 0; last_len = 0; max_wait = 0
                while idle_time < 15 and max_wait < 120:
                    if self._stop_event.wait(3): return
                    idle_time += 3; max_wait += 3
                    with self.library_lock:
                        curr_len = len(self.library_queue)
                        if curr_len > last_len: idle_time = 0; last_len = curr_len
                
                items_to_process = []
                with self.library_lock:
                    items_to_process = self.library_queue[:]
                    self.library_queue = [] 
                
                if items_to_process: self._process_library_group(items_to_process)
            except Exception as e:
                if self._stop_event.wait(5): return

    def _process_library_group(self, items):
        return notification_bot_library_group_service.process_library_group(
            self,
            items,
            wait_between_groups=lambda: self._stop_event.wait(2),
        )

    def _check_fresh_episodes(self, series_id):
        return notification_bot_fresh_episode_service.check_fresh_episodes(series_id, self._parse_emby_time)

    def _parse_emby_time(self, date_str):
        return notification_bot_fresh_episode_service.parse_emby_time(date_str)

    def _push_episode_group(self, series_id, episodes):
        return notification_bot_library_push_service.push_episode_group(self, series_id, episodes)

    def _push_single_item(self, item):
        return notification_bot_library_push_service.push_single_item(self, item)

    def _scheduler_loop(self):
        while self.running:
            try:
                now = datetime.datetime.now()
                if now.minute != self.last_check_min:
                    self.last_check_min = now.minute
                    if now.hour == 9 and now.minute == 0:
                        self._check_user_expiration()
                        # bus.publish("notify.daily_report")  # 已由观影报告插件定时任务处理，避免重复
                if now.minute % 10 == 0 and now.minute != self.last_sync_min:
                    self.last_sync_min = now.minute
                    self._sync_pending_requests()
                if self._stop_event.wait(5): return
            except:
                if self._stop_event.wait(60): return

    def _sync_pending_requests(self):
        return notification_bot_pending_sync_service.sync_pending_requests(self)

    def _check_user_expiration(self):
        return notification_bot_user_expiration_service.check_user_expiration()


class NotificationBot:
    def __init__(self):
        self.running = False
        self.poll_thread = None
        self.offset = 0
        self.user_cache = {}
        self.ip_cache = {} 
        self.wecom_token = None
        self.wecom_token_expires = 0
        self.delete_cache = {}
        self._msg_reply_mode = {}  # chat_id -> user_id 存储回复模式
        self._subscribed = False
        self._stop_event = threading.Event()

    def _is_muted(self, user_id, event_type):
        if not user_id: return False
        try:
            return notify_rule_dao.is_bot_notify_muted(user_id, event_type)
        except:
            return False

    def start(self):
        if self.running: return
        if not get_bot_tg_token() and not get_wecom_corpid(): return
        self._subscribe_events()
        self._stop_event.clear()
        self.running = True
        self._set_commands()
        self._set_wecom_menu() 
        if get_bot_tg_token():
            self.poll_thread = threading.Thread(
                target=self._polling_loop,
                daemon=True,
                name="notification-bot-polling",
            )
            self.poll_thread.start()
        logger.info("🤖 Notification Bot Started")

    def stop(self):
        self.running = False
        self._stop_event.set()
        self._unsubscribe_events()
        thread = self.poll_thread
        if thread and thread.is_alive():
            thread.join(timeout=1)
        if not thread or not thread.is_alive():
            self.poll_thread = None

    def _subscribe_events(self):
        if self._subscribed:
            return
        bus.subscribe("notify.library.new_episode", self.on_library_new_episode)
        bus.subscribe("notify.library.new_item", self.on_library_new_item)
        bus.subscribe("notify.gap_cleared", self.on_gap_cleared)
        bus.subscribe("notify.playback.start", self._on_playback_start_event)
        bus.subscribe("notify.playback.stop", self._on_playback_stop_event)
        bus.subscribe("notify.user.login", self.on_user_login)
        bus.subscribe("notify.item.deleted", self.on_item_deleted)
        bus.subscribe("notify.daily_report", self.on_daily_report)
        bus.subscribe("notify.risk.alert", self.on_risk_alert)
        self._subscribed = True

    def _unsubscribe_events(self):
        if not self._subscribed:
            return
        bus.unsubscribe("notify.library.new_episode", self.on_library_new_episode)
        bus.unsubscribe("notify.library.new_item", self.on_library_new_item)
        bus.unsubscribe("notify.gap_cleared", self.on_gap_cleared)
        bus.unsubscribe("notify.playback.start", self._on_playback_start_event)
        bus.unsubscribe("notify.playback.stop", self._on_playback_stop_event)
        bus.unsubscribe("notify.user.login", self.on_user_login)
        bus.unsubscribe("notify.item.deleted", self.on_item_deleted)
        bus.unsubscribe("notify.daily_report", self.on_daily_report)
        bus.unsubscribe("notify.risk.alert", self.on_risk_alert)
        self._subscribed = False

    def _on_playback_start_event(self, data):
        self.on_playback_event(data, "start")

    def _on_playback_stop_event(self, data):
        self.on_playback_event(data, "stop")

    def on_risk_alert(self, data):
        return notification_bot_risk_alert_service.handle_risk_alert(self, data)

    def on_gap_cleared(self, data):
        if not get_enable_library_notify(): return
        s_idx = data["s_idx"]; e_idx = data["e_idx"]
        series_name = data.get("series_name", "未知剧集")
        msg = (f"🎉 <b>残卷补全成功！</b>\n\n📺 剧集已入库：<b>《{series_name}》 S{str(s_idx).zfill(2)}E{str(e_idx).zfill(2)}</b>\n"
               f"✅ 状态：缺集工单已自动核销闭环\n<i>拼图已圆满，强迫症得到治愈。</i>")
        self.send_message("sys_notify", msg, platform="all")

    def on_library_new_episode(self, data):
        return notification_bot_library_new_episode_service.handle_library_new_episode(self, data)

    def on_library_new_item(self, item):
        return notification_bot_library_new_item_service.handle_library_new_item(self, item)

    def _notify_channels(self, photo_io, caption, keyboard, item_type, item_info):
        return notification_bot_channel_service.notify_channels(photo_io, caption, keyboard, item_type, item_info)

    def _send_to_channel(self, chat_id, photo_io, caption, keyboard):
        return notification_bot_channel_service.send_to_channel(chat_id, photo_io, caption, keyboard)

    def send_to_channels(self, photo_io, caption, keyboard=None):
        return notification_bot_channel_service.send_to_channels(photo_io, caption, keyboard)

    def _format_ticks(self, ticks):
        if not ticks: return "00:00:00"
        try:
            total_seconds = int(int(ticks) / 10000000)
            h = total_seconds // 3600
            m = (total_seconds % 3600) // 60
            s = total_seconds % 60
            return f"{h:02}:{m:02}:{s:02}"
        except:
            return "00:00:00"

    def on_playback_event(self, data, action):
        return notification_bot_playback_event_service.handle_playback_event(self, data, action)

    def on_user_login(self, data):
        return notification_bot_user_login_service.handle_user_login(self, data)

    def on_item_deleted(self, data):
        return notification_bot_item_deleted_service.handle_item_deleted(self, data)

    def on_daily_report(self):
        chat_id = "sys_notify"
        # 🔥 时区修复：强制增加 'localtime'，与本地北京时间保持严格对齐
        where = "WHERE DateCreated >= date('now', 'localtime', '-1 day', 'start of day') AND DateCreated < date('now', 'localtime', 'start of day')"
        res = playback_store.query(f"SELECT COUNT(*) as c FROM PlaybackActivity {where}")
        count = res[0]['c'] if res else 0
        if count == 0:
            yesterday_str = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
            msg = (f"📅 <b>昨日日报 ({yesterday_str})</b>\n\n😴 昨天服务器静悄悄，大家都去现充了吗？\n\n📊 活跃用户：0 人\n⏳ 播放时长：0 小时")
            self.send_message(chat_id, msg, platform="all")
        else: self._cmd_stats(chat_id, 'yesterday', platform="all")

    def _check_admin_permission(self, chat_id, user_id):
        """检查用户是否有管理员权限
        
        检查逻辑：
        1. 如果 tg_chat_id 配置了，检查 chat_id 是否在配置中
        2. 检查用户是否是群组管理员或机器人创建者
        """
        token = get_notify_tg_bot_token()
        if not token or not user_id:
            return False
        
        # 获取配置的管理员 chat_id 列表
        raw_cids = str(get_tg_chat_id())
        admin_chat_ids = [c.strip() for c in raw_cids.replace('，', ',').split(',') if c.strip()]
        
        # 如果配置了特定的 chat_id，只有这些 chat_id 才能操作
        if admin_chat_ids and str(chat_id) not in admin_chat_ids:
            return False
        
        # 检查用户是否是群组管理员
        try:
            proxies = get_safe_proxies()
            # 获取群组信息
            res = telegram_client.get_api(token, "getChatMember", params={"chat_id": chat_id, "user_id": user_id}, proxies=proxies, timeout=10)
            if res.status_code == 200:
                member = res.json().get("result", {})
                status = member.get("status", "")
                # creator, administrator 可以操作
                if status in ["creator", "administrator"]:
                    return True
        except Exception: pass
        
        # 如果没有配置 tg_chat_id，且用户不是管理员，拒绝
        if not admin_chat_ids:
            return False
        
        return True

    def _download_user_image(self, user_id):
        return notification_bot_media_helper_service.download_user_image(user_id)

    def _get_username(self, user_id):
        return notification_bot_media_helper_service.get_username(self, user_id)

    def _get_subnet_key(self, ip):
        return notification_bot_media_helper_service.get_subnet_key(ip)

    def _save_playback_history(self, data, user_id, user_name, item, ip, location):
        return notification_bot_media_helper_service.save_playback_history(data, user_id, user_name, item, ip, location)

    def _download_emby_image(self, item_id, img_type='Primary', image_tag=None):
        return notification_bot_media_helper_service.download_emby_image(item_id, img_type, image_tag)

    def _get_wecom_token(self):
        return notification_bot_wecom_service.get_wecom_token(self)

    def _html_to_wecom_text(self, html_text, inline_keyboard=None):
        return notification_bot_wecom_service.html_to_wecom_text(html_text, inline_keyboard)

    def _set_wecom_menu(self):
        return notification_bot_wecom_service.set_wecom_menu(self)

    def _send_wecom_message(self, text, inline_keyboard=None, touser="@all"):
        return notification_bot_wecom_service.send_wecom_message(self, text, inline_keyboard, touser)

    def _send_wecom_photo(self, photo_bytes, html_text, inline_keyboard=None, touser="@all"):
        return notification_bot_wecom_service.send_wecom_photo(self, photo_bytes, html_text, inline_keyboard, touser)

    def send_photo(self, chat_id, photo_io, caption, parse_mode="HTML", reply_markup=None, platform="all", wecom_photo_io=None):
        return notification_bot_delivery_service.send_photo(
            self,
            chat_id,
            photo_io,
            caption,
            parse_mode,
            reply_markup,
            platform,
            wecom_photo_io,
        )

    def send_message(self, chat_id, text, parse_mode="HTML", reply_markup=None, platform="all"):
        return notification_bot_delivery_service.send_message(self, chat_id, text, parse_mode, reply_markup, platform)

    def edit_message(self, chat_id, message_id, text, parse_mode="HTML", reply_markup=None, platform="tg"):
        return notification_bot_delivery_service.edit_message(self, chat_id, message_id, text, parse_mode, reply_markup, platform)

    def _polling_loop(self):
        return notification_bot_polling_service.run_polling_loop(self)

    def _handle_callback(self, cq):
        return notification_bot_callback_dispatcher_service.handle_callback(self, cq)

    def _set_commands(self):
        return notification_bot_command_registration_service.set_commands()

    def _is_admin(self, cid, platform="tg"):
        return notification_bot_message_dispatch_service.is_admin(cid, platform)

    def _handle_message(self, text, cid, platform="tg"):
        return notification_bot_message_dispatch_service.handle_message(self, text, cid, platform)

    def _cmd_latest(self, cid, platform):
        return notification_bot_latest_command_service.cmd_latest(self, cid, platform)

    def _extract_tech_info(self, item):
        return notification_bot_search_command_service.extract_tech_info(item)

    def _cmd_search(self, chat_id, text, platform):
        return notification_bot_search_command_service.cmd_search(self, chat_id, text, platform)

    def _cmd_stats(self, chat_id, period='day', platform="tg"):
        return notification_bot_stats_command_service.cmd_stats(self, chat_id, period, platform)

    def _cmd_now(self, cid, platform):
        return notification_bot_playback_command_service.cmd_now(self, cid, platform)

    def _cmd_recent(self, cid, platform):
        return notification_bot_playback_command_service.cmd_recent(self, cid, platform)

    def _cmd_check(self, cid, platform):
        return notification_bot_check_command_service.cmd_check(self, cid, platform)

    def _cmd_emby_restart(self, cid, text, platform):
        return notification_bot_emby_restart_command_service.cmd_emby_restart(self, cid, text, platform)

    def _cmd_calendar(self, cid, platform):
        return notification_bot_info_command_service.cmd_calendar(self, cid, platform)

    def _format_expire_status(self, expire_date):
        return notification_bot_whois_command_service.format_expire_status(expire_date)

    def _format_whois_row(self, row, index=None):
        return notification_bot_whois_command_service.format_whois_row(row, index)

    def _cmd_whois(self, cid, text, platform):
        return notification_bot_whois_command_service.cmd_whois(self, cid, text, platform)

    def _cmd_help(self, cid, platform):
        return notification_bot_info_command_service.cmd_help(self, cid, platform)

    def _handle_msg_reply_callback(self, cid, mid, user_id, token, proxies):
        return notification_bot_message_center_callback_service.handle_msg_reply_callback(self, cid, mid, user_id, token, proxies)

    def _handle_msg_block_callback(self, cid, mid, user_id, token, proxies, cq):
        return notification_bot_message_center_callback_service.handle_msg_block_callback(cid, mid, user_id, token, proxies, cq)

    def _handle_msg_unblock_callback(self, cid, mid, user_id, token, proxies, cq):
        return notification_bot_message_center_callback_service.handle_msg_unblock_callback(cid, mid, user_id, token, proxies, cq)

    def _handle_msg_reply_message(self, text, cid):
        return notification_bot_message_center_callback_service.handle_msg_reply_message(self, text, cid)

class EmbyPulseOrchestrator:
    def __init__(self):
        self.daemon = SystemDaemon()
        self.notifier = NotificationBot()
        
    def start(self):
        self.daemon.start()
        self.notifier.start()
        
    def stop(self):
        self.daemon.stop()
        self.notifier.stop()
        
    def push_now(self, user_id, period, theme):
        return self.notifier._cmd_stats("sys_notify", period, platform="all")

    def push_playback_event(self, data, action="start"):
        bus.publish("webhook.received", f"playback.{action}", data)

bot = EmbyPulseOrchestrator()


def start_notification_services() -> None:
    init_notify_rules_db()
    from app.domains.notifications.notify_admin import ensure_notify_rules_table
    from app.domains.notifications.notify_rules import start_notify_rules_services

    ensure_notify_rules_table()
    start_notify_rules_services()
    bot.start()

    try:
        from app.domains.notifications.user_bot_service import start_user_bot_services

        start_user_bot_services()
    except Exception as e:
        print(f"⚠️ 用户机器人启动异常: {e}")


def stop_notification_services() -> None:
    bot.stop()

    from app.domains.notifications.user_bot_service import user_bot

    user_bot.stop()


def is_user_bot_running() -> bool:
    from app.domains.notifications.user_bot_service import user_bot

    return user_bot.running
