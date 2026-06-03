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
from app.domains.notifications import notification_bot_delivery_service
from app.domains.notifications import notification_bot_message_center_callback_service
from app.domains.notifications import notification_bot_media_helper_service
from app.domains.notifications import notification_bot_media_quality_service
from app.domains.notifications import notification_bot_playback_command_service
from app.domains.notifications import notification_bot_request_admin_message_sync_service
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

def _submit_bot_task(fn, *args):
    if not _bot_executor_slots.acquire(blocking=False):
        logger.warning("[Bot] 后台任务队列已满，丢弃本次异步任务")
        return False
    future = _bot_executor.submit(fn, *args)
    future.add_done_callback(lambda _f: _bot_executor_slots.release())
    return True

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
        uid = data.get("user_id", "")
        username = data.get("username", "未知")
        current = data.get("current", 0)
        limit = data.get("limit", 0)
        devices_info = data.get("devices_info", "未知设备")
        violation_action = data.get("violation_action", "warn_only")
        
        # 根据处理方式显示不同的状态标签
        action_text = {
            "warn_only": "🔔 仅提醒管理员",
            "warn_user": "📢 已警告用户",
            "auto_ban": "🚫 已自动封禁"
        }.get(violation_action, "🔔 仅提醒管理员")
        
        msg = (f"🚨 <b>【风控预警】 账号并发越界</b>\n\n"
               f"👤 <b>涉事用户：</b>{username}\n"
               f"📈 <b>当前并发：</b>{current} / 额度 {limit}\n"
               f"📱 <b>违规设备：</b>\n{devices_info}\n"
               f"⚙️ <b>处理方式：</b>{action_text}\n\n"
               f"⚠️ <i>天眼系统已记录，请立即进行处置！</i>")
        
        keyboard = {"inline_keyboard": []}
        # 自动封禁模式下不显示封禁按钮
        if uid and violation_action != "auto_ban":
            keyboard["inline_keyboard"].append([{"text": "🚫 立即封禁此违规账号", "callback_data": f"risk_ban_{uid}"}])
            
        admin_url = get_pulse_url() or get_media_server_main_public_or_host()
        if admin_url:
            risk_url = f"{admin_url.rstrip('/')}/risk"
            keyboard["inline_keyboard"].append([{"text": "🛡️ 前往风控大盘拔网线", "url": risk_url}])
            
        self.send_message("sys_notify", msg, reply_markup=keyboard if keyboard["inline_keyboard"] else None, platform="all")

        try:
            add_system_notification(
                notify_type="risk",
                title=f"🚨 并发越界: {username}",
                message=f"当前并发 {current} / 额度 {limit}，处理: {action_text}",
                action_url="/risk"
            )
        except Exception as e:
            logger.error(f"写入风控通知失败: {e}")

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
        # 检查通知规则配置
        try:
            from app.domains.notifications.notify_admin import get_notify_rule
            rule = get_notify_rule('user_login')
            if not rule or not rule.get('enabled'):
                return
        except:
            # 兜底：使用旧配置
            if not get_notify_user_login(): return
        
        try:
            user = data.get("User") or {}
            session = data.get("Session") or {}
            user_id = user.get("Id") or data.get("UserId")
            user_name = user.get("Name") or data.get("Title") or data.get("UserName") or "未知账号"
            
            if self._is_muted(user_id, "login"):
                logger.info(f"🔇 [静音规则] 拦截了用户 {user_name} 的登录通知")
                return

            ip = session.get("RemoteEndPoint") or data.get("RemoteEndPoint") or "127.0.0.1"
            loc = get_location(ip)
            client = session.get("Client") or data.get("Client") or data.get("AppName") or "未知设备"
            dev_name = session.get("DeviceName") or data.get("DeviceName") or "未知终端"
            
            msg = (f"🔐 <b>安全预警：账号登录</b>\n\n"
                   f"👤 <b>用户：</b>{user_name}\n"
                   f"🌐 <b>网络：</b>{ip} ({loc})\n"
                   f"📱 <b>设备：</b>{client} ({dev_name})\n"
                   f"🕒 <b>时间：</b>{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # 根据规则发送到指定渠道
            try:
                from app.domains.notifications.notify_admin import get_notify_rule
                rule = get_notify_rule('user_login')
                channels = rule.get('channels', []) if rule else []
                
                # TG机器人/企业微信
                if 'tg_bot' in channels or 'wecom' in channels:
                    avatar_io = self._download_user_image(user_id) if user_id else None
                    fallback_img = "https://api.dicebear.com/9.x/notionists/png?seed=" + urllib.parse.quote(user_name)
                    tg_img = avatar_io or fallback_img
                    platform = "all" if ('tg_bot' in channels and 'wecom' in channels) else ("tg" if 'tg_bot' in channels else "wecom")
                    self.send_photo("sys_notify", tg_img, msg, platform=platform, wecom_photo_io=tg_img)
                
                # Web通知中心
                if 'web' in channels:
                    from app.infra.db.notification_dao import add_system_notification
                    add_system_notification("user", f"用户登录: {user_name}", f"{ip} ({loc}) - {client}", "/users_manage")
            except Exception as e:
                logger.error(f"[用户登录通知] 发送失败: {e}")
                # 兜底：使用旧方式
                avatar_io = self._download_user_image(user_id) if user_id else None
                fallback_img = "https://api.dicebear.com/9.x/notionists/png?seed=" + urllib.parse.quote(user_name)
                tg_img = avatar_io or fallback_img
                self.send_photo("sys_notify", tg_img, msg, platform="all", wecom_photo_io=tg_img)
        except Exception as e: logger.error(f"登录通知组装异常: {e}")

    def on_item_deleted(self, data):
        if not get_notify_item_deleted(): return
        try:
            item = data.get("Item") or data
            raw_type = item.get("Type", "")
            title = item.get("Name") or item.get("Title") or "未知资源"
            
            # 用户删除通知已移到 users.py，这里跳过
            if raw_type == "User" or "删除了用户" in title:
                return

            series_name = item.get("SeriesName")
            season_num = item.get("ParentIndexNumber")
            ep_num = item.get("IndexNumber")
            year = item.get("ProductionYear", "")
            item_id = str(item.get("Id", ""))
            unique_name = f"{series_name}_{season_num}_{ep_num}_{title}" if series_name else title
            
            now = time.time()
            if (item_id and item_id in self.delete_cache and (now - self.delete_cache[item_id] < 300)) or \
               (unique_name and unique_name in self.delete_cache and (now - self.delete_cache[unique_name] < 300)):
                return  
                
            if item_id: self.delete_cache[item_id] = now
            if unique_name: self.delete_cache[unique_name] = now
            self.delete_cache = {k: v for k, v in self.delete_cache.items() if now - v < 600}
            
            year_str = f" ({year})" if year else ""
            del_type = "媒体"
            
            if raw_type == "Movie": del_type = "电影"
            elif raw_type == "Series": del_type = "整剧"
            elif raw_type == "Season":
                del_type = "整季"
                s_num = ep_num if ep_num is not None else season_num
                title = f"{series_name or title} - 第 {s_num} 季" if s_num else f"{series_name or title}"
            elif raw_type == "Episode" or (series_name and ep_num is not None):
                del_type = "单集"
                s_str = str(season_num).zfill(2) if season_num is not None else "01"
                e_str = str(ep_num).zfill(2) if ep_num is not None else "XX"
                title = f"{series_name or '未知剧集'} S{s_str}E{e_str} {title}"
            
            msg = (f"🗑️ <b>系统告警：{del_type}被删除</b>\n\n"
                   f"🎬 <b>内容：</b>{title}{year_str}\n"
                   f"🕒 <b>时间：</b>{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                   f"<i>* 该项目已从媒体库物理存储中被永久移除。</i>")
            
            primary_io = self._download_emby_image(item.get("Id"), 'Primary') if item.get("Id") else None
            backdrop_io = self._download_emby_image(item.get("Id"), 'Backdrop') if item.get("Id") else None
            if not primary_io and not backdrop_io and item.get("SeriesId"): primary_io = self._download_emby_image(item.get("SeriesId"), 'Primary')
            
            tmdb_img_url = None
            if not primary_io and not backdrop_io:
                tmdb_id = item.get("ProviderIds", {}).get("Tmdb")
                if not tmdb_id and item.get("SeriesProviderIds"): tmdb_id = item.get("SeriesProviderIds", {}).get("Tmdb")
                if tmdb_id and tmdb_client.api_key:
                    try:
                        proxies = get_safe_proxies()
                        if raw_type == "Movie":
                            tmdb_res = tmdb_client.get_movie_details(tmdb_id, proxies=proxies, timeout=5)
                        else:
                            tmdb_res = tmdb_client.get_tv_details(tmdb_id, proxies=proxies, timeout=5)
                        if tmdb_res.status_code == 200:
                            p_path = tmdb_res.json().get("poster_path")
                            if p_path: tmdb_img_url = f"https://image.tmdb.org/t/p/w500{p_path}"
                    except Exception: pass
            
            tg_img = primary_io or backdrop_io or tmdb_img_url or REPORT_COVER_URL
            self.send_photo("sys_notify", tg_img, msg, platform="all", wecom_photo_io=tg_img)
        except Exception as e: logger.error(f"删除通知组装异常: {e}")

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
        token = get_notify_tg_bot_token()
        
        while self.running and not self._stop_event.is_set():
            raw_cids = str(get_tg_chat_id())
            admin_ids = [c.strip() for c in raw_cids.replace('，', ',').split(',') if c.strip()]
            
            try:
                res = telegram_client.get_updates(token, params={"offset": self.offset, "timeout": 30}, proxies=get_safe_proxies(), timeout=35)
                if res.status_code == 200:
                    for u in res.json().get("result", []):
                        self.offset = u["update_id"] + 1
                        if "message" in u:
                            msg_obj = u["message"]
                            cid = str(msg_obj["chat"]["id"])
                            chat_type = msg_obj["chat"].get("type", "")
                            
                            # 🔥 静默跳过群组/频道消息，只处理管理员私聊
                            if chat_type in ["group", "supergroup", "channel"]:
                                continue
                            
                            # 🔥 安全检查：必须配置 tg_chat_id 且 chat_id 在白名单中
                            if not admin_ids or cid not in admin_ids:
                                continue
                            
                            # 提取文本：优先 text，其次 caption（图文消息）
                            msg_text = msg_obj.get("text", "") or msg_obj.get("caption", "")
                            # 从 entities/caption_entities 中提取 URL 类型的链接
                            for ent in msg_obj.get("entities", []) + msg_obj.get("caption_entities", []):
                                if ent.get("type") == "text_link" and ent.get("url"):
                                    msg_text += " " + ent["url"]
                            self._handle_message(msg_text, cid, platform="tg")
                        elif "callback_query" in u:
                            cq = u["callback_query"]
                            cid = str(cq["message"]["chat"]["id"])
                            # 🔥 安全检查：必须配置 tg_chat_id 且 chat_id 在白名单中
                            if not admin_ids or cid not in admin_ids:
                                continue
                            _submit_bot_task(self._handle_callback, cq)
                else:
                    if self._stop_event.wait(5): return
            except:
                if self._stop_event.wait(5): return

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
            try:
                from app.plugins import get_plugin_config, get_plugin
                plugin = get_plugin("emby_restart")
                if not plugin or not plugin.enabled:
                    self.send_message(cid, "❌ Emby 自动重启插件未启用", platform="tg")
                    return
                
                config = get_plugin_config("emby_restart")
                servers = config.get("servers", [])
                
                action = data.split(":")[1]
                
                if action == "all":
                    # 重启全部
                    self.send_message(cid, f"🔄 正在重启全部 {len(servers)} 台 Emby 服务器...", platform="tg")
                    result = plugin.manual_restart()
                    if result.get("success"):
                        self.send_message(cid, f"✅ {result.get('message', '重启成功')}", platform="tg")
                    else:
                        self.send_message(cid, f"❌ {result.get('message', '重启失败')}", platform="tg")
                else:
                    # 重启单个服务器
                    index = int(action)
                    if index < 0 or index >= len(servers):
                        self.send_message(cid, "❌ 服务器不存在", platform="tg")
                        return
                    
                    server = servers[index]
                    name = server.get('name', '未命名')
                    self.send_message(cid, f"🔄 正在重启服务器 [{name}]...", platform="tg")
                    
                    result = plugin._restart_via_emby_api(server.get('host'), server.get('api_key'))
                    if result.get("success"):
                        self.send_message(cid, f"✅ 服务器 [{name}] 重启成功", platform="tg")
                    else:
                        self.send_message(cid, f"❌ 服务器 [{name}] 重启失败: {result.get('message', '未知错误')}", platform="tg")
                return
            except Exception as e:
                logger.error(f"[Bot] emby_restart callback error: {e}")
                self.send_message(cid, f"❌ 执行失败: {str(e)}", platform="tg")
                return
            except Exception: pass

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
        token = get_notify_tg_bot_token()
        if not token: return
        cmds = [
            {"command": "search", "description": "🔍 搜索资源"}, 
            {"command": "stats", "description": "📊 今日日报"}, 
            {"command": "weekly", "description": "📅 本周周报"}, 
            {"command": "monthly", "description": "🗓️ 本月月报"}, 
            {"command": "yearly", "description": "📜 年度总结"}, 
            {"command": "now", "description": "🟢 正在播放"}, 
            {"command": "latest", "description": "🆕 最近入库"}, 
            {"command": "recent", "description": "📜 最近播放记录"}, 
            {"command": "check", "description": "📡 系统探针"}, 
            {"command": "calendar", "description": "📺 今日更新"}, 
            {"command": "emby_restart", "description": "🔄 重启Emby(Pro)"},
            {"command": "whois", "description": "👤 查询绑定信息"},
            {"command": "help", "description": "🤖 帮助菜单"}
        ]
        try: telegram_client.post_api(token, "setMyCommands", json={"commands": cmds}, proxies=get_safe_proxies(), timeout=10)
        except Exception: pass

    def _is_admin(self, cid, platform="tg"):
        """检查 chat_id 是否为配置的管理员"""
        if platform == "tg":
            raw_cids = str(get_tg_chat_id())
            admin_ids = [c.strip() for c in raw_cids.replace('，', ',').split(',') if c.strip()]
            return bool(admin_ids and str(cid) in admin_ids)
        elif platform == "wecom":
            # 企业微信通过 touser 配置控制
            return True  # WeCom 消息由 API 直接发送，已受限
        return False

    def _handle_message(self, text, cid, platform="tg"):
        text = text.strip()
        
        # 检查是否在回复模式
        if hasattr(self, '_msg_reply_mode') and cid in self._msg_reply_mode:
            self._handle_msg_reply_message(text, cid)
            return
        
        # 🔥 注意：更具体的命令要放在前面，避免被短命令匹配
        if text.startswith("/check"): self._cmd_check(cid, platform)
        elif text.startswith("/search"): self._cmd_search(cid, text, platform)
        elif text.startswith("/stats"): self._cmd_stats(cid, 'day', platform)
        elif text.startswith("/weekly"): self._cmd_stats(cid, 'week', platform)
        elif text.startswith("/monthly"): self._cmd_stats(cid, 'month', platform)
        elif text.startswith("/yearly"): self._cmd_stats(cid, 'year', platform)
        elif text.startswith("/now"): self._cmd_now(cid, platform)
        elif text.startswith("/latest"): self._cmd_latest(cid, platform)
        elif text.startswith("/recent"): self._cmd_recent(cid, platform)
        elif text.startswith("/calendar"): self._cmd_calendar(cid, platform)
        elif text.startswith("/emby_restart"): self._cmd_emby_restart(cid, text, platform)
        elif text.startswith("/whois"): self._cmd_whois(cid, text, platform)
        elif text.startswith("/help"): self._cmd_help(cid, platform)
        else:
            # 非命令消息，仅管理员可触发事件总线
            if not self._is_admin(cid, platform):
                logger.warning(f"[Bot] 非管理员用户尝试发送非命令消息: {cid}")
                return
            logger.info(f"[Bot] 非命令消息，发布到事件总线: {text[:50]}...")
            bus.publish("bot.admin_message", text, cid, platform)

    def _cmd_latest(self, cid, platform):
        try:
            user_id = get_admin_id()
            if not user_id: return self.send_message(cid, "❌ 错误: 无法获取 Emby 用户身份", platform=platform)
            fields = "DateCreated,Name,SeriesName,Type,ParentIndexNumber,IndexNumber"
            params = {"IncludeItemTypes": "Movie,Episode", "Limit": 8, "Fields": fields}
            
            res = media_api.get(f"/Users/{user_id}/Items/Latest", params=params, timeout=10)
            if res.status_code != 200: return self.send_message(cid, f"❌ 查询失败", platform=platform)
            
            items = res.json()
            if not items: return self.send_message(cid, "📭 最近没有新入库的资源", platform=platform)

            msg = "🆕 <b>最近入库 (Top 8)</b>\n\n"
            for i in items:
                name = i.get("Name", "未知")
                item_type = i.get("Type")
                
                if item_type == "Episode" and i.get("SeriesName"):
                    s_idx = str(i.get("ParentIndexNumber", 0)).zfill(2) if i.get("ParentIndexNumber") is not None else "01"
                    e_idx = str(i.get("IndexNumber", 0)).zfill(2) if i.get("IndexNumber") is not None else "XX"
                    name = f"《{i.get('SeriesName')}》 S{s_idx}E{e_idx} {name}"
                elif item_type == "Movie":
                    name = f"《{name}》"
                
                date_raw = i.get("DateCreated")
                date_str = date_raw[:10] if date_raw else "未知时间"
                type_icon = "🎬" if item_type == "Movie" else "📺"
                
                msg += f"{type_icon} <code>{date_str}</code> | <b>{name}</b>\n"
                
            self.send_message(cid, msg.strip(), platform=platform)
        except Exception as e:
            logger.error(f"[Bot] latest query error: {e}")
            self.send_message(cid, f"❌ 查询异常", platform=platform)

    def _extract_tech_info(self, item):
        sources = item.get("MediaSources", [])
        if not sources: return "📼 未知"
        info_parts = []
        video = next((s for s in sources[0].get("MediaStreams", []) if s.get("Type") == "Video"), None)
        if video:
            w = video.get("Width", 0)
            if w >= 3800: res = "4K"
            elif w >= 1900: res = "1080P"
            elif w >= 1200: res = "720P"
            else: res = "SD"
            extra = []
            v_range = video.get("VideoRange", "")
            title = video.get("DisplayTitle", "").upper()
            if "HDR" in v_range or "HDR" in title: extra.append("HDR")
            if "DOVI" in title or "DOLBY VISION" in title: extra.append("DoVi")
            res_str = f"{res} {' '.join(extra)}"
            info_parts.append(res_str.strip())
            bitrate = sources[0].get("Bitrate", 0)
            if bitrate > 0: info_parts.append(f"{round(bitrate / 1000000, 1)}Mbps")
        return " | ".join(info_parts) if info_parts else "📼 未知"

    def _cmd_search(self, chat_id, text, platform):
        parts = text.split(' ', 1)
        if len(parts) < 2: return self.send_message(chat_id, "🔍 请使用: /search 关键词", platform=platform)
        keyword = parts[1].strip()
        try:
            user_id = get_admin_id()
            if not user_id: return self.send_message(chat_id, "❌ 错误: 无法获取 Emby 用户身份", platform=platform)

            fields = "ProductionYear,Type,Id" 
            params = {"SearchTerm": keyword, "IncludeItemTypes": "Movie,Series", "Recursive": "true", "Fields": fields, "Limit": 5}
            res = media_api.get(f"/Users/{user_id}/Items", params=params, timeout=10)
            if res.status_code != 200: return self.send_message(chat_id, f"❌ 搜索失败", platform=platform)
            items = res.json().get("Items", [])
            if not items: return self.send_message(chat_id, f"📭 未找到与 <b>{keyword}</b> 相关的资源", platform=platform)
            
            top = items[0]
            type_raw = top.get("Type")
            tech_info_str = "查询中..."; ep_count_str = ""; details = {}

            try:
                if type_raw == "Series":
                    details = media_api.get(
                        f"/Users/{user_id}/Items/{top['Id']}",
                        params={"Fields": "Overview,CommunityRating,Genres,RecursiveItemCount"},
                        timeout=5,
                    ).json()
                    ep_count = details.get("RecursiveItemCount", 0)
                    ep_count_str = f"📊 共 {ep_count} 集"
                    sample_res = media_api.get(
                        f"/Users/{user_id}/Items",
                        params={"ParentId": top['Id'], "Recursive": "true", "IncludeItemTypes": "Episode", "Limit": 1, "Fields": "MediaSources"},
                        timeout=5,
                    )
                    if sample_res.status_code == 200 and sample_res.json().get("Items"):
                        tech_info_str = self._extract_tech_info(sample_res.json().get("Items")[0])
                else:
                    details = media_api.get(
                        f"/Users/{user_id}/Items/{top['Id']}",
                        params={"Fields": "Overview,CommunityRating,Genres,MediaSources"},
                        timeout=8,
                    ).json()
                    tech_info_str = self._extract_tech_info(details)
            except Exception: tech_info_str = "暂无技术信息"

            name = details.get("Name", top.get("Name"))
            year = details.get("ProductionYear", top.get("ProductionYear"))
            year_str = f"({year})" if year else ""
            rating = details.get("CommunityRating", "N/A")
            genres = " / ".join(details.get("Genres", [])[:3]) or "未分类"
            
            overview = str(details.get("Overview") or "")
            overview = re.sub(r'<[^>]+>', '', overview).strip()
            if not overview: overview = "暂无简介"
            if len(overview) > 120: overview = overview[:120] + "..."
            
            type_icon = "🎬" if type_raw == "Movie" else "📺"
            info_line = f"{ep_count_str} | {tech_info_str}" if type_raw == "Series" else tech_info_str
            
            base_url = get_media_server_main_public_or_host() or get_media_server_host()
            if base_url and not base_url.startswith(('http://', 'https://')):
                base_url = 'https://' + base_url
            play_url = f"{base_url}/web/index.html#!/item?id={top.get('Id')}&serverId={top.get('ServerId')}"

            caption = (f"{type_icon} <b>{name}</b> {year_str}\n"
                       f"⭐️ {rating}  |  🎭 {genres}\n"
                       f"💿 {info_line}\n\n"
                       f"📝 <b>剧情简介：</b>\n{overview}\n")
            
            if len(items) > 1:
                caption += "\n🔎 <b>其他结果：</b>\n"
                for i, sub in enumerate(items[1:]):
                    sub_year = f"({sub.get('ProductionYear')})" if sub.get('ProductionYear') else ""
                    sub_type = "📺" if sub.get("Type") == "Series" else "🎬"
                    caption += f"{sub_type} {sub.get('Name')} {sub_year}\n"

            keyboard = None
            if base_url and base_url.startswith(('http://', 'https://')):
                keyboard = {"inline_keyboard": [[{"text": "▶️ 立即播放", "url": play_url}]]}
            primary_io = self._download_emby_image(top.get("Id"), 'Primary')
            backdrop_io = self._download_emby_image(top.get("Id"), 'Backdrop')

            tg_img = primary_io or backdrop_io or REPORT_COVER_URL
            wecom_img = backdrop_io or primary_io or REPORT_COVER_URL
            self.send_photo(chat_id, tg_img, caption.strip(), reply_markup=keyboard, platform=platform, wecom_photo_io=wecom_img)
        except Exception as e:
            self.send_message(chat_id, "❌ 搜索时发生错误", platform=platform)

    def _cmd_stats(self, chat_id, period='day', platform="tg"):
        # 🔥 使用统一的时间计算模块
        from app.shared.time import get_period_range, get_period_days, get_weekday_cn
        
        where, params = get_base_filter('all')
        titles = {'day': '今日日报', 'yesterday': '昨日日报', 'week': '本周周报', 'month': '本月月报', 'year': '年度报告'}
        title_cn = titles.get(period, '数据报表')
        
        # 🔥 使用统一的时间范围计算
        start_date, end_date, period_where, _ = get_period_range(period)
        if period_where:
            where += " " + period_where.replace("WHERE", "AND")
        
        # 计算天数用于日均播放
        days = get_period_days(period)
        
        # 日期显示
        today = datetime.date.today()
        if period == 'yesterday':
            date_str = start_date.strftime("%m-%d")
            weekday = get_weekday_cn(start_date)
        elif period == 'day':
            date_str = today.strftime("%m-%d")
            weekday = get_weekday_cn(today)
        elif period == 'week':
            end_display = today  # 本周至今
            date_str = f"{start_date.strftime('%m-%d')} ~ {end_display.strftime('%m-%d')}"
            weekday = ""
        elif period == 'month':
            date_str = today.strftime("%Y年%m月")
            weekday = ""
        elif period == 'year':
            date_str = today.strftime("%Y年")
            weekday = ""
        else:
            date_str = ""
            weekday = ""

        # 🔥 读取观影报告插件的排除类型配置（默认不排除）
        exclude_types = []
        content_limit = 10  # 默认 Top 10
        try:
            from app.plugins import get_plugin_config
            view_report_config = get_plugin_config("view_report")
            if view_report_config:
                # 排除类型
                config_exclude = view_report_config.get('exclude_types', [])
                if isinstance(config_exclude, str):
                    config_exclude = [t.strip() for t in config_exclude.split(',') if t.strip()]
                if config_exclude:
                    exclude_types = config_exclude
                # 内容排行数量
                try:
                    content_limit = int(view_report_config.get('top_content_limit') or 10)
                except (ValueError, TypeError):
                    content_limit = 10
        except:
            pass
        
        # 构建排除类型 SQL
        exclude_sql = ""
        if exclude_types:
            exclude_placeholders = ', '.join(['?' for _ in exclude_types])
            exclude_sql = f" AND ItemType NOT IN ({exclude_placeholders})"
            # 🔥 修复：params 可能是 list 或 tuple，都要正确处理
            if isinstance(params, (list, tuple)):
                params = tuple(params) + tuple(exclude_types)
            else:
                params = tuple(exclude_types)

        try:
            plays_res = playback_store.query(f"SELECT COUNT(*) as c FROM PlaybackActivity {where}{exclude_sql}", params)
            if not plays_res: raise Exception("DB Error")
            plays = plays_res[0]['c']
            dur_res = playback_store.query(f"SELECT SUM(PlayDuration) as c FROM PlaybackActivity {where}{exclude_sql}", params)
            dur = dur_res[0]['c'] if dur_res and dur_res[0]['c'] else 0
            # 🔥 使用格式化字符串，确保四舍五入一致
            hours_str = f"{dur / 3600:.1f}"
            users_res = playback_store.query(f"SELECT COUNT(DISTINCT UserId) as c FROM PlaybackActivity {where}{exclude_sql}", params)
            users = users_res[0]['c'] if users_res else 0
            
            # 日均播放
            avg_plays_str = f"{plays / days:.1f}" if days > 0 else str(plays)

            # 用户排行
            top_users = playback_store.query(f"SELECT UserId, SUM(PlayDuration) as t FROM PlaybackActivity {where}{exclude_sql} GROUP BY UserId ORDER BY t DESC LIMIT 5", params)
            user_str = ""
            if top_users:
                for i, u in enumerate(top_users):
                    name = self._get_username(u['UserId'])
                    # 🔥 使用格式化字符串，确保四舍五入一致
                    h = u['t'] / 3600
                    h_str = f"{h:.1f}"
                    prefix = ['🥇','🥈','🥉'][i] if i < 3 else f"{i+1}."
                    user_str += f"{prefix} {name} ({h_str}h)\n"
            else: user_str = "暂无数据\n"

            # 🔥 内容排行 - 区分剧集和电影，按时长排序
            all_content = playback_store.query(f"SELECT ItemName, ItemId, ItemType, COUNT(*) as C, COALESCE(SUM(PlayDuration), 0) as Duration FROM PlaybackActivity {where}{exclude_sql} GROUP BY ItemName ORDER BY Duration DESC LIMIT 100", params)
            
            # 分离剧集和电影
            tv_pattern = re.compile(r' - [sS]\d|第.+[集期]|EP?\d', re.IGNORECASE)
            tv_list = []
            movie_list = []
            
            for item in all_content or []:
                name = item['ItemName'] if item['ItemName'] else ''
                series_name = name.split(' - ')[0] if ' - ' in name else name
                duration = item['Duration'] if item['Duration'] else 0
                count = item['C'] if item['C'] else 0
                item_id = item['ItemId'] if item['ItemId'] else None
                
                if tv_pattern.search(name) or item['ItemType'] == 'Episode':
                    existing = [t for t in tv_list if t['SeriesName'] == series_name]
                    if not existing and len(tv_list) < content_limit:
                        tv_list.append({'SeriesName': series_name, 'ItemName': name, 'ItemId': item_id, 'C': count, 'Duration': duration})
                    elif existing:
                        existing[0]['C'] += count
                        existing[0]['Duration'] += duration
                else:
                    if len(movie_list) < content_limit:
                        movie_list.append({'ItemName': name, 'ItemId': item_id, 'C': count, 'Duration': duration})
            
            # 重新按时长排序
            tv_list.sort(key=lambda x: x['Duration'], reverse=True)
            movie_list.sort(key=lambda x: x['Duration'], reverse=True)
            
            # 格式化剧集排行
            tv_str = ""
            for i, item in enumerate(tv_list):
                d = item['Duration']
                h = int(d // 3600)
                m = int((d % 3600) // 60)
                if h > 0:
                    dur_str = f"{h} 小时 {m} 分钟"
                else:
                    dur_str = f"{m} 分钟"
                tv_str += f"{i+1}. {item['SeriesName']}\n播放次数: {item['C']} 时长: {dur_str}\n"
            
            # 格式化电影排行
            movie_str = ""
            for i, item in enumerate(movie_list):
                d = item['Duration']
                h = int(d // 3600)
                m = int((d % 3600) // 60)
                if h > 0:
                    dur_str = f"{h} 小时 {m} 分钟"
                else:
                    dur_str = f"{m} 分钟"
                movie_str += f"{i+1}. {item['ItemName']}\n播放次数: {item['C']} 时长: {dur_str}\n"

            # 构建标题
            title_display = f"{title_cn}"
            if date_str:
                title_display = f"{title_cn}\n📅 {date_str}"
                if weekday:
                    title_display += f" {weekday}"

            # 🔥 图文模式：所有周期都走海报+详细文字
            if HAS_PIL:
                # 日期行
                date_line = f"📅 {date_str}" if date_str else ""
                weekday_line = f" {weekday}" if weekday else ""
                
                caption_parts = [
                    f"📊 <b>EmbyPulse {title_cn}</b>",
                    f"{date_line}{weekday_line}",
                    "",
                    "📈 <b>数据大盘</b>",
                    f"▶️ 总播放量：{plays} 次",
                    f"⏱️ 活跃时长：{hours_str} 小时",
                    f"👥 活跃人数：{users} 人",
                ]
                
                # 周报/月报显示日均
                if period in ['week', 'month']:
                    caption_parts.append(f"📊 日均播放：{avg_plays_str} 次")
                
                caption_parts.extend([
                    "",
                    f"🏆 <b>活跃用户 Top {len(top_users) if top_users else 5}</b>",
                    user_str.strip(),
                ])
                
                if tv_str:
                    caption_parts.extend([
                        "",
                        f"📺 <b>剧集排名</b>",
                        tv_str.strip()
                    ])
                
                if movie_str:
                    caption_parts.extend([
                        "",
                        f"🎬 <b>电影排名</b>",
                        movie_str.strip()
                    ])
                
                caption = "\n".join(caption_parts)
                poster = report_gen.generate_daily_poster(period, tv_list, movie_list)
                if poster:
                    self.send_photo(chat_id, poster, caption.strip(), platform=platform)
                    return

            # fallback：无 Pillow 时纯文字
            caption = (f"📊 <b>EmbyPulse {title_display}</b>\n\n"
                       f"📈 <b>数据大盘</b>\n"
                       f"▶️ 总播放量：{plays} 次\n"
                       f"⏱️ 活跃时长：{hours_str} 小时\n"
                       f"👥 活跃人数：{users} 人\n\n"
                       f"🏆 <b>活跃用户 Top 5</b>\n"
                       f"{user_str}\n"
                       f"🔥 <b>热门内容 Top 10</b>\n"
                       f"{tv_str or movie_str or '暂无数据'}")
            self.send_photo(chat_id, REPORT_COVER_URL, caption.strip(), platform=platform)
        except Exception as e:
            logger.error(f"[Bot] _cmd_stats error: {e}")
            import traceback
            traceback.print_exc()
            self.send_message(chat_id, f"❌ 统计失败: {str(e)}", platform=platform)

    def _cmd_now(self, cid, platform):
        return notification_bot_playback_command_service.cmd_now(self, cid, platform)

    def _cmd_recent(self, cid, platform):
        return notification_bot_playback_command_service.cmd_recent(self, cid, platform)

    def _cmd_check(self, cid, platform):
        return notification_bot_check_command_service.cmd_check(self, cid, platform)

    def _cmd_emby_restart(self, cid, text, platform):
        """Emby 服务器重启命令"""
        try:
            from app.plugins import get_plugin_config, get_plugin
            
            # 检查插件是否启用
            plugin = get_plugin("emby_restart")
            if not plugin or not plugin.enabled:
                self.send_message(cid, "❌ Emby 自动重启插件未启用", platform=platform)
                return
            
            config = get_plugin_config("emby_restart")
            servers = config.get("servers", [])
            
            if not servers:
                self.send_message(cid, "❌ 未配置 Emby 服务器，请先在插件面板中添加服务器", platform=platform)
                return
            
            # 发送服务器列表卡片
            msg = "🖥️ <b>Emby 服务器管理</b>\n\n请选择要重启的服务器：\n"
            
            # 发送每个服务器的按钮
            for i, s in enumerate(servers):
                name = s.get('name', '未命名')
                msg += f"\n<b>{i+1}.</b> {name}"
            
            msg += f"\n\n💡 点击下方按钮重启对应服务器"
            
            # 构建按钮 (Telegram inline keyboard 格式)
            inline_keyboard = []
            row = []
            for i, s in enumerate(servers):
                name = s.get('name', '未命名')[:8]  # 限制按钮文字长度
                row.append({"text": f"🔄 {name}", "callback_data": f"emby_restart:{i}"})
                if len(row) == 2:  # 每行2个按钮
                    inline_keyboard.append(row)
                    row = []
            if row:
                inline_keyboard.append(row)
            
            # 添加重启全部按钮
            inline_keyboard.append([{"text": "🔄 重启全部服务器", "callback_data": "emby_restart:all"}])
            
            reply_markup = {"inline_keyboard": inline_keyboard}
            
            self.send_message(cid, msg, platform=platform, reply_markup=reply_markup)
                
        except Exception as e:
            logger.error(f"[Bot] emby_restart error: {e}")
            self.send_message(cid, f"❌ 执行失败: {str(e)}", platform=platform)

    def _cmd_calendar(self, cid, platform):
        """今日剧集更新"""
        try:
            from app.domains.notifications.calendar_notify import get_today_updates, format_notify_message
            updates = get_today_updates()
            message = format_notify_message(updates)
            self.send_message(cid, message, platform=platform)
        except Exception as e:
            logger.error(f"[Bot] calendar error: {e}")
            self.send_message(cid, "❌ 获取今日更新失败", platform=platform)

    def _format_expire_status(self, expire_date):
        return notification_bot_whois_command_service.format_expire_status(expire_date)

    def _format_whois_row(self, row, index=None):
        return notification_bot_whois_command_service.format_whois_row(row, index)

    def _cmd_whois(self, cid, text, platform):
        return notification_bot_whois_command_service.cmd_whois(self, cid, text, platform)

    def _cmd_help(self, cid, platform):
        msg = ("🤖 <b>EmbyPulse 智能助理指南</b>\n\n"
               "📊 <b>数据报表指令</b>\n"
               "/stats - 获取今日播放大盘与用户排行\n"
               "/weekly - 获取本周全站数据周报\n"
               "/monthly - 获取本月活跃度月报\n"
               "/yearly - 获取年度全景总结数据\n\n"
               "🎬 <b>媒体库与状态指令</b>\n"
               "/now - 查看当前服务器有谁正在播放\n"
               "/latest - 获取最近新入库的 8 部影视剧\n"
               "/recent - 查看本站最近的 10 条播放历史\n"
               "/search [关键词] - 搜索影视资源并获取直达链接\n"
               "/calendar - 查看今日剧集更新\n\n"
               "🛠 <b>系统管理指令</b>\n"
               "/check - 测试 Emby 服务器连通性与测速探针\n"
               "/emby_restart - 重启 Emby 服务器（Pro）\n"
               "/whois [TG用户名/TG ID/Emby用户名] - 查询绑定信息与到期时间\n"
               "/help - 获取本帮助菜单")
        self.send_message(cid, msg.strip(), platform=platform)

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
