import sqlite3
import requests
import logging
import time
import threading
import datetime
from app.core.config import cfg, DB_PATH, SYSTEM_DB_PATH
from app.core.database import add_sys_notification
from app.core.event_bus import bus

logger = logging.getLogger("uvicorn")

# ==========================================
# 🗡️ 屠龙刀：强力执法接口
# ==========================================
def kick_session(session_id: str, reason: str = "管理员强制中止播放"):
    host = cfg.get("emby_host", "").rstrip('/')
    api_key = cfg.get("emby_api_key", "")
    if not host or not api_key: return False
    
    url = f"{host}/emby/Sessions/{session_id}/Playing/Stop"
    try:
        res = requests.post(url, headers={"X-Emby-Token": api_key}, timeout=5)
        return res.status_code in [200, 204]
    except Exception as e:
        logger.error(f"[风控] 踢出设备失败: {e}")
        return False

def ban_user(user_id: str):
    host = cfg.get("emby_host", "").rstrip('/')
    api_key = cfg.get("emby_api_key", "")
    if not host or not api_key: return False
    
    policy_url = f"{host}/emby/Users/{user_id}"
    try:
        res = requests.get(policy_url, headers={"X-Emby-Token": api_key}, timeout=5)
        if res.status_code == 200:
            user_data = res.json()
            policy = user_data.get("Policy", {})
            policy["IsDisabled"] = True
            
            update_url = f"{host}/emby/Users/{user_id}/Policy"
            update_res = requests.post(update_url, headers={"X-Emby-Token": api_key}, json=policy, timeout=5)
            
            if update_res.status_code in [200, 204]:
                # 🔥 设置 admin_disabled = 1，标记为管理员封禁（非过期禁用）
                try:
                    conn = sqlite3.connect(SYSTEM_DB_PATH)
                    c = conn.cursor()
                    c.execute("INSERT OR IGNORE INTO users_meta (user_id, created_at) VALUES (?, ?)", 
                              (user_id, datetime.datetime.now().isoformat()))
                    c.execute("UPDATE users_meta SET admin_disabled = 1 WHERE user_id = ?", (user_id,))
                    conn.commit()
                    conn.close()
                except Exception as e:
                    logger.error(f"[风控] 设置 admin_disabled 失败: {e}")
                return True
    except Exception as e:
        logger.error(f"[风控] 封禁用户失败: {e}")
    return False

def unban_user(user_id: str):
    """解封用户"""
    host = cfg.get("emby_host", "").rstrip('/')
    api_key = cfg.get("emby_api_key", "")
    if not host or not api_key: return False
    
    policy_url = f"{host}/emby/Users/{user_id}"
    try:
        res = requests.get(policy_url, headers={"X-Emby-Token": api_key}, timeout=5)
        if res.status_code == 200:
            user_data = res.json()
            policy = user_data.get("Policy", {})
            policy["IsDisabled"] = False
            
            update_url = f"{host}/emby/Users/{user_id}/Policy"
            update_res = requests.post(update_url, headers={"X-Emby-Token": api_key}, json=policy, timeout=5)
            
            if update_res.status_code in [200, 204]:
                # 🔥 清除 admin_disabled 标记
                try:
                    conn = sqlite3.connect(SYSTEM_DB_PATH)
                    c = conn.cursor()
                    c.execute("UPDATE users_meta SET admin_disabled = 0 WHERE user_id = ?", (user_id,))
                    conn.commit()
                    conn.close()
                except Exception as e:
                    logger.error(f"[风控] 清除 admin_disabled 失败: {e}")
                return True
    except Exception as e:
        logger.error(f"[风控] 解封用户失败: {e}")
    return False

