import threading
import time
import datetime
import logging
import urllib.parse
import json 
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from app.core.config import REPORT_COVER_URL, FALLBACK_IMAGE_URL
from app.infra.db.notification_dao import add_system_notification
from app.domains.media_requests import gap_dao, media_request_dao
from app.domains.media_requests.public_service import remove_gap_from_scan_state
from app.domains.users import user_bot_dao
from app.domains.notifications import bot_service_dao, message_dao
from app.domains.notifications import notification_bot_channel_service
from app.domains.notifications import notification_bot_check_command_service
from app.domains.notifications import notification_bot_command_registration_service
from app.domains.notifications import notification_bot_delivery_service
from app.domains.notifications import notification_bot_emby_restart_command_service
from app.domains.notifications import notification_bot_info_command_service
from app.domains.notifications import notification_bot_item_deleted_service
from app.domains.notifications import notification_bot_latest_command_service
from app.domains.notifications import notification_bot_message_dispatch_service
from app.domains.notifications import notification_bot_message_center_callback_service
from app.domains.notifications import notification_bot_media_helper_service
from app.domains.notifications import notification_bot_media_quality_service
from app.domains.notifications import notification_bot_playback_command_service
from app.domains.notifications import notification_bot_polling_service
from app.domains.notifications import notification_bot_request_admin_message_sync_service
from app.domains.notifications import notification_bot_risk_alert_service
from app.domains.notifications import notification_bot_search_command_service
from app.domains.notifications import notification_bot_stats_command_service
from app.domains.notifications import notification_bot_user_login_service
from app.domains.notifications import notification_bot_wecom_service
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
        # 只对重要事件输出日志，减少刷屏
        important_events = ["item.added", "library.new", "playback.start", "playback.stop", "auth", "login", "delete", "remove"]
        if any(e in event for e in important_events):
            logger.info(f"🔔 [Webhook] 收到事件: {event}")
        
        if "item.added" in event or "library.new" in event:
            item = data.get("Item", {})
            if item.get("Id"):
                self.add_library_task(item)
                if item.get("Type") == "Episode":
                    from app.domains.playback.calendar_service import calendar_service
                    calendar_service.mark_episode_ready(item.get("SeriesId"), item.get("ParentIndexNumber"), item.get("IndexNumber"))
                    self._clear_gap_record_async(item)
        elif "playback.start" in event:
            logger.info(f"🔔 [Webhook] 发布 playback.start 事件")
            bus.publish("notify.playback.start", data)
        elif "playback.stop" in event:
            logger.info(f"🔔 [Webhook] 发布 playback.stop 事件")
            bus.publish("notify.playback.stop", data)
        elif "auth" in event or "login" in event: bus.publish("notify.user.login", data)
        elif "delete" in event or "remove" in event: bus.publish("notify.item.deleted", data)

    def _auto_finish_request(self, tmdb_id, season=None):
        """自动更新求片状态为已入库，并通知用户
        
        Args:
            tmdb_id: TMDB ID
            season: 季数（可选，电影不需要，电视剧需要精确匹配）
        """
        if not tmdb_id: return
        try:
            tid = int(tmdb_id)
            requests_to_notify, users_to_notify = media_request_dao.finish_media_requests_for_item(tid, season)
            
            # 🔥 通知用户（入库完成）
            if requests_to_notify and users_to_notify:
                self._notify_request_status_change(tid, requests_to_notify, users_to_notify, "finish")
                
        except Exception as e:
            logger.error(f"[自动入库] 更新工单状态失败: {e}")
    
    def _notify_request_status_change(self, tmdb_id, requests_info, users_info, action, reject_reason=None):
        """通知用户工单状态变更
        
        Args:
            tmdb_id: TMDB ID
            requests_info: 工单信息列表 [{title, year, media_type, season}]
            users_info: 用户列表 [{user_id, username}]
            action: 操作类型 (approve/finish/reject/manual/hdhive_done)
            reject_reason: 拒绝原因（可选）
        """
        try:
            from app.domains.notifications.notify_admin import get_notify_rule
            rule = get_notify_rule('request_status')
            
            if not rule or not rule.get('enabled') or 'tg_bot' not in rule.get('channels', []):
                logger.info(f"[状态变更通知] 规则未启用或渠道不含tg_bot")
                return
            
            # 批量查询 TG 绑定
            user_ids = [u['user_id'] for u in users_info]
            tg_bindings = media_request_dao.list_tg_bindings(user_ids)
            
            from app.domains.notifications.user_bot_service import _send, _tg_api
            
            for req in requests_info:
                title = req['title']
                year = req['year'] or ''
                media_type = req['media_type']
                season = req['season']
                
                # 构建标题
                if media_type == 'tv':
                    title_text = f"{title} S{season}"
                else:
                    title_text = title
                
                # 状态文本和图标
                if action == "approve":
                    status_icon = "🚀"
                    status_text = "审批通过，正在下载中"
                elif action == "finish":
                    status_icon = "✅"
                    status_text = "已入库完成，可以观看啦！"
                elif action == "reject":
                    status_icon = "❌"
                    status_text = f"已拒绝\n📝 原因: {reject_reason or '未说明'}"
                elif action == "manual":
                    status_icon = "✋"
                    status_text = "已手动接单，正在处理中"
                elif action == "hdhive_done":
                    status_icon = "📥"
                    status_text = "影巢转存成功，等待入库"
                else:
                    status_icon = "📢"
                    status_text = "状态已更新"
                
                msg = f"{status_icon} <b>求片状态更新</b>\n\n📺 <b>内容：</b>{title_text} ({year})\n📢 <b>状态：</b>{status_text}"
                
                for u in users_info:
                    user_id = u['user_id']
                    tg_id = tg_bindings.get(user_id)
                    
                    if tg_id:
                        logger.info(f"[自动入库通知] 发送给用户: tg_id={tg_id}, title={title_text}")
                        try:
                            _send(int(tg_id), msg)
                        except Exception as e:
                            logger.error(f"[自动入库通知] 发送失败: {e}")
                            
        except Exception as e:
            logger.error(f"[状态变更通知] 通知失败: {e}")

    def _clear_gap_record_async(self, item: dict):
        try:
            if item.get("Type") != "Episode": return
            series_id = str(item.get("SeriesId"))
            season = int(item.get("ParentIndexNumber", -1))
            episode = int(item.get("IndexNumber", -1))
            if season == -1 or episode == -1: return

            gap_dao.delete_gap_record_by_series_episode(series_id, season, episode)
            try:
                remove_gap_from_scan_state(series_id, season, episode)
            except Exception: pass
        except Exception as e: pass

    def add_library_task(self, item):
        with self.library_lock:
            max_queue = 300
            max_queue = get_library_notify_queue_max()
            if len(self.library_queue) >= max_queue:
                dropped = self.library_queue.pop(0)
                logger.warning(f"[入库通知] 队列已满，丢弃最旧项目: {dropped.get('Name') or dropped.get('Id')}")
            if not any(x.get('Id') == item.get('Id') for x in self.library_queue):
                self.library_queue.append(item)

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
        groups = defaultdict(list)
        for item in items:
            itype = item.get('Type')
            if itype in ['Episode', 'Season'] and item.get('SeriesId'): groups[str(item.get('SeriesId'))].append(item)
            elif itype == 'Series': groups[str(item.get('Id'))].append(item)
            else: groups[str(item.get('Id'))].append(item)

        for group_id, group_items in groups.items():
            try:
                is_tv = any(x.get('Type') in ['Episode', 'Season', 'Series'] for x in group_items)
                if is_tv:
                    fresh_episodes = self._check_fresh_episodes(group_id)
                    if fresh_episodes: self._push_episode_group(group_id, fresh_episodes)
                    else:
                        series_item = next((x for x in group_items if x.get('Type') == 'Series'), None)
                        if series_item: self._push_single_item(series_item)
                        else:
                            episodes_only = [x for x in group_items if x.get('Type') == 'Episode']
                            if episodes_only: self._push_episode_group(group_id, episodes_only)
                else:
                    self._push_single_item(group_items[0])
                if self._stop_event.wait(2):
                    return
            except Exception as e:
                logger.error(f"[入库通知] 处理失败: {e}")

    def _check_fresh_episodes(self, series_id):
        admin_id = get_admin_id()
        if not admin_id: return []
        try:
            params = { "ParentId": series_id, "Recursive": "true", "IncludeItemTypes": "Episode", "Limit": 1000, "SortBy": "DateCreated", "SortOrder": "Descending", "Fields": "DateCreated,Name,ParentIndexNumber,IndexNumber" }
            res = media_api.get(f"/Users/{admin_id}/Items", params=params, timeout=10)
            if res.status_code != 200: return []
            items = res.json().get("Items", [])
            if not items: return []
            fresh_list = []; last_time = None
            for i, item in enumerate(items):
                curr_time = self._parse_emby_time(item.get("DateCreated"))
                if not curr_time: 
                    if i == 0: fresh_list.append(item)
                    break
                if i == 0: fresh_list.append(item); last_time = curr_time
                else:
                    delta = abs((last_time - curr_time).total_seconds())
                    if delta <= 120: fresh_list.append(item); last_time = curr_time 
                    else: break 
            return fresh_list
        except Exception as e: return []

    def _parse_emby_time(self, date_str):
        if not date_str: return None
        try:
            clean_str = date_str.replace('Z', '')[:26]
            if '.' in clean_str: return datetime.datetime.strptime(clean_str, "%Y-%m-%dT%H:%M:%S.%f")
            else: return datetime.datetime.strptime(clean_str, "%Y-%m-%dT%H:%M:%S")
        except: return None

    def _push_episode_group(self, series_id, episodes):
        admin_id = get_admin_id()
        series_info = {}
        
        try:
            res = media_api.get(f"/Users/{admin_id}/Items/{series_id}", timeout=10)
            if res.status_code == 200: series_info = res.json()
        except Exception: pass
        if not series_info: series_info = episodes[0]

        series_name = series_info.get('Name', '未知剧集')

        try:
            for ep in episodes:
                s_idx = ep.get('ParentIndexNumber'); e_idx = ep.get('IndexNumber')
                if s_idx is None or e_idx is None: continue
                if gap_dao.delete_cleared_gap_record(series_id, s_idx, e_idx):
                    bus.publish("notify.gap_cleared", {"s_idx": s_idx, "e_idx": e_idx, "series_name": series_name})
        except Exception as e: pass

        st_tmdb = series_info.get("ProviderIds", {}).get("Tmdb")
        if st_tmdb:
            # Extract seasons from added episodes, only update those actually added (avoid affecting other seasons)
            added_seasons = set()
            for ep in episodes:
                s_idx = ep.get('ParentIndexNumber')
                if s_idx is not None:
                    added_seasons.add(s_idx)
            # Update each added season separately
            for s in added_seasons:
                self._auto_finish_request(st_tmdb, season=s)
        bus.publish("notify.library.new_episode", { "series_id": series_id, "episodes": episodes, "series_info": series_info })

    def _push_single_item(self, item):
        try:
            res = media_api.get(f"/Items/{item['Id']}", timeout=10)
            if res.status_code == 200: item = res.json()
        except Exception: pass
        tmdb_id = item.get("ProviderIds", {}).get("Tmdb")
        if tmdb_id: self._auto_finish_request(tmdb_id)
        bus.publish("notify.library.new_item", item)

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
        try:
            # 🔥 修复：检查所有未完成状态（待审批、下载中、手动接单、待入库）
            rows = media_request_dao.list_pending_sync_requests()
            if not rows: return
            admin_id = get_admin_id()
            if not admin_id: return
            for r in rows:
                tid = r['tmdb_id']; mtype = r['media_type']; sn = r['season']
                request_type = r.get('request_type', 'new')
                episodes_str = r.get('episodes', '')
                
                type_filter = "Movie" if mtype == "movie" else "Series"
                params = {"AnyProviderIdEquals": f"tmdb.{tid}", "IncludeItemTypes": type_filter, "Recursive": "true"}
                res = media_api.get(f"/Users/{admin_id}/Items", params=params, timeout=5).json()
                if res.get("Items"):
                    if mtype == "movie":
                        media_request_dao.mark_sync_request_finished(tid)
                        logger.info(f"[入库同步] 电影已入库: tmdb_id={tid}")
                    else:
                        # 🔥 追新请求：检查请求的集数是否都已入库
                        sid = res["Items"][0]["Id"]
                        
                        if request_type == 'update' and episodes_str:
                            # 追新请求：检查集数
                            requested_eps = [int(e) for e in episodes_str.split(",") if e.strip().isdigit()]
                            ep_params = {"ParentId": sid, "IncludeItemTypes": "Episode", "Recursive": "true", "Fields": "ParentIndexNumber,IndexNumber"}
                            ep_res = media_api.get(f"/Users/{admin_id}/Items", params=ep_params, timeout=5).json()
                            local_eps = []
                            for ep in ep_res.get("Items", []):
                                ep_season = ep.get("ParentIndexNumber")
                                ep_num = ep.get("IndexNumber")
                                if ep_season == sn and ep_num:
                                    local_eps.append(ep_num)
                            
                            # 如果请求的集数都已入库，更新状态
                            if requested_eps and all(e in local_eps for e in requested_eps):
                                media_request_dao.mark_sync_request_finished(tid, sn)
                                logger.info(f"[入库同步] 追新已入库: tmdb_id={tid}, season={sn}, episodes={episodes_str}")
                        else:
                            # 求片请求：检查季是否存在
                            s_res = media_api.get(f"/Shows/{sid}/Seasons", params={"UserId": admin_id}, timeout=5).json()
                            local_seasons = [s.get("IndexNumber") for s in s_res.get("Items", [])]
                            if sn in local_seasons:
                                media_request_dao.mark_sync_request_finished(tid, sn)
                                logger.info(f"[入库同步] 求片已入库: tmdb_id={tid}, season={sn}")
                if self._stop_event.wait(0.5):
                    return
        except Exception as e: 
            logger.error(f"[入库同步] 定时同步异常: {e}")

    def _check_user_expiration(self):
        try:
            users = user_dao.list_users_with_expire_date()
            if not users: return
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            for u in users:
                if u['expire_date'] < today:
                    try:
                        # 🔥 修复：先获取完整 Policy，再修改 IsDisabled，避免重置其他权限
                        user_res = media_api.get(f"/Users/{u['user_id']}", timeout=5)
                        if user_res.status_code == 200:
                            policy = user_res.json().get('Policy', {})
                            if not policy.get('IsDisabled', False):
                                policy['IsDisabled'] = True
                                media_api.post(f"/Users/{u['user_id']}/Policy", json=policy, timeout=5)
                    except Exception: pass
        except Exception: pass


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
        if not get_enable_library_notify(): return
        series_id = data["series_id"]; episodes = data["episodes"]; series_info = data["series_info"]

        season_groups = defaultdict(list)
        for ep in episodes: season_groups[ep.get('ParentIndexNumber', 1)].append(ep)
            
        season_strs = []; total_eps = 0

        for s_idx in sorted(season_groups.keys()):
            s_eps = season_groups[s_idx]
            ep_indices = sorted(list(set([e.get('IndexNumber', 0) for e in s_eps if e.get('IndexNumber') is not None])))
            total_eps += len(ep_indices)
            if len(ep_indices) > 1:
                ranges = []; start = ep_indices[0]; end = ep_indices[0]
                for idx in ep_indices[1:]:
                    if idx == end + 1: end = idx
                    else:
                        ranges.append(f"E{str(start).zfill(2)}" if start == end else f"E{str(start).zfill(2)}-E{str(end).zfill(2)}")
                        start = idx; end = idx
                ranges.append(f"E{str(start).zfill(2)}" if start == end else f"E{str(start).zfill(2)}-E{str(end).zfill(2)}")
                season_strs.append(f"S{str(s_idx).zfill(2)}{', '.join(ranges)}")
            elif len(ep_indices) == 1:
                season_strs.append(f"S{str(s_idx).zfill(2)}E{str(ep_indices[0]).zfill(2)}")

        final_ep_str = ", ".join(season_strs)
        title_suffix = f"{final_ep_str} (共{total_eps}集)" if total_eps > 1 else final_ep_str
        
        if total_eps == 1 and len(episodes) == 1:
            ep_name = episodes[0].get('Name', '')
            if ep_name and "Episode" not in ep_name and "第" not in ep_name: title_suffix += f" {ep_name}"

        series_name = series_info.get('Name', '未知剧集')
        year = series_info.get("ProductionYear", "")
        rating = series_info.get("CommunityRating", "N/A")
        
        overview = str(series_info.get("Overview") or "")
        overview = re.sub(r'<[^>]+>', '', overview).strip()
        if not overview: overview = "暂无简介..."
        if len(overview) > 150: overview = overview[:140] + "..."
        
        # 🔥 获取媒体质量信息（从第一个剧集获取）
        quality_info = {"quality": "", "video_codec": "", "audio_codec": "", "resolution": "", "hdr": "", "quality_icon": ""}
        if episodes:
            ep_id = episodes[0].get('Id', '')
            logger.info(f"[媒体质量] 准备获取剧集质量信息: ep_id={ep_id}")
            quality_info = get_media_quality_info(ep_id)
            logger.info(f"[媒体质量] 获取结果: {quality_info}")
        
        base_url = get_media_server_main_public_or_host() or get_media_server_host()
        if base_url and not base_url.startswith(('http://', 'https://')):
            base_url = 'https://' + base_url
        play_url = f"{base_url}/web/index.html#!/item?id={series_id}&serverId={series_info.get('ServerId','')}"

        # 尝试使用自定义通知模板
        tpl_vars = {
            "series_name": series_name, "episode_info": title_suffix,
            "year": year, "rating": rating,
            "time": datetime.datetime.now().strftime('%Y-%m-%d %H:%M'), "overview": overview,
            # 🔥 新增质量字段
            "quality": quality_info.get("quality", ""),
            "quality_icon": quality_info.get("quality_icon", "📺"),
            "video_codec": quality_info.get("video_codec", ""),
            "audio_codec": quality_info.get("audio_codec", ""),
            "resolution": quality_info.get("resolution", ""),
            "hdr": quality_info.get("hdr", "")
        }
        try:
            from app.plugins import get_plugin
            tpl_plugin = get_plugin("notify_template")
            if tpl_plugin and tpl_plugin.enabled:
                caption = tpl_plugin.render("library_new_episode", tpl_vars)
            else:
                raise Exception("fallback")
        except:
            caption = (f"📺 <b>新入库 剧集 {series_name}</b> {title_suffix}\n\n📌 年份：{year}  |  ⭐ 评分：{rating}\n"
                       f"🕒 时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n📝 <b>剧情简介：</b>\n{overview}")

        keyboard = None
        if base_url and base_url.startswith(('http://', 'https://')):
            keyboard = {"inline_keyboard": [[{"text": "▶️ 立即播放", "url": play_url}]]}
        primary_io = self._download_emby_image(series_id, 'Primary')
        backdrop_io = self._download_emby_image(series_id, 'Backdrop')
        # TG 和企业微信都优先使用横版封面
        tg_img = backdrop_io or primary_io or REPORT_COVER_URL
        wecom_img = backdrop_io or primary_io or REPORT_COVER_URL
        
        # 🔥 根据通知规则发送到指定渠道
        channels = get_notify_channels("library_new")
        platform = "all" if "tg_bot" in channels and "wecom" in channels else \
                   "tg" if "tg_bot" in channels else \
                   "wecom" if "wecom" in channels else "none"
        
        if platform != "none":
            self.send_photo("sys_notify", tg_img, caption, reply_markup=keyboard, platform=platform, wecom_photo_io=wecom_img)
        
        # 🎯 推送到频道（如果配置了）
        if "tg_channel" in channels:
            self._notify_channels(tg_img, caption, keyboard, "episode", series_info)

    def on_library_new_item(self, item):
        if not get_enable_library_notify():
            return
        
        try:
            name = item.get("Name", "未知")
            year = item.get("ProductionYear", "")
            rating = item.get("CommunityRating", "N/A")
            
            overview = str(item.get("Overview") or "")
            overview = re.sub(r'<[^>]+>', '', overview).strip()
            if not overview: overview = "暂无简介..."
            if len(overview) > 150: overview = overview[:140] + "..."
            
            type_raw = item.get("Type")
            type_cn = "电影"; type_icon = "🎬"
            if type_raw in ["Series", "Episode"]: type_cn = "剧集"; type_icon = "📺"
            
            # 获取媒体质量信息
            quality_info = get_media_quality_info(item.get('Id', ''))
            
            base_url = get_media_server_main_public_or_host() or get_media_server_host()
            if base_url and not base_url.startswith(('http://', 'https://')):
                base_url = 'https://' + base_url
            play_url = f"{base_url}/web/index.html#!/item?id={item['Id']}&serverId={item.get('ServerId','')}"

            # 尝试使用自定义通知模板
            tpl_vars = {
                "name": name, "type_icon": type_icon, "type_cn": type_cn,
                "year": year, "rating": rating,
                "time": datetime.datetime.now().strftime('%Y-%m-%d %H:%M'), "overview": overview,
                # 🔥 新增质量字段
                "quality": quality_info.get("quality", ""),
                "quality_icon": quality_info.get("quality_icon", "🎬"),
                "video_codec": quality_info.get("video_codec", ""),
                "audio_codec": quality_info.get("audio_codec", ""),
                "resolution": quality_info.get("resolution", ""),
                "hdr": quality_info.get("hdr", "")
            }
            try:
                from app.plugins import get_plugin
                tpl_plugin = get_plugin("notify_template")
                if tpl_plugin and tpl_plugin.enabled:
                    caption = tpl_plugin.render("library_new_item", tpl_vars)
                else:
                    raise Exception("fallback")
            except Exception as e:
                logger.warning(f"[入库通知] 模板渲染失败，使用默认模板: {e}")
                caption = (f"{type_icon} <b>新入库 {type_cn} {name}</b> ({year})\n\n⭐ 评分：{rating} / 10\n"
                           f"🕒 时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n📝 <b>剧情简介：</b>\n{overview}")
            
            keyboard = None
            if base_url and base_url.startswith(('http://', 'https://')):
                keyboard = {"inline_keyboard": [[{"text": "▶️ 立即播放", "url": play_url}]]}
            primary_io = self._download_emby_image(item['Id'], 'Primary')
            backdrop_io = self._download_emby_image(item['Id'], 'Backdrop')
            tg_img = backdrop_io or primary_io or REPORT_COVER_URL
            wecom_img = backdrop_io or primary_io or REPORT_COVER_URL
            
            channels = get_notify_channels("library_new")
            platform = "all" if "tg_bot" in channels and "wecom" in channels else \
                       "tg" if "tg_bot" in channels else \
                       "wecom" if "wecom" in channels else "none"
            
            if platform != "none":
                self.send_photo("sys_notify", tg_img, caption, reply_markup=keyboard, platform=platform, wecom_photo_io=wecom_img)
            
            if "tg_channel" in channels:
                self._notify_channels(tg_img, caption, keyboard, type_raw.lower() if type_raw else "movie", item)
        except Exception as e:
            logger.error(f"[入库通知] 处理失败: {e}")

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
        if not get_enable_notify():
            logger.info(f"🔇 [播放通知] 开关未开启，跳过")
            return

        # 添加详细日志排查问题
        session = data.get("Session") or data
        item = data.get("Item") or session.get("NowPlayingItem") or {}
        user = data.get("User") or session
        user_name = user.get("Name") or user.get("UserName") or "未知用户"
        user_id = user.get("Id") or session.get("UserId")

        logger.info(f"🔔 [播放通知] 收到 {action} 事件，用户: {user_name} (ID: {user_id})")

        try:
            if self._is_muted(user_id, "playback"):
                logger.info(f"🔇 [播放通知] 用户 {user_name} 被静音，跳过")
                return

            play_state = session.get("PlayState", {})
            playback_info = data.get("PlaybackInfo", {})
            
            pos_ticks = data.get("PlaybackPositionTicks") or data.get("PositionTicks") or playback_info.get("PositionTicks") or play_state.get("PositionTicks") or 0
            run_ticks = item.get("RunTimeTicks") or session.get("NowPlayingItem", {}).get("RunTimeTicks") or data.get("RunTimeTicks") or 0
            
            try: pos_ticks = int(pos_ticks)
            except: pos_ticks = 0
            try: run_ticks = int(run_ticks)
            except: run_ticks = 0

            target_id = item.get("Id")
            raw_type = item.get("Type", "")
            
            series_id = item.get("SeriesId") or session.get("NowPlayingItem", {}).get("SeriesId")
            
            detail_res = {}
            if target_id and user_id:
                try:
                    resp = media_api.get(f"/Users/{user_id}/Items/{target_id}", timeout=2)
                    if resp.status_code == 200:
                        detail_res = resp.json()
                        
                    if pos_ticks <= 0 and session.get("Id"):
                        sess_res = media_api.get("/Sessions", timeout=2).json()
                        for s in sess_res:
                            if s.get("Id") == session.get("Id"):
                                pos_ticks = int(s.get("PlayState", {}).get("PositionTicks") or 0)
                                break
                except Exception: pass

            if run_ticks <= 0:
                run_ticks = int(detail_res.get("RunTimeTicks") or 0)

            overview_raw = detail_res.get("Overview") or item.get("Overview") or ""
            rating_raw = detail_res.get("CommunityRating") or item.get("CommunityRating")

            if not series_id:
                series_id = detail_res.get("SeriesId") or detail_res.get("ParentId")

            if raw_type == "Episode" and series_id:
                if not str(overview_raw).strip() or not rating_raw:
                    try:
                        series_res = media_api.get(f"/Users/{user_id}/Items/{series_id}", timeout=2).json()
                        if not str(overview_raw).strip():
                            overview_raw = series_res.get("Overview") or ""
                        if not rating_raw:
                            rating_raw = series_res.get("CommunityRating")
                    except Exception: pass

            overview = re.sub(r'<[^>]+>', '', str(overview_raw)).strip()
            if not overview:
                overview = "暂无简介..."
            elif len(overview) > 150:
                overview = overview[:140] + "..."

            rating_str = f"{rating_raw}/10" if rating_raw else "无"

            title = item.get("Name") or "未知内容"
            ep_info = ""
            type_map = {"Episode": "剧集", "Movie": "电影", "Audio": "音乐", "MusicVideo": "MV", "LiveTvProgram": "直播", "TvChannel": "频道"}
            type_cn = type_map.get(raw_type, "媒体")
            
            if raw_type == "Episode" and item.get("SeriesName"): 
                idx = item.get("IndexNumber", 0); parent_idx = item.get("ParentIndexNumber", 1)
                ep_info = f" S{str(parent_idx).zfill(2)}E{str(idx).zfill(2)} {title}"
                title = f"{item.get('SeriesName')}"
            elif raw_type == "Audio" and item.get("Artists"):
                artist_str = ", ".join(item.get("Artists"))
                title = f"{title} - {artist_str}"
            
            emoji = "▶️" if action == "start" else "⏹️"; act = "开始播放" if action == "start" else "停止播放"
            # IP 信息通过 webhook 保存，这里重新获取用于通知
            ip = session.get("RemoteEndPoint") or data.get("RemoteEndPoint") or "127.0.0.1"
            loc = get_location(ip)

            if run_ticks <= 1:
                progress_str = "🟢 实时流/未知总时长"
            else:
                pct = int((pos_ticks / run_ticks) * 100)
                pct = min(max(pct, 0), 100)
                pos_str = self._format_ticks(pos_ticks)
                run_str = self._format_ticks(run_ticks)
                progress_str = f"{pos_str} / {run_str} ({pct}%)"

            client = session.get("Client") or data.get("Client") or "未知端"
            device = session.get("DeviceName") or data.get("DeviceName") or "未知设备"

            # 尝试使用自定义通知模板
            template_key = "playback_start" if action == "start" else "playback_stop"
            tpl_vars = {
                "username": user_name, "title": title, "ep_info": ep_info,
                "type_cn": type_cn, "rating": rating_str, "progress": progress_str,
                "ip": ip, "location": loc, "client": client, "device": device,
                "time": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "overview": overview
            }
            try:
                from app.plugins import get_plugin
                tpl_plugin = get_plugin("notify_template")
                if tpl_plugin and tpl_plugin.enabled:
                    msg = tpl_plugin.render(template_key, tpl_vars)
                else:
                    raise Exception("fallback")
            except:
                msg = (f"{emoji} <b>【{user_name}】{act} {type_cn} {title}</b>{ep_info}\n\n"
                       f"⭐ <b>评分：</b>{rating_str} ｜ 📚 <b>类型：</b>{type_cn}\n"
                       f"🔄 <b>进度：</b>{progress_str}\n"
                       f"🌐 <b>IP地址：</b>{ip} {loc}\n"
                       f"📱 <b>设备：</b>{client} {device}\n"
                       f"🕒 <b>时间：</b>{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                       f"📝 <b>剧情：</b>{overview}")
            
            target_jump_id = target_id
            if raw_type == "Episode" and series_id: target_jump_id = series_id
            elif raw_type == "Audio" and item.get("AlbumId"): target_jump_id = item.get("AlbumId")
            
            base_url = get_media_server_main_public_or_host() or get_media_server_host()
            if base_url and not base_url.startswith(('http://', 'https://')):
                base_url = 'https://' + base_url

            # 只有有效的http/https URL才添加按钮
            keyboard = None
            if base_url and base_url.startswith(('http://', 'https://')):
                play_url = f"{base_url}/web/index.html#!/item?id={target_jump_id}&serverId={item.get('ServerId','')}"
                keyboard = {"inline_keyboard": [[{"text": "🔗 跳转详情", "url": play_url}]]}

            primary_io = self._download_emby_image(target_jump_id, 'Primary') 
            backdrop_io = self._download_emby_image(target_jump_id, 'Backdrop')
            if not primary_io and not backdrop_io:
                primary_io = self._download_emby_image(item.get("Id"), 'Primary')
                backdrop_io = self._download_emby_image(item.get("Id"), 'Backdrop')

            # TG 和企业微信都优先使用横版封面
            tg_img = backdrop_io or primary_io or REPORT_COVER_URL
            wecom_img = backdrop_io or primary_io or REPORT_COVER_URL
            self.send_photo("sys_notify", tg_img, msg, reply_markup=keyboard, platform="all", wecom_photo_io=wecom_img)
        except Exception as e: 
            logger.error(f"[Bot] Playback event error: {e}")

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
        data = cq.get("data", ""); cid = str(cq["message"]["chat"]["id"])
        mid = cq["message"]["message_id"]; cq_id = cq["id"]; token = get_notify_tg_bot_token()
        proxies = get_safe_proxies()
        
        # 🔥 权限检查：对于管理类操作，检查用户是否有权限
        if data.startswith("req_") or data.startswith("feed_"):
            user_id = cq.get("from", {}).get("id")
            if not self._check_admin_permission(cid, user_id):
                # 回复无权限提示
                try:
                    telegram_client.post_api(
                        token,
                        "answerCallbackQuery",
                        json={"callback_query_id": cq_id, "text": "⛔ 您没有权限执行此操作", "show_alert": True},
                        proxies=proxies,
                        timeout=5,
                    )
                except Exception: pass
                return
        
        try: telegram_client.post_api(token, "answerCallbackQuery", json={"callback_query_id": cq_id}, proxies=proxies, timeout=5)
        except Exception: pass

        # 插件回调分发
        if data.startswith("p115_"):
            try:
                from app.plugins.cloud115.plugin import handle_115_callback, handle_115_offline_callback
                # 转存回调: p115_tf_xxx
                if data.startswith("p115_tf_"):
                    if handle_115_callback(data, cid, cq_id, "tg"):
                        return
                # 离线回调: p115_ol_xxx
                elif data.startswith("p115_ol_"):
                    if handle_115_offline_callback(data, cid, cq_id, "tg"):
                        return
            except Exception: pass

        # 影巢搜索回调: hdhive_sr_xxx (115资源选择)
        if data.startswith("hdhive_sr_"):
            try:
                from app.plugins.hdhive.plugin import handle_hdhive_search_callback
                if handle_hdhive_search_callback(data, cid, cq_id, "tg"):
                    return
            except Exception: pass

        # 影巢 TMDB 选择回调: hdhive_tmdb_xxx
        if data.startswith("hdhive_tmdb_"):
            try:
                from app.plugins.hdhive.plugin import handle_hdhive_tmdb_callback
                if handle_hdhive_tmdb_callback(data, cid, cq_id, "tg"):
                    return
            except Exception: pass

        # 影巢 TMDB 分页回调: hdhive_tmdbprev_xxx 或 hdhive_tmdbnext_xxx
        logger.info(f"[Bot] 检查TMDB分页回调: data={data[:50]}...")
        if data.startswith("hdhive_tmdbprev_") or data.startswith("hdhive_tmdbnext_") or data.startswith("hdhive_tmdbpage_"):
            logger.info(f"[Bot] 匹配到TMDB分页回调: {data}")
            try:
                from app.plugins.hdhive.plugin import handle_hdhive_tmdbpage_callback
                message_id = cq.get("message", {}).get("message_id")
                result = handle_hdhive_tmdbpage_callback(data, cid, cq_id, "tg", message_id)
                logger.info(f"[Bot] TMDB分页回调结果: {result}")
                if result:
                    return
            except Exception as e:
                logger.error(f"[Bot] TMDB分页回调异常: {e}")
                pass

        # 影巢翻页回调: hdhive_page_xxx
        if data.startswith("hdhive_page_"):
            try:
                from app.plugins.hdhive.plugin import handle_hdhive_page_callback
                message_id = cq.get("message", {}).get("message_id")
                if handle_hdhive_page_callback(data, cid, cq_id, "tg", message_id):
                    return
            except Exception: pass

        # Emby 重启回调: emby_restart:index 或 emby_restart:all
        if data.startswith("emby_restart:"):
            notification_bot_emby_restart_command_service.handle_emby_restart_callback(
                self, data, cid, cq, platform="tg"
            )
            return

        # 求片通知影巢搜索回调: req_hdhive_xxx
        if data.startswith("req_hdhive_"):
            try:
                from app.plugins.hdhive.plugin import handle_request_hdhive_callback
                if handle_request_hdhive_callback(data, cid, cq_id, "tg"):
                    return
            except Exception as e:
                logger.error(f"[Bot] 求片影巢搜索回调异常: {e}")

        # 消息中心回调处理
        if data.startswith("msg_reply:"):
            user_id = data.replace("msg_reply:", "")
            self._handle_msg_reply_callback(cid, mid, user_id, token, proxies)
            return

        if data.startswith("msg_block:"):
            user_id = data.replace("msg_block:", "")
            self._handle_msg_block_callback(cid, mid, user_id, token, proxies, cq)
            return

        if data.startswith("msg_cancel:"):
            # 取消回复模式
            self._msg_reply_mode.discard(cid)
            try:
                telegram_client.post_api(token, "editMessageText", json={
                    "chat_id": cid, "message_id": mid,
                    "text": "❌ 已取消回复",
                    "reply_markup": {"inline_keyboard": []}
                }, proxies=proxies, timeout=5)
            except Exception: pass
            return

        if data.startswith("msg_unblock:"):
            user_id = data.replace("msg_unblock:", "")
            self._handle_msg_unblock_callback(cid, mid, user_id, token, proxies, cq)
            return

        if data.startswith("risk_ban_"):
            uid = data.replace("risk_ban_", "")
            from app.domains.risk.risk_service import ban_user, log_risk_action
            
            operator = cq.get('from', {}).get('first_name', 'Admin')
            target_username = self._get_username(uid) 
            
            if ban_user(uid):
                log_risk_action(uid, target_username, "ban", f"机器快捷执法 (操作人: {operator})")
                action_text = f"✅ 已成功封禁该违规账号！\n(执行人: {operator})"
            else:
                action_text = "❌ 封禁失败，可能 API 权限不足。"
                
            msg_obj = cq["message"]
            orig_text = msg_obj.get("text", "风控警报")
            new_text = f"{orig_text}\n\n━━━━━━━━━━━━━━\n{action_text}"
            try: telegram_client.post_api(token, "editMessageText", json={"chat_id": cid, "message_id": mid, "text": new_text, "reply_markup": {"inline_keyboard": []}}, proxies=proxies, timeout=5)
            except Exception: pass
            return

        if data.startswith("feed_"):
            parts = data.split("_")
            action = parts[1]; feed_id = int(parts[2])
            status_map = {"fix": 1, "done": 2, "reject": 3}
            status_text = {"fix": "🛠️ 已标记：修复中", "done": "✅ 已标记：修复完成", "reject": "❌ 已标记：暂不处理(忽略)"}
            
            if action in status_map:
                media_request_dao.update_feedback_status(feed_id, status_map[action])
                msg_obj = cq["message"]
                operator = cq.get('from', {}).get('first_name', 'Admin')
                if "caption" in msg_obj:
                    orig_text = msg_obj.get("caption", "资源报错工单")
                    new_text = f"{orig_text}\n\n━━━━━━━━━━━━━━\n{status_text[action]}\n(操作人: {operator})"
                    try: telegram_client.post_api(token, "editMessageCaption", json={"chat_id": cid, "message_id": mid, "caption": new_text, "reply_markup": {"inline_keyboard": []}}, proxies=proxies, timeout=5)
                    except Exception: pass
                else:
                    orig_text = msg_obj.get("text", "资源报错工单")
                    new_text = f"{orig_text}\n\n━━━━━━━━━━━━━━\n{status_text[action]}\n(操作人: {operator})"
                    try: telegram_client.post_api(token, "editMessageText", json={"chat_id": cid, "message_id": mid, "text": new_text, "reply_markup": {"inline_keyboard": []}}, proxies=proxies, timeout=5)
                    except Exception: pass
            return

        if data.startswith("req_"):
            parts = data.split("_")
            action = parts[1]
            
            # 处理影巢搜索回调
            if action == "hdhive":
                try:
                    from app.plugins.hdhive.plugin import handle_request_hdhive_search
                    handle_request_hdhive_search(data, cid, cq_id, "tg")
                except Exception as e:
                    logger.error(f"[Bot] 影巢搜索回调处理失败: {e}")
                    try:
                        telegram_client.post_api(
                            token,
                            "editMessageReplyMarkup",
                            json={"chat_id": cid, "message_id": mid, "reply_markup": {"inline_keyboard": []}},
                            proxies=proxies,
                            timeout=5,
                        )
                    except Exception: pass
                return
            
            if action == "reject" and len(parts) > 2 and parts[2] == "menu":
                tid = parts[3]
                reasons = ["影片未上映", "剧集未开播", "未找到可用资源", "质量太差等待洗版"]
                keyboard = {"inline_keyboard": [
                    [{"text": reasons[0], "callback_data": f"req_reject_do_{tid}_0"}, {"text": reasons[1], "callback_data": f"req_reject_do_{tid}_1"}],
                    [{"text": reasons[2], "callback_data": f"req_reject_do_{tid}_2"}, {"text": reasons[3], "callback_data": f"req_reject_do_{tid}_3"}],
                    [{"text": "🔙 取消返回", "callback_data": f"req_back_{tid}"}]
                ]}
                try: telegram_client.post_api(token, "editMessageReplyMarkup", json={"chat_id": cid, "message_id": mid, "reply_markup": keyboard}, proxies=proxies, timeout=5)
                except Exception: pass
                return
            
            elif action == "back":
                tid = parts[2]; admin_url = get_pulse_url() or "http://127.0.0.1:10307"
                # 检查影巢插件是否启用
                hdhive_enabled = False
                try:
                    from app.plugins import get_plugin
                    hdhive_plugin = get_plugin("hdhive")
                    hdhive_enabled = hdhive_plugin and hdhive_plugin.enabled
                except:
                    pass
                # 尝试从数据库获取求片信息以构建影巢搜索按钮
                r = media_request_dao.get_request_summary_by_tmdb(tid)
                if hdhive_enabled and r:
                    title_safe = r["title"].replace("_", "-").replace(" ", "-")
                    keyboard = {"inline_keyboard": [
                        [{"text": "🚀 推送 MP", "callback_data": f"req_approve_{tid}"}, {"text": "✋ 手动接单", "callback_data": f"req_manual_{tid}"}],
                        [{"text": "🔍 影巢搜索", "callback_data": f"req_hdhive_{tid}_{r['media_type']}_0_{title_safe}"}, {"text": "❌ 拒绝求片", "callback_data": f"req_reject_menu_{tid}"}],
                        [{"text": "💻 网页审批", "url": f"{admin_url}/requests_admin"}]
                    ]}
                else:
                    keyboard = {"inline_keyboard": [
                        [{"text": "🚀 推送 MP", "callback_data": f"req_approve_{tid}"}, {"text": "✋ 手动接单", "callback_data": f"req_manual_{tid}"}],
                        [{"text": "❌ 拒绝求片", "callback_data": f"req_reject_menu_{tid}"}, {"text": "💻 网页审批", "url": f"{admin_url}/requests_admin"}]
                    ]}
                try: telegram_client.post_api(token, "editMessageReplyMarkup", json={"chat_id": cid, "message_id": mid, "reply_markup": keyboard}, proxies=proxies, timeout=5)
                except Exception: pass
                return

            tid = parts[2]; reject_reason = None
            if action == "reject" and len(parts) > 2 and parts[2] == "do":
                tid = parts[3]; r_idx = int(parts[4])
                reasons = ["影片未上映", "剧集未开播", "未找到可用资源", "质量太差等待洗版"]
                reject_reason = reasons[r_idx]; action_db = "reject"
            else:
                action_db = action

            rows = media_request_dao.list_pending_requests_by_tmdb(tid)
            if not rows:
                try: telegram_client.post_api(token, "editMessageReplyMarkup", json={"chat_id": cid, "message_id": mid, "reply_markup": {"inline_keyboard": []}}, proxies=proxies, timeout=5)
                except Exception: pass
                return
                
            if action_db == "approve":
                mp_url = get_moviepilot_url(); mp_token = get_moviepilot_token()
                for r in rows:
                    if mp_url and mp_token:
                        payload = { "name": r["title"], "tmdbid": int(tid), "year": str(r["year"]), "type": "电影" if r["media_type"]=="movie" else "电视剧" }
                        if r["media_type"] == "tv": payload["season"] = r['season']
                        try: moviepilot_client.subscribe(mp_url, mp_token, payload, timeout=10)
                        except Exception: pass
                    media_request_dao.update_media_request_status(tid, r['season'], 1)
                action_text = "✅ 已审批：推送 MP 自动下载"
            elif action_db == "manual":
                for r in rows: media_request_dao.update_media_request_status(tid, r['season'], 4)
                action_text = "✅ 已审批：管理员手动接单"
            elif action_db == "reject":
                for r in rows: media_request_dao.update_media_request_status(tid, r['season'], 3, reject_reason)
                action_text = f"❌ 已拒绝 ({reject_reason})"
                
            msg_obj = cq["message"]
            operator = cq.get('from', {}).get('first_name', 'Admin')
            if "caption" in msg_obj:
                orig_caption = msg_obj.get("caption", "求片请求")
                _record_request_admin_message(tid, cid, mid, True, orig_caption)
                _sync_request_admin_messages(tid, action_text, operator, token, proxies, orig_caption, True)
            else:
                orig_text = msg_obj.get("text", "求片请求")
                _record_request_admin_message(tid, cid, mid, False, orig_text)
                _sync_request_admin_messages(tid, action_text, operator, token, proxies, orig_text, False)

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
