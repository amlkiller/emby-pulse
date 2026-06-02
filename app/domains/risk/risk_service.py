import logging
import time
import threading
import datetime
from app.core.event_bus import bus
from app.infra.clients.media_server_client import media_api
from app.infra.config.risk_settings import (
    get_default_max_concurrent,
    get_violation_action,
    is_risk_control_enabled,
    is_risk_sys_notification_enabled,
)
from app.infra.db.notification_dao import add_system_notification
from app.domains.risk.risk_dao import (
    create_risk_log,
    get_tg_user_id_for_emby_user,
    get_user_concurrent_policy,
    set_user_admin_disabled,
)

logger = logging.getLogger("uvicorn")

# ==========================================
# 🗡️ 屠龙刀：强力执法接口
# ==========================================
def kick_session(session_id: str, reason: str = "管理员强制中止播放"):
    try:
        res = media_api.post(f"/Sessions/{session_id}/Playing/Stop", timeout=5)
        return res.status_code in [200, 204]
    except Exception as e:
        logger.error(f"[风控] 踢出设备失败: {e}")
        return False

def ban_user(user_id: str):
    try:
        res = media_api.get(f"/Users/{user_id}", timeout=5)
        if res.status_code == 200:
            user_data = res.json()
            policy = user_data.get("Policy", {})
            policy["IsDisabled"] = True
            
            update_res = media_api.post(f"/Users/{user_id}/Policy", json=policy, timeout=5)
            
            if update_res.status_code in [200, 204]:
                # 🔥 设置 admin_disabled = 1，标记为管理员封禁（非过期禁用）
                try:
                    set_user_admin_disabled(user_id, True, datetime.datetime.now().isoformat())
                except Exception as e:
                    logger.error(f"[风控] 设置 admin_disabled 失败: {e}")
                return True
    except Exception as e:
        logger.error(f"[风控] 封禁用户失败: {e}")
    return False

def unban_user(user_id: str):
    """解封用户"""
    try:
        res = media_api.get(f"/Users/{user_id}", timeout=5)
        if res.status_code == 200:
            user_data = res.json()
            policy = user_data.get("Policy", {})
            policy["IsDisabled"] = False
            
            update_res = media_api.post(f"/Users/{user_id}/Policy", json=policy, timeout=5)
            
            if update_res.status_code in [200, 204]:
                # 🔥 清除 admin_disabled 标记
                try:
                    set_user_admin_disabled(user_id, False)
                except Exception as e:
                    logger.error(f"[风控] 清除 admin_disabled 失败: {e}")
                return True
    except Exception as e:
        logger.error(f"[风控] 解封用户失败: {e}")
    return False

def log_risk_action(user_id: str, username: str, action: str, reason: str):
    try:
        create_risk_log(user_id, username, action, reason)
    except Exception as e:
        logger.error(f"[风控] 记录日志失败: {e}")

# ==========================================
# 👁️ 天眼：零延迟实时扫描
# ==========================================
def get_user_concurrent_limit(user_id: str) -> tuple:
    """
    获取用户并发限制和VIP状态
    返回: (limit, is_vip)
    VIP用户返回 (-1, True) 表示无限制
    """
    try:
        row = get_user_concurrent_policy(user_id)
        if row:
            is_vip = bool(row["is_vip"])
            # VIP用户无限制
            if is_vip:
                return (-1, True)
            if row["max_concurrent"] is not None:
                return (int(row["max_concurrent"]), False)
    except Exception: pass
    return (get_default_max_concurrent(), False)

_alerted_sessions = set()
# 🔥 核心更新：状态记忆体，用于记录上一次扫描的并发情况，防刷屏
_last_playback_state = {}
# 🔥 扫描锁，防止并发扫描
_scan_lock = threading.Lock()
# 🔥 上次扫描时间，用于限流
_last_scan_time = 0
_risk_monitor_started = False
_risk_monitor_start_lock = threading.Lock()
_risk_monitor_stop_event = threading.Event()
_risk_monitor_thread = None
_risk_monitor_subscribed = False

def _send_user_warning(user_id, username, current_count, limit, devices_info):
    """通过TG用户机器人给违规用户发送警告消息"""
    try:
        # 查找用户的TG绑定
        tg_user_id = get_tg_user_id_for_emby_user(user_id)
        if not tg_user_id:
            logger.info(f"[风控警告] 用户 {username} 未绑定TG，无法发送警告消息")
            return
        
        # 构建警告消息
        devices_text = "\n".join([f"  🔸 {d}" for d in devices_info])
        msg = (f"⚠️ <b>【并发超限警告】</b>\n\n"
               f"👤 <b>账号：</b>{username}\n"
               f"📈 <b>当前并发：</b>{current_count} 个设备\n"
               f"📋 <b>允许上限：</b>{limit} 个设备\n\n"
               f"📱 <b>当前播放设备：</b>\n{devices_text}\n\n"
               f"⚠️ <b>您已违反并发播放规则！</b>\n"
               f"请立即停止多余的播放，否则账号可能会被限制或封禁。\n\n"
               f"如有疑问，请联系管理员。")
        
        # 通过用户机器人发送消息
        from app.domains.notifications.user_bot_service import _send
        _send(tg_user_id, msg)
        logger.info(f"✅ [风控警告] 已向用户 {username} (TG: {tg_user_id}) 发送警告消息")
    except Exception as e:
        logger.error(f"❌ [风控警告] 发送用户警告失败: {e}")

def _send_user_ban_notify(user_id, username, current_count, limit, devices_info):
    """通过TG用户机器人给被封禁用户发送通知"""
    try:
        # 查找用户的TG绑定
        tg_user_id = get_tg_user_id_for_emby_user(user_id)
        if not tg_user_id:
            logger.info(f"[风控封禁] 用户 {username} 未绑定TG，无法发送封禁通知")
            return
        
        # 构建封禁通知消息
        devices_text = "\n".join([f"  🔸 {d}" for d in devices_info])
        msg = (f"🚫 <b>【账号已被封禁】</b>\n\n"
               f"👤 <b>账号：</b>{username}\n"
               f"📈 <b>违规并发：</b>{current_count} 个设备（上限 {limit}）\n\n"
               f"📱 <b>违规设备：</b>\n{devices_text}\n\n"
               f"❌ <b>您的账号因严重违反并发播放规则，已被系统自动封禁。</b>\n\n"
               f"📌 如需解封，请联系管理员。")
        
        # 通过用户机器人发送消息
        from app.domains.notifications.user_bot_service import _send
        _send(tg_user_id, msg)
        logger.info(f"✅ [风控封禁] 已向用户 {username} (TG: {tg_user_id}) 发送封禁通知")
    except Exception as e:
        logger.error(f"❌ [风控封禁] 发送封禁通知失败: {e}")

def scan_playbacks_and_alert():
    global _last_scan_time
    
    # 🔥 限流：距离上次扫描不足5秒则跳过
    now = time.time()
    if now - _last_scan_time < 5:
        return
    
    # 🔥 加锁防止并发扫描
    if not _scan_lock.acquire(blocking=False):
        logger.debug("[风控天眼] 扫描进行中，跳过本次")
        return
    
    try:
        _last_scan_time = now
        
        if not is_risk_control_enabled(): return

        try:
            res = media_api.get("/Sessions", timeout=10)
            if res.status_code != 200: return
            sessions = res.json()
        except Exception as e:
            logger.error(f"[风控天眼] 获取会话失败: {e}")
            return
        
        active_playbacks = {}
        for s in sessions:
            if s.get("NowPlayingItem") and s["NowPlayingItem"].get("MediaType") == "Video":
                uid = s.get("UserId")
                if not uid: continue
                if uid not in active_playbacks:
                    active_playbacks[uid] = []
                active_playbacks[uid].append(s)
                
        global _alerted_sessions
        global _last_playback_state
        
        current_alert_fingerprints = set()
        
        # 提取当前所有用户的并发数简影：{ uid: count }
        current_playback_state = {uid: len(sessions) for uid, sessions in active_playbacks.items()}
        
        # 只有在有人看，且状态与上一次不同时（有人进、出或多开），才打印雷达大盘日志
        state_changed = current_playback_state != _last_playback_state
        
        if len(active_playbacks) > 0 and state_changed:
            logger.info(f"📡 [天眼雷达] 播放并发状态发生更新... 当前有 {len(active_playbacks)} 名用户在看视频。")

        for uid, user_sessions in active_playbacks.items():
            limit, is_vip = get_user_concurrent_limit(uid)
            current_count = len(user_sessions)
            username = user_sessions[0].get("UserName", "未知用户")
            
            # VIP用户跳过风控检测
            if is_vip:
                if current_count != _last_playback_state.get(uid, 0):
                    logger.info(f"   ⭐ VIP用户: {username} | 当前并发: {current_count} | 已豁免风控")
                continue
            
            # 🔥 重点拦截：只有当具体的这个用户并发数变化了，才打印它的日志
            if current_count != _last_playback_state.get(uid, 0):
                logger.info(f"   ▶️ 锁定用户: {username} | 当前并发: {current_count} | 专属限额: {limit}")
            
            if current_count > limit:
                devices_info = []
                alert_trigger_ids = []
                for s in user_sessions:
                    dev_name = s.get("DeviceName", "未知设备")
                    client = s.get("Client", "未知客户端")
                    sid = s.get("Id", "")
                    devices_info.append(f"{dev_name} ({client})")
                    alert_trigger_ids.append(sid)
                
                fingerprint = f"{uid}-" + "-".join(sorted(alert_trigger_ids))
                current_alert_fingerprints.add(fingerprint)
                
                if fingerprint not in _alerted_sessions:
                    log_risk_action(uid, username, "warn", f"并发超限: 当前 {current_count} / 限额 {limit}")
                    devices_text = "\n".join([f"  🔸 {d}" for d in devices_info])
                    
                    # 获取违规处理方式
                    violation_action = get_violation_action()
                    logger.warning(f"🚨 [风控执行] 发现越界！用户: {username}, 处理方式: {violation_action}")
                    
                    # 根据处理方式执行不同操作
                    if violation_action == "auto_ban":
                        # 自动封禁
                        logger.warning(f"🚫 [风控自动封禁] 正在封禁用户 {username}...")
                        if ban_user(uid):
                            log_risk_action(uid, username, "ban", f"并发超限自动封禁: {current_count}/{limit}")
                            logger.info(f"✅ [风控自动封禁] 用户 {username} 已被自动封禁")
                            # 封禁后发送通知给用户
                            _send_user_ban_notify(uid, username, current_count, limit, devices_info)
                        else:
                            logger.error(f"❌ [风控自动封禁] 封禁用户 {username} 失败")
                    
                    # 发布通知事件（无论哪种模式都通知管理员）
                    bus.publish("notify.risk.alert", {
                        "user_id": uid,          
                        "username": username,
                        "current": current_count,
                        "limit": limit,
                        "devices_info": devices_text,
                        "violation_action": violation_action
                    })
                    
                    # 如果是 warn_user 模式，额外给用户发送警告消息
                    if violation_action == "warn_user":
                        _send_user_warning(uid, username, current_count, limit, devices_info)
                else:
                    if state_changed:
                        logger.info(f"⚠️ [风控防抖] {username} 的这批设备已在处置中，忽略重复报警...")
                    
        # 更新记忆体状态
        _alerted_sessions.clear()
        _alerted_sessions.update(current_alert_fingerprints)
        _last_playback_state = current_playback_state
                    
    except Exception as e:
        logger.error(f"[风控天眼] 扫描异常: {e}")
    finally:
        _scan_lock.release()

def _on_playback_start(data):
    # 稍微延迟等 Emby session 注册完成再扫描
    def delay_scan():
        if _risk_monitor_stop_event.wait(3):
            return
        scan_playbacks_and_alert()
    threading.Thread(target=delay_scan, daemon=True).start()

def _risk_monitor_loop():
    while not _risk_monitor_stop_event.is_set():
        try: scan_playbacks_and_alert()
        except Exception: pass
        _risk_monitor_stop_event.wait(60)

def _on_risk_alert_for_web(data):
    # 检查是否开启全局通知中心
    if not is_risk_sys_notification_enabled():
        return
    
    username = data.get("username", "未知")
    current = data.get("current", 0)
    limit = data.get("limit", 0)
    violation_action = data.get("violation_action", "warn_only")
    
    action_text = {
        "warn_only": "仅提醒",
        "warn_user": "已警告用户",
        "auto_ban": "已自动封禁"
    }.get(violation_action, "仅提醒")
    
    add_system_notification(
        notify_type="risk",
        title=f"🚨 并发越界: {username}",
        message=f"当前并发 {current} / 额度 {limit}，处理: {action_text}",
        action_url="/risk"
    )

def start_risk_monitor():
    global _risk_monitor_started, _risk_monitor_thread, _risk_monitor_subscribed
    with _risk_monitor_start_lock:
        if _risk_monitor_started:
            return
        _risk_monitor_stop_event.clear()
        _risk_monitor_started = True

        if not _risk_monitor_subscribed:
            bus.subscribe("notify.playback.start", _on_playback_start)
            bus.subscribe("notify.risk.alert", _on_risk_alert_for_web)
            _risk_monitor_subscribed = True
        _risk_monitor_thread = threading.Thread(target=_risk_monitor_loop, daemon=True, name="RiskMonitorThread")
        _risk_monitor_thread.start()

    logger.info("👁️ [风险管控] 零延迟天眼系统已启动 (事件驱动 + 60s兜底)")


def stop_risk_monitor():
    global _risk_monitor_started, _risk_monitor_thread, _risk_monitor_subscribed
    with _risk_monitor_start_lock:
        if not _risk_monitor_started:
            return
        _risk_monitor_stop_event.set()
        if _risk_monitor_subscribed:
            bus.unsubscribe("notify.playback.start", _on_playback_start)
            bus.unsubscribe("notify.risk.alert", _on_risk_alert_for_web)
            _risk_monitor_subscribed = False
        thread = _risk_monitor_thread
        _risk_monitor_started = False
        _risk_monitor_thread = None
    if thread and thread.is_alive():
        thread.join(timeout=1)