def log_risk_action(user_id: str, username: str, action: str, reason: str):
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        cur = conn.cursor()
        cur.execute("INSERT INTO risk_logs (user_id, username, action, reason) VALUES (?, ?, ?, ?)", (user_id, username, action, reason))
        if action == "ban":
            cur.execute("UPDATE users_meta SET risk_level = 'banned' WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
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
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT max_concurrent, is_vip FROM users_meta WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        conn.close()
        if row:
            is_vip = bool(row[1])
            # VIP用户无限制
            if is_vip:
                return (-1, True)
            if row[0] is not None:
                return (int(row[0]), False)
    except: pass
    return (int(cfg.get("default_max_concurrent", 2)), False)

_alerted_sessions = set()
# 🔥 核心更新：状态记忆体，用于记录上一次扫描的并发情况，防刷屏
_last_playback_state = {}
# 🔥 扫描锁，防止并发扫描
_scan_lock = threading.Lock()
# 🔥 上次扫描时间，用于限流
_last_scan_time = 0

def _send_user_warning(user_id, username, current_count, limit, devices_info):
    """通过TG用户机器人给违规用户发送警告消息"""
    try:
        # 查找用户的TG绑定
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        row = conn.execute("SELECT tg_user_id FROM tg_user_bindings WHERE emby_user_id = ?", (user_id,)).fetchone()
        conn.close()
        
        if not row:
            logger.info(f"[风控警告] 用户 {username} 未绑定TG，无法发送警告消息")
            return
        
        tg_user_id = row[0]
        
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
        from app.services.user_bot_service import _send
        _send(tg_user_id, msg)
        logger.info(f"✅ [风控警告] 已向用户 {username} (TG: {tg_user_id}) 发送警告消息")
    except Exception as e:
        logger.error(f"❌ [风控警告] 发送用户警告失败: {e}")

def _send_user_ban_notify(user_id, username, current_count, limit, devices_info):
    """通过TG用户机器人给被封禁用户发送通知"""
    try:
        # 查找用户的TG绑定
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        row = conn.execute("SELECT tg_user_id FROM tg_user_bindings WHERE emby_user_id = ?", (user_id,)).fetchone()
        conn.close()
        
        if not row:
            logger.info(f"[风控封禁] 用户 {username} 未绑定TG，无法发送封禁通知")
            return
        
        tg_user_id = row[0]
        
        # 构建封禁通知消息
        devices_text = "\n".join([f"  🔸 {d}" for d in devices_info])
        msg = (f"🚫 <b>【账号已被封禁】</b>\n\n"
               f"👤 <b>账号：</b>{username}\n"
               f"📈 <b>违规并发：</b>{current_count} 个设备（上限 {limit}）\n\n"
               f"📱 <b>违规设备：</b>\n{devices_text}\n\n"
               f"❌ <b>您的账号因严重违反并发播放规则，已被系统自动封禁。</b>\n\n"
               f"📌 如需解封，请联系管理员。")
        
        # 通过用户机器人发送消息
        from app.services.user_bot_service import _send
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
        
        if not cfg.get("enable_risk_control", True): return

        host = cfg.get("emby_host", "").rstrip('/')
        api_key = cfg.get("emby_api_key", "")
        if not host or not api_key: return

        try:
            res = requests.get(f"{host}/emby/Sessions", headers={"X-Emby-Token": api_key}, timeout=10)
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
                    violation_action = cfg.get("violation_action", "warn_only")
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
        time.sleep(3)
        scan_playbacks_and_alert()
    threading.Thread(target=delay_scan, daemon=True).start()

def _risk_monitor_loop():
    while True:
        try: scan_playbacks_and_alert()
        except: pass
        time.sleep(60) 

def _on_risk_alert_for_web(data):
    # 检查是否开启全局通知中心
    if not cfg.get("enable_risk_sys_notification", True):
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
    
    add_sys_notification(
        notify_type="risk",
        title=f"🚨 并发越界: {username}",
        message=f"当前并发 {current} / 额度 {limit}，处理: {action_text}",
        action_url="/risk"
    )

def start_risk_monitor():
    bus.subscribe("notify.playback.start", _on_playback_start)
    bus.subscribe("notify.risk.alert", _on_risk_alert_for_web)
    
    threading.Thread(target=_risk_monitor_loop, daemon=True, name="RiskMonitorThread").start()
    logger.info("👁️ [风险管控] 零延迟天眼系统已启动 (事件驱动 + 60s兜底)")