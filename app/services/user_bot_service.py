"""
EmbyPulse 用户 TG 机器人 (Pro 专属)
独立于管理员机器人，面向普通用户提供自助服务
"""
import threading
import time
import requests
import datetime
import secrets
import sqlite3
import json
import logging
import re
import random
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from app.core.config import cfg
from app.core.database import DB_PATH, SYSTEM_DB_PATH, query_db
from app.utils.proxy_helper import get_safe_proxies  # 🔒 SSRF 安全代理读取
from app.core.media_adapter import media_api
from app.core.security import validate_password_strength  # 🔒 统一密码强度校验

logger = logging.getLogger("uvicorn")

# 🔒 XSS 防护：HTML 转义函数（用于 Telegram 消息）
def escape_html(text):
    """转义 HTML 特殊字符，防止 XSS 攻击"""
    if not text:
        return ''
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

# 🚀 线程池：限制最大并发数，防止线程爆炸
MAX_CONCURRENT_TASKS = 50  # 最大并发任务数
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

def _get_restriction_cache_ttl():
    """从配置获取缓存时间，默认 120 秒"""
    try:
        ttl = int(cfg.get("user_bot_restriction_cache_ttl") or 120)
        return max(0, min(ttl, 3600))  # 限制在 0-3600 秒
    except:
        return 120

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


def _submit_task(func, *args, **kwargs):
    """提交任务到线程池，支持排队"""
    global _active_tasks, _waiting_count
    
    # 检查等待队列是否已满
    with _waiting_count_lock:
        if _waiting_count >= MAX_WAITING_TASKS:
            return False  # 等待队列也满了，拒绝
        _waiting_count += 1
    
    def wrapper():
        global _active_tasks, _waiting_count
        # 从等待队列移到活跃
        with _waiting_count_lock:
            _waiting_count -= 1
        with _active_tasks_lock:
            _active_tasks += 1
        
        try:
            func(*args, **kwargs)
        finally:
            with _active_tasks_lock:
                _active_tasks -= 1
    
    _task_executor.submit(wrapper)
    return True


def _get_queue_status():
    """获取当前队列状态"""
    with _active_tasks_lock:
        with _waiting_count_lock:
            return {
                "active": _active_tasks, 
                "waiting": _waiting_count,
                "max_active": MAX_CONCURRENT_TASKS,
                "max_waiting": MAX_WAITING_TASKS
            }


def _enter_reg_queue(chat_id):
    """进入注册队列。超出并发上限时阻塞排队并发送位置提示，超时返回 False。"""
    global _reg_waiters, _reg_active
    with _reg_waiters_lock:
        _reg_waiters += 1
        pos = _reg_waiters
        active = _reg_active
    if active >= MAX_CONCURRENT_REG:
        # 已经满了，告诉用户大致位置（含自己）
        _send(chat_id, f"⏳ 当前注册人数较多，你排在第 {pos} 位，请稍候（最长等待 {REG_QUEUE_MAX_WAIT // 60} 分钟）...")
    got = _reg_sema.acquire(timeout=REG_QUEUE_MAX_WAIT)
    with _reg_waiters_lock:
        _reg_waiters -= 1
        if got:
            _reg_active += 1
    if not got:
        _send(chat_id, "⌛ 注册排队等待超时，请稍后重试")
        return False
    return True


def _leave_reg_queue():
    """离开注册队列，释放信号量。"""
    global _reg_active
    with _reg_waiters_lock:
        _reg_active = max(0, _reg_active - 1)
    try:
        _reg_sema.release()
    except ValueError:
        # BoundedSemaphore 释放次数超出上限，理论上不应发生
        logger.exception("[UserBot] _reg_sema release 异常")


def _send_open_reg_closed_notify(reason=""):
    """发送开放注册关闭通知"""
    notify_user = cfg.get("user_bot_open_reg_notify_user", False)
    notify_group = cfg.get("user_bot_open_reg_notify_group", False)
    
    if not notify_user and not notify_group:
        return
    
    msg = """📢 <b>开放注册已结束</b>

🙏 感谢大家的支持！
📊 本次开放注册已圆满结束
💌 如有疑问请联系管理员

⏰ 结束时间：{}
📝 原因：{}""".format(
        datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        reason or "手动关闭"
    )
    
    # 发送到用户机器人私聊
    if notify_user:
        try:
            bindings = _get_all_bindings()
            for b in bindings:
                tg_id = b.get('tg_user_id') if isinstance(b, dict) else b[0]
                try:
                    _send(int(tg_id), msg)
                except Exception as e:
                    logger.error(f"[开放注册通知] 发送给用户 {tg_id} 失败: {e}")
        except Exception as e:
            logger.error(f"[开放注册通知] 用户私聊通知失败: {e}")
    
    # 发送到群聊
    if notify_group:
        try:
            from app.services.bot_service import bot
            allowed_groups = cfg.get("user_bot_allowed_groups", "")
            if allowed_groups:
                group_ids = [g.strip() for g in allowed_groups.replace('，', ',').split('\n') if g.strip()]
                for gid in group_ids:
                    try:
                        bot.send_message(gid, msg, platform="tg", parse_mode="HTML")
                    except Exception as e:
                        logger.error(f"[开放注册通知] 发送到群 {gid} 失败: {e}")
        except Exception as e:
            logger.error(f"[开放注册通知] 群聊通知失败: {e}")


def _ensure_user_bot_tables():
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        conn.execute("""CREATE TABLE IF NOT EXISTS tg_user_bindings (
            tg_user_id TEXT PRIMARY KEY,
            emby_user_id TEXT,
            emby_username TEXT,
            tg_username TEXT,
            tg_display_name TEXT,
            init_password TEXT DEFAULT '',
            bound_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        try: conn.execute("ALTER TABLE tg_user_bindings ADD COLUMN init_password TEXT DEFAULT ''")
        except Exception: pass
        try: conn.execute("ALTER TABLE tg_user_bindings ADD COLUMN tg_username TEXT")
        except Exception: pass
        try: conn.execute("ALTER TABLE tg_user_bindings ADD COLUMN tg_display_name TEXT")
        except Exception: pass
        conn.execute("""CREATE TABLE IF NOT EXISTS tg_user_blacklist (
            tg_user_id TEXT PRIMARY KEY,
            reason TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        # 🤖 开放注册日志表
        conn.execute("""CREATE TABLE IF NOT EXISTS tg_reg_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_user_id TEXT,
            emby_username TEXT,
            emby_user_id TEXT,
            reg_type TEXT DEFAULT 'open',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        # 🤖 用户机器人用户表（记录所有 /start 过的用户）
        conn.execute("""CREATE TABLE IF NOT EXISTS tg_bot_users (
            tg_user_id TEXT PRIMARY KEY,
            tg_name TEXT DEFAULT '',
            first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        # 🔥 频道绑定表（将频道ID绑定到用户）
        conn.execute("""CREATE TABLE IF NOT EXISTS tg_channel_bindings (
            channel_id TEXT PRIMARY KEY,
            tg_user_id TEXT,
            channel_title TEXT DEFAULT '',
            bound_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"用户机器人表初始化失败: {e}")

_ensure_user_bot_tables()


def _get_proxies():
    return get_safe_proxies()


def _tg_api(method, data=None, token=None):
    tk = token or cfg.get("tg_user_bot_token")
    if not tk:
        return None
    try:
        # 缩短超时时间，快速失败
        r = requests.post(f"https://api.telegram.org/bot{tk}/{method}", json=data, proxies=_get_proxies(), timeout=8)
        return r.json() if r.status_code == 200 else None
    except:
        return None


def _check_user_in_chat(user_id: str, chat_id: str) -> bool:
    """
    检查用户是否在指定频道/群聊中
    
    Args:
        user_id: Telegram 用户 ID
        chat_id: 频道/群聊 ID（支持 @用户名 或数字 ID）
    
    Returns:
        bool: True 表示用户在该频道/群聊中
    """
    try:
        result = _tg_api("getChatMember", {"chat_id": chat_id, "user_id": user_id})
        if not result or not result.get("ok"):
            return False
        
        member = result.get("result", {})
        status = member.get("status", "")
        
        # 有效状态：member, administrator, creator, restricted
        # 无效状态：left, kicked
        return status in ["member", "administrator", "creator", "restricted"]
    except Exception as e:
        logger.error(f"检查用户 {user_id} 是否在 {chat_id} 中失败: {e}")
        return False


def _check_user_restrictions(tg_user_id: str) -> dict:
    """
    检查用户是否满足使用限制条件（智能缓存）
    
    缓存策略：
    - 通过检查：缓存60秒，但每次使用时仍需验证（防止取关后继续使用）
    - 未通过检查：不缓存（让用户加入后能立即使用）
    
    Args:
        tg_user_id: Telegram 用户 ID
    
    Returns:
        dict: {
            "passed": bool,  # 是否通过检查
            "missing_channels": list,  # 未关注的频道
            "missing_groups": list     # 未加入的群聊
        }
    """
    result = {"passed": True, "missing_channels": [], "missing_groups": []}
    
    # 检查是否启用限制
    enabled = cfg.get("user_bot_restriction_enabled", False)
    if not enabled:
        return result
    
    # 🔥 检查缓存（缓存有效期内完全信任，不做任何 API 调用）
    cache_ttl = _get_restriction_cache_ttl()
    with _restriction_cache_lock:
        cached = _restriction_cache.get(tg_user_id)
        if cached and cached["passed"] and (time.time() - cached["cached_at"] < cache_ttl):
            # 缓存有效，直接返回
            return {"passed": True, "missing_channels": [], "missing_groups": []}
    
    # 获取必须关注的频道
    required_channels = cfg.get("user_bot_required_channels", "")
    if required_channels:
        channels = [c.strip() for c in required_channels.split("\n") if c.strip()]
        for channel in channels:
            in_chat = _check_user_in_chat(tg_user_id, channel)
            if not in_chat:
                result["missing_channels"].append(channel)
    
    # 获取必须加入的群聊
    required_groups = cfg.get("user_bot_required_groups", "")
    logger.info(f"[使用限制] required_groups={repr(required_groups)}")
    if required_groups:
        try:
            # 🔥 尝试解析 JSON 格式
            groups_data = json.loads(required_groups) if required_groups.strip().startswith('[') else None
            if groups_data:
                # JSON 格式：[{"id": "-100123", "name": "群名称", "link": "https://t.me/xxx"}]
                for group in groups_data:
                    group_id = group.get("id", "")
                    if group_id:
                        in_chat = _check_user_in_chat(tg_user_id, group_id)
                        logger.info(f"[使用限制] 检查群聊 {group_id}, user={tg_user_id}, in_chat={in_chat}")
                        if not in_chat:
                            result["missing_groups"].append({
                                "id": group_id,
                                "name": group.get("name", group_id),
                                "link": group.get("link", "")
                            })
            else:
                # 兼容旧格式：一行一个群 ID
                groups = [g.strip() for g in required_groups.split("\n") if g.strip()]
                logger.info(f"[使用限制] 解析后的群聊列表: {groups}")
                for group in groups:
                    in_chat = _check_user_in_chat(tg_user_id, group)
                    logger.info(f"[使用限制] 检查群聊 {group}, user={tg_user_id}, in_chat={in_chat}")
                    if not in_chat:
                        result["missing_groups"].append({"id": group, "name": group, "link": ""})
        except json.JSONDecodeError:
            # JSON 解析失败，使用旧格式
            groups = [g.strip() for g in required_groups.split("\n") if g.strip()]
            for group in groups:
                in_chat = _check_user_in_chat(tg_user_id, group)
                if not in_chat:
                    result["missing_groups"].append({"id": group, "name": group, "link": ""})
    
    # 判断是否通过
    result["passed"] = len(result["missing_channels"]) == 0 and len(result["missing_groups"]) == 0
    
    # 🔥 只有通过检查才缓存
    if result["passed"]:
        with _restriction_cache_lock:
            _restriction_cache[tg_user_id] = {
                "passed": True,
                "missing_channels": [],
                "missing_groups": [],
                "cached_at": time.time()
            }
    
    return result


def _clear_restriction_cache(tg_user_id: str):
    """清除用户的限制检查缓存"""
    with _restriction_cache_lock:
        _restriction_cache.pop(tg_user_id, None)


def _format_restriction_message(check_result: dict) -> str:
    """
    格式化限制检查失败的消息
    """
    msg = "⚠️ <b>使用限制</b>\n\n"
    msg += "使用本机器人需要满足以下条件：\n\n"
    
    if check_result["missing_channels"]:
        msg += "📢 <b>必须关注的频道：</b>\n"
        for ch in check_result["missing_channels"]:
            # 如果是 @ 开头的用户名，显示为可点击链接
            if ch.startswith("@"):
                msg += f"• <a href=\"https://t.me/{ch[1:]}\">{ch}</a>\n"
            else:
                msg += f"• {ch}\n"
        msg += "\n"
    
    if check_result["missing_groups"]:
        msg += "👥 <b>必须加入的群聊：</b>\n"
        for grp in check_result["missing_groups"]:
            # 支持新旧格式
            if isinstance(grp, dict):
                name = grp.get("name", grp.get("id", "未知群"))
                link = grp.get("link", "")
                if link:
                    msg += f"• <a href=\"{link}\">{name}</a>\n"
                else:
                    msg += f"• {name}\n"
            else:
                msg += f"• {grp}\n"
        msg += "\n"
    
    msg += "💡 关注/加入后，发送 <b>/check</b> 重新验证。"
    
    return msg


def _send(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = reply_markup
    return _tg_api("sendMessage", data)


def _edit(chat_id, message_id, text, reply_markup=None):
    """编辑已有消息，实现同一对话内交互"""
    data = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = reply_markup
    result = _tg_api("editMessageText", data)
    if not result or not result.get("ok"):
        return _send(chat_id, text, reply_markup)
    return result


def _reply(chat_id, text, reply_markup=None, msg_id=None):
    """统一回复：有 msg_id 时编辑原消息，否则发新消息"""
    if msg_id:
        return _edit(chat_id, msg_id, text, reply_markup)
    return _send(chat_id, text, reply_markup)


# 用户会话状态（用于多步交互，如注册输入用户名）
_user_state = {}  # tg_user_id -> {"action": "register_name", ...}


def _send_open_reg_closed_notify(reason=""):
    """发送开放注册关闭通知（名额已满等场景）"""
    notify_user = cfg.get("user_bot_open_reg_notify_user", False)
    notify_group = cfg.get("user_bot_open_reg_notify_group", False)
    
    if not notify_user and not notify_group:
        return
    
    reason_text = f"（{reason}）" if reason else ""
    msg = f"""📢 <b>开放注册已结束</b>

🙏 感谢大家的支持！
📊 本次开放注册已圆满结束{reason_text}
💌 如有疑问请联系管理员

⏰ 结束时间：{datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}"""
    
    # 发送到所有启动过机器人的用户私聊
    if notify_user:
        try:
            users = _get_all_bot_users()
            for u in users:
                try:
                    _send(int(u['tg_user_id']), msg)
                except Exception as e:
                    logger.error(f"[开放注册通知] 发送给用户 {u['tg_user_id']} 失败: {e}")
        except Exception as e:
            logger.error(f"[开放注册通知] 用户私聊通知失败: {e}")
    
    # 发送到群聊（使用用户机器人）
    if notify_group:
        try:
            allowed_groups = cfg.get("user_bot_allowed_groups", "")
            if allowed_groups:
                group_ids = [g.strip() for g in allowed_groups.replace('，', ',').split('\n') if g.strip()]
                for gid in group_ids:
                    try:
                        _send(int(gid), msg)  # 使用用户机器人发送
                        logger.info(f"[开放注册通知] 已发送到群 {gid}")
                    except Exception as e:
                        logger.error(f"[开放注册通知] 发送到群 {gid} 失败: {e}")
            else:
                logger.warning("[开放注册通知] 未配置群 ID，跳过群聊通知")
        except Exception as e:
            logger.error(f"[开放注册通知] 群聊通知失败: {e}")


def _unbind_user(tg_user_id):
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        conn.execute("DELETE FROM tg_user_bindings WHERE tg_user_id = ?", (str(tg_user_id),))
        conn.commit()
        conn.close()
        # 清除缓存（加锁）
        with _cache_lock:
            _binding_cache.pop(str(tg_user_id), None)
    except:
        pass


def _get_binding_by_emby_id(emby_user_id):
    """通过 emby_user_id 获取绑定关系"""
    try:
        emby_id_str = str(emby_user_id).strip()
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        # 尝试精确匹配
        row = conn.execute("SELECT tg_user_id, emby_username, init_password, tg_username, tg_display_name FROM tg_user_bindings WHERE emby_user_id = ?", (emby_id_str,)).fetchone()
        if not row:
            # 尝试模糊匹配（处理可能的格式差异）
            row = conn.execute("SELECT tg_user_id, emby_username, init_password, tg_username, tg_display_name FROM tg_user_bindings WHERE CAST(emby_user_id AS TEXT) = ?", (emby_id_str,)).fetchone()
        conn.close()
        if row:
            return {"tg_user_id": row[0], "emby_username": row[1], "init_password": row[2] or "", "tg_username": row[3] or "", "tg_name": row[4] or ""}
        logger.warning(f"[绑定] 未找到 emby_user_id={emby_id_str} 的 TG 绑定")
        return None
    except Exception as e:
        logger.error(f"[绑定] 查询 emby_user_id={emby_user_id} 失败: {e}")
        return None


def _get_binding(tg_user_id):
    """获取绑定关系（带缓存，线程安全）"""
    cache_key = str(tg_user_id)
    
    # 检查缓存（加锁读取）
    with _cache_lock:
        cached = _binding_cache.get(cache_key)
        if cached and (time.time() - cached["cached_at"] < _BINDING_CACHE_TTL):
            return cached["binding"]
    
    # 缓存未命中，查询数据库
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        row = conn.execute("SELECT emby_user_id, emby_username, init_password, tg_username, tg_display_name FROM tg_user_bindings WHERE tg_user_id = ?", (cache_key,)).fetchone()
        conn.close()
        result = {"emby_user_id": row[0], "emby_username": row[1], "init_password": row[2] or "", "tg_username": row[3] or "", "tg_name": row[4] or ""} if row else None
        
        # 更新缓存（加锁写入）
        with _cache_lock:
            _binding_cache[cache_key] = {"binding": result, "cached_at": time.time()}
        return result
    except:
        return None


def _get_channel_binding(channel_id):
    """获取频道绑定关系（频道ID -> 用户ID -> Emby账号）"""
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        row = conn.execute("SELECT tg_user_id, channel_title FROM tg_channel_bindings WHERE channel_id = ?", (str(channel_id),)).fetchone()
        conn.close()
        if row:
            tg_user_id = row[0]
            channel_title = row[1]
            # 获取该用户的绑定
            user_binding = _get_binding(tg_user_id)
            if user_binding:
                return {**user_binding, "channel_title": channel_title, "bound_tg_user_id": tg_user_id}
        return None
    except:
        return None


def _bind_channel(channel_id, tg_user_id, channel_title=""):
    """绑定频道到用户"""
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        conn.execute("""INSERT OR REPLACE INTO tg_channel_bindings (channel_id, tg_user_id, channel_title, bound_at)
                        VALUES (?, ?, ?, datetime('now','localtime'))""", (str(channel_id), str(tg_user_id), channel_title))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"绑定频道失败: {e}")
        return False


def _unbind_channel(channel_id):
    """解绑频道"""
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        conn.execute("DELETE FROM tg_channel_bindings WHERE channel_id = ?", (str(channel_id),))
        conn.commit()
        conn.close()
        return True
    except:
        return False


def _get_all_bindings():
    """获取所有绑定关系"""
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        rows = conn.execute("SELECT tg_user_id, emby_user_id, emby_username FROM tg_user_bindings").fetchall()
        conn.close()
        return [{"tg_user_id": r[0], "emby_user_id": r[1], "emby_username": r[2]} for r in rows]
    except:
        return []


def _record_bot_user(tg_user_id, tg_name=""):
    """记录/更新机器人用户（所有 /start 过的用户）"""
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        conn.execute("""INSERT INTO tg_bot_users (tg_user_id, tg_name, first_seen, last_seen) 
                        VALUES (?, ?, datetime('now','localtime'), datetime('now','localtime'))
                        ON CONFLICT(tg_user_id) DO UPDATE SET 
                        tg_name = excluded.tg_name,
                        last_seen = datetime('now','localtime')""",
                     (str(tg_user_id), tg_name))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"记录机器人用户失败: {e}")


def _get_all_bot_users():
    """获取所有启动过机器人的用户"""
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        rows = conn.execute("SELECT tg_user_id, tg_name FROM tg_bot_users").fetchall()
        conn.close()
        return [{"tg_user_id": r[0], "tg_name": r[1]} for r in rows]
    except:
        return []


def _bind_user(tg_user_id, emby_user_id, emby_username, init_password="", tg_username="", tg_display_name=""):
    """
    绑定 TG 用户与 Emby 账号
    - 确保一个 Emby 账号只能被一个 TG 用户绑定
    - 绑定前会清理该 Emby 账号的旧绑定关系
    """
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        # 先清理该 Emby 账号的所有旧绑定（确保一个 Emby 账号只对应一个 TG 用户）
        conn.execute("DELETE FROM tg_user_bindings WHERE emby_user_id = ?", (emby_user_id,))
        # 然后插入或替换当前绑定
        conn.execute("INSERT OR REPLACE INTO tg_user_bindings (tg_user_id, tg_username, tg_display_name, emby_user_id, emby_username, init_password) VALUES (?, ?, ?, ?, ?, ?)",
                     (str(tg_user_id), tg_username, tg_display_name, emby_user_id, emby_username, init_password))
        conn.commit()
        conn.close()
        # 更新缓存（加锁）
        with _cache_lock:
            _binding_cache[str(tg_user_id)] = {
                "binding": {"emby_user_id": emby_user_id, "emby_username": emby_username, "init_password": init_password},
                "cached_at": time.time()
            }
    except:
        pass


def _rate_check(tg_user_id, cooldown=3):
    now = time.time()
    if now - _rate_limit[tg_user_id] < cooldown:
        return False
    _rate_limit[tg_user_id] = now
    return True


def _is_blacklisted(tg_user_id):
    """检查是否在黑名单（带缓存，线程安全）"""
    cache_key = str(tg_user_id)
    
    with _cache_lock:
        cached = _blacklist_cache.get(cache_key)
        if cached and (time.time() - cached["cached_at"] < _BLACKLIST_CACHE_TTL):
            return cached["blacklisted"]
    
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        row = conn.execute("SELECT 1 FROM tg_user_blacklist WHERE tg_user_id = ?", (cache_key,)).fetchone()
        conn.close()
        result = bool(row)
        with _cache_lock:
            _blacklist_cache[cache_key] = {"blacklisted": result, "cached_at": time.time()}
        return result
    except:
        return False


def _add_to_blacklist(tg_user_id, reason=""):
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        conn.execute("INSERT OR REPLACE INTO tg_user_blacklist (tg_user_id, reason) VALUES (?, ?)", (str(tg_user_id), reason))
        conn.commit()
        conn.close()
    except Exception: pass


def _check_emby_account(binding):
    """检查绑定的 Emby 账号是否还存在（带缓存，线程安全）"""
    if not binding:
        return False
    
    user_id = binding['emby_user_id']
    
    # 检查缓存
    with _cache_lock:
        cached = _emby_account_cache.get(user_id)
        if cached and (time.time() - cached["cached_at"] < _EMBY_ACCOUNT_CACHE_TTL):
            return cached["exists"]
    
    try:
        res = media_api.get(f"/Users/{user_id}", timeout=5)
        exists = res.status_code == 200
        # 更新缓存
        with _cache_lock:
            _emby_account_cache[user_id] = {"exists": exists, "cached_at": time.time()}
        return exists
    except:
        return True  # 网络异常时不误判，返回 True 表示账号可能还在


def _get_username_lock(username_lower):
    """获取用户名锁（防止并发注册时用户名冲突），带清理机制"""
    with _username_locks_lock:
        # 如果锁数量超过上限，清理一半（简单的清理策略）
        if len(_username_locks) > _USERNAME_LOCK_MAX_SIZE:
            # 保留最近一半的锁
            keys_to_remove = list(_username_locks.keys())[:_USERNAME_LOCK_MAX_SIZE // 2]
            for key in keys_to_remove:
                del _username_locks[key]
            logger.info(f"[UserBot] 清理用户名锁，移除 {len(keys_to_remove)} 个")
        
        if username_lower not in _username_locks:
            _username_locks[username_lower] = threading.Lock()
        return _username_locks[username_lower]

# ==========================================
# 可视化卡片菜单
# ==========================================

def _main_menu_keyboard(binding=None):
    """生成主菜单 inline keyboard"""
    if not binding:
        return {"inline_keyboard": [
            [{"text": "📝 绑定已有账号", "callback_data": "ub_menu_bind"}, {"text": "🆕 注册新账号", "callback_data": "ub_menu_register"}],
            [{"text": "🎟️ 注册码激活", "callback_data": "ub_menu_code"}, {"text": "📊 媒体库统计", "callback_data": "ub_menu_library"}]
        ]}
    rows = [
        [{"text": "✅ 每日签到", "callback_data": "ub_menu_checkin"}, {"text": "👤 个人中心", "callback_data": "ub_menu_profile"}],
        [{"text": "🏪 积分商城", "callback_data": "ub_menu_shop"}, {"text": "🎬 我要求片", "callback_data": "ub_menu_request"}],
        [{"text": "📋 我的求片", "callback_data": "ub_menu_myrequests"}],
        [{"text": "📊 媒体库统计", "callback_data": "ub_menu_library"}],
        [{"text": "🔐 修改密码", "callback_data": "ub_menu_password"}, {"text": "📡 服务器状态", "callback_data": "ub_menu_server"}],
        [{"text": "🎟️ 续期码续期", "callback_data": "ub_menu_renew"}],
        [{"text": "🔓 解绑账号", "callback_data": "ub_menu_unbind"}],
    ]
    # 用户中心网页链接
    portal_url = cfg.get("user_bot_portal_url")
    if portal_url:
        rows.append([{"text": "🌐 网页版用户中心", "url": portal_url}])
    return {"inline_keyboard": rows}


def cmd_start(chat_id, tg_user_id, tg_name):
    # 记录用户（所有 /start 过的用户）
    _record_bot_user(tg_user_id, tg_name)
    
    binding = _get_binding(tg_user_id)
    if binding:
        msg = (f"👋 欢迎回来，<b>{binding['emby_username']}</b>！\n\n"
               f"🎬 EmbyPulse 用户自助服务\n"
               f"请选择你需要的服务：")
    else:
        msg = (f"👋 你好 <b>{tg_name}</b>！\n\n"
               f"🎬 这是 <b>EmbyPulse</b> 用户自助服务机器人\n\n"
               f"你还没有绑定账号，请先完成绑定或注册：")
    _send(chat_id, msg, reply_markup=_main_menu_keyboard(binding))


def cmd_help(chat_id, tg_user_id):
    binding = _get_binding(tg_user_id)
    status = f"✅ 已绑定：<b>{binding['emby_username']}</b>" if binding else "❌ 未绑定账号"
    _send(chat_id,
          f"🤖 <b>EmbyPulse 用户助手</b>\n\n{status}\n\n"
          "📋 <b>命令列表</b>\n"
          "/bind 用户名 — 绑定 Emby 账号\n"
          "/register — 开放注册\n"
          "/code 注册码 — 注册码激活\n"
          "/renew 续期码 — 续期码续期\n"
          "/checkin — 每日签到\n"
          "/points — 积分余额\n"
          "/shop — 积分商城\n"
          "/pk 积分 — PK掷骰子\n"
          "/lottery 号码 — 彩票\n"
          "/scratch — 刮刮乐\n"
          "/request 关键词 — 求片\n"
          "/server — 服务器状态\n"
          "/library — 媒体库统计\n"
          "/menu — 返回主菜单",
          reply_markup=_main_menu_keyboard(binding))


def cmd_bind(chat_id, tg_user_id, args, tg_username="", tg_display_name=""):
    if not args or ' ' not in args.strip():
        _send(chat_id, "📝 <b>绑定账号</b>\n\n请发送命令（用户名和密码用空格隔开）：\n<code>/bind 用户名 密码</code>\n\n例如：<code>/bind zhangsan mypassword</code>")
        return
    parts = args.strip().split(' ', 1)
    username = parts[0].strip()
    password = parts[1].strip() if len(parts) > 1 else ""
    if not password:
        _send(chat_id, "❌ 请同时输入密码：/bind 用户名 密码")
        return
    try:
        # 通过 Emby AuthenticateByName 验证身份
        host = cfg.get("emby_host")
        url = f"{host}/emby/Users/AuthenticateByName"
        headers = {"X-Emby-Authorization": 'MediaBrowser Client="EmbyPulse", Device="TGBot", DeviceId="UserBot", Version="1.0.0"'}
        res = requests.post(url, json={"Username": username, "Pw": password}, headers=headers, timeout=10)
        if res.status_code != 200:
            _send(chat_id, "❌ 用户名或密码错误，请检查后重试")
            return
        user_info = res.json().get("User", {})
        uid = user_info.get("Id")
        uname = user_info.get("Name", username)
        _bind_user(tg_user_id, uid, uname, tg_username=tg_username, tg_display_name=tg_display_name)
        _send(chat_id, f"✅ <b>绑定成功！</b>\n\n👤 Emby 账号：<b>{uname}</b>\n\n发送 /menu 打开主菜单",
              reply_markup=_main_menu_keyboard({"emby_user_id": uid, "emby_username": uname}))
    except Exception as e:
        _send(chat_id, f"❌ 绑定失败：{e}")


def cmd_register(chat_id, tg_user_id, tg_name):
    if not cfg.get("user_bot_open_reg"):
        _send(chat_id, "❌ 开放注册未开启，请联系管理员获取注册码后使用 /code 注册码")
        return
    if _get_binding(tg_user_id):
        _send(chat_id, "❌ 你已经绑定了账号，无需重复注册")
        return
    if _is_blacklisted(tg_user_id):
        _send(chat_id, "🚫 你的账号已被管理员限制注册，如有疑问请联系管理员。\n\n如果你有注册码，可以使用 /code 注册码 进行注册。")
        return
    # 进入注册流程：等待用户输入用户名
    _user_state[str(tg_user_id)] = {"action": "register_name"}
    _send(chat_id, "🆕 <b>注册新账号</b>\n\n请输入你想要的用户名（支持字母、数字、中文、下划线(_)、连字符(-)、@、.）：",
          reply_markup={"inline_keyboard": [[{"text": "❌ 取消", "callback_data": "ub_cancel_state"}]]})


# ==========================================
# 注册 quota 软预占 / 用户数缓存 / batch_used 落盘
# ==========================================

def _load_batch_used_from_cfg():
    """从 cfg.json 加载 batch_used 到内存，幂等"""
    global _batch_used_mem, _batch_used_dirty
    with _batch_used_lock:
        if _batch_used_mem is None:
            try:
                _batch_used_mem = int(cfg.get("user_bot_reg_batch_used", 0) or 0)
            except Exception:
                _batch_used_mem = 0
            _batch_used_dirty = 0


def _flush_batch_used(force=False):
    """把内存中的 batch_used 落盘到 cfg.json"""
    global _batch_used_dirty
    with _batch_used_lock:
        if _batch_used_mem is None:
            return
        if not force and _batch_used_dirty == 0:
            return
        try:
            cfg.set("user_bot_reg_batch_used", _batch_used_mem)
            _batch_used_dirty = 0
        except Exception:
            logger.exception("[UserBot] batch_used 落盘失败")


def _batch_flush_loop():
    """后台线程：周期性把 _batch_used_mem flush 到 cfg.json"""
    while not _batch_flush_stop.is_set():
        try:
            if _batch_flush_stop.wait(BATCH_FLUSH_INTERVAL):
                break
            _flush_batch_used()
        except Exception:
            logger.exception("[UserBot] batch_used flush 循环异常")
            # 出错后稍候再试，避免热循环
            if _batch_flush_stop.wait(5):
                break


def _start_batch_flush_thread():
    """启动后台 flush 线程（幂等）"""
    global _batch_flush_thread
    _batch_flush_stop.clear()
    if _batch_flush_thread is not None and _batch_flush_thread.is_alive():
        return
    _batch_flush_thread = threading.Thread(target=_batch_flush_loop, daemon=True, name="batch-flush")
    _batch_flush_thread.start()


def get_batch_used_snapshot():
    """对外暴露的 batch_used 当前值，供 API 读取（避免 cfg.json 滞后）"""
    with _batch_used_lock:
        if _batch_used_mem is not None:
            return _batch_used_mem
    try:
        return int(cfg.get("user_bot_reg_batch_used", 0) or 0)
    except Exception:
        return 0


def _refresh_user_count_cache_locked(force=False, quota=0):
    """在 _quota_lock 持有的前提下刷新缓存。返回 count 或 None。
    quota>0 且当前 count 接近上限时，强制刷新以保证准确。
    """
    now = time.time()
    cached = _user_count_cache.get("count")
    cached_ts = _user_count_cache.get("ts", 0.0)
    fresh = (cached is not None) and (now - cached_ts < USER_COUNT_CACHE_TTL)
    near_limit = (
        quota > 0 and cached is not None
        and cached >= max(0, quota - USER_COUNT_NEAR_LIMIT_MARGIN)
    )
    if fresh and not force and not near_limit:
        return cached
    try:
        users = media_api.get("/Users", timeout=5).json()
        hidden_users = cfg.get("hidden_users") or []
        normal_users = [
            u for u in users
            if u.get("Name") not in hidden_users
            and not u.get("Policy", {}).get("IsAdministrator")
        ]
        _user_count_cache["count"] = len(normal_users)
        _user_count_cache["users"] = users
        _user_count_cache["ts"] = now
        return _user_count_cache["count"]
    except Exception as e:
        logger.warning(f"[UserBot] 刷新 Emby 用户数失败: {e}")
        return cached  # 退回到旧值（也可能是 None）


def _invalidate_user_count_cache():
    with _quota_lock:
        _user_count_cache["ts"] = 0.0


def get_cached_user_count_for_api(force=False):
    """供 /api/bot/reg_quota_status 读取的入口"""
    with _quota_lock:
        cnt = _refresh_user_count_cache_locked(force=force)
    return cnt if cnt is not None else 0


def get_users_list_cached(max_age=USER_COUNT_CACHE_TTL):
    """获取缓存的 Emby 用户列表（用于重名检查）。缓存失效时现拉。
    返回 list 或 None（失败时）。
    """
    with _quota_lock:
        users = _user_count_cache.get("users")
        ts = _user_count_cache.get("ts", 0.0)
        if users is not None and time.time() - ts < max_age:
            return users
    # 缓存失效，主动刷新一次
    with _quota_lock:
        _refresh_user_count_cache_locked(force=True)
        return _user_count_cache.get("users")


def _reserve_quota_slot(quota_mode, quota):
    """软预占一个 quota 槽。成功返回 (True, None)，失败返回 (False, reason)。
    reason in {"batch_full", "total_full", "emby_unreachable"}。
    成功时 _quota_reserved 自增；调用方必须保证最终 _release_quota_slot 被调用。
    """
    global _quota_reserved
    if quota <= 0:
        return True, None
    with _quota_lock:
        if quota_mode == "batch":
            _load_batch_used_from_cfg()  # 确保 _batch_used_mem 已初始化
            used = _batch_used_mem or 0
            if used + _quota_reserved >= quota:
                return False, "batch_full"
            _quota_reserved += 1
            return True, None
        # total 模式
        cnt = _refresh_user_count_cache_locked(quota=quota)
        if cnt is None:
            # Emby 不可达：保守拒绝，避免无脑放行造成超额
            if _quota_reserved > 0:
                return False, "emby_unreachable"
            # 没有任何在飞预占且缓存为空 → 让首请求探路放行
            _quota_reserved += 1
            return True, None
        if cnt + _quota_reserved >= quota:
            # 临近上限，再强制刷新一次确认
            cnt2 = _refresh_user_count_cache_locked(force=True, quota=quota)
            if cnt2 is not None and cnt2 + _quota_reserved >= quota:
                return False, "total_full"
        _quota_reserved += 1
        return True, None


def _release_quota_slot(committed, quota_mode, quota):
    """释放软预占。committed=True 表示注册真的成功了。
    - batch 模式：committed 时把 _batch_used_mem 自增 1，达 quota 关注册并通知。
    - total 模式：committed 时失效用户数缓存，并强制刷新检查是否需要关注册。
    """
    global _quota_reserved
    with _quota_lock:
        if _quota_reserved > 0:
            _quota_reserved -= 1
    if not committed:
        return
    if quota_mode == "batch":
        _inc_batch_used(quota)
    else:
        # total: 缓存里的旧 count 已经无效（多了一个新用户）
        _invalidate_user_count_cache()
        if quota > 0:
            with _quota_lock:
                cnt = _refresh_user_count_cache_locked(force=True, quota=quota)
            if cnt is not None and cnt >= quota:
                try:
                    cfg.set("user_bot_open_reg", False)
                    logger.info(f"[UserBot] 用户总数已达上限({cnt}/{quota})，开放注册已自动关闭")
                    _send_open_reg_closed_notify("用户总数已达上限")
                except Exception:
                    logger.exception("[UserBot] 关闭开放注册失败")


def _inc_batch_used(quota):
    """batch 模式：注册成功后递增 batch_used。达 quota 立即落盘并关注册。"""
    global _batch_used_mem, _batch_used_dirty
    closed_now = False
    with _batch_used_lock:
        if _batch_used_mem is None:
            try:
                _batch_used_mem = int(cfg.get("user_bot_reg_batch_used", 0) or 0)
            except Exception:
                _batch_used_mem = 0
            _batch_used_dirty = 0
        _batch_used_mem += 1
        _batch_used_dirty += 1
        should_flush = _batch_used_dirty >= BATCH_FLUSH_THRESHOLD
        if quota > 0 and _batch_used_mem >= quota:
            closed_now = True
            should_flush = True
        if should_flush:
            try:
                cfg.set("user_bot_reg_batch_used", _batch_used_mem)
                _batch_used_dirty = 0
            except Exception:
                logger.exception("[UserBot] batch_used 落盘失败")
    if closed_now:
        try:
            cfg.set("user_bot_open_reg", False)
            logger.info(f"[UserBot] 批次注册名额已用完({_batch_used_mem}/{quota})，开放注册已自动关闭")
            _send_open_reg_closed_notify("批次名额已满")
        except Exception:
            logger.exception("[UserBot] 关闭开放注册失败")


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
        if not cfg.get("user_bot_open_reg"):
            _send(chat_id, "❌ 开放注册已关闭，请联系管理员获取注册码后使用 /code 注册码")
            return

        # 🎯 支持两种名额模式
        quota_mode = cfg.get("user_bot_reg_quota_mode", "total")
        try:
            quota = int(cfg.get("user_bot_reg_quota", 0) or 0)
        except Exception:
            quota = 0

        # 🔒 软预占 quota（在调用 Emby 建号前先占槽，杜绝并发超额）
        if quota > 0:
            ok, reason = _reserve_quota_slot(quota_mode, quota)
            if not ok:
                if reason == "batch_full":
                    _send(chat_id, "❌ 本次开放注册名额已用完，请联系管理员")
                    try:
                        cfg.set("user_bot_open_reg", False)
                    except Exception:
                        pass
                    _send_open_reg_closed_notify("批次名额已满")
                elif reason == "total_full":
                    _send(chat_id, "❌ 用户数量已达上限，开放注册已自动关闭")
                    try:
                        cfg.set("user_bot_open_reg", False)
                    except Exception:
                        pass
                    _send_open_reg_closed_notify("用户总数已达上限")
                else:
                    _send(chat_id, "❌ 暂时无法检查注册名额，请稍后重试")
                return
            reserved = True

        max_reg = int(cfg.get("user_bot_max_reg", 0))
        if max_reg > 0 and quota <= 0:
            try:
                conn = sqlite3.connect(SYSTEM_DB_PATH)
                count = conn.execute("SELECT COUNT(*) FROM tg_user_bindings").fetchone()[0]
                conn.close()
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

                template_id = cfg.get("user_bot_template_user") or cfg.get("default_user_template_id")
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

                reg_days = int(cfg.get("user_bot_reg_days", 30))
                expire = (datetime.date.today() + datetime.timedelta(days=reg_days)).strftime("%Y-%m-%d")

                allow_routes = cfg.get("user_bot_allow_routes", "")
                block_routes = cfg.get("user_bot_block_routes", "")

                if allow_routes or block_routes:
                    query_db("INSERT OR REPLACE INTO users_meta (user_id, expire_date, allow_routes, block_routes, created_at) VALUES (?, ?, ?, ?, datetime('now','localtime'))",
                             (uid, expire, allow_routes, block_routes))
                else:
                    template_routes = None
                    if template_id:
                        try:
                            template_meta = query_db("SELECT allow_routes, block_routes FROM users_meta WHERE user_id = ?", (template_id,), one=True)
                            if template_meta and (template_meta.get('allow_routes') or template_meta.get('block_routes')):
                                template_routes = template_meta
                        except Exception: pass

                    if template_routes:
                        query_db("INSERT OR REPLACE INTO users_meta (user_id, expire_date, allow_routes, block_routes, created_at) VALUES (?, ?, ?, ?, datetime('now','localtime'))",
                                 (uid, expire, template_routes.get('allow_routes', ''), template_routes.get('block_routes', '')))
                    else:
                        query_db("INSERT OR REPLACE INTO users_meta (user_id, expire_date, created_at) VALUES (?, ?, datetime('now','localtime'))", (uid, expire))

                _bind_user(tg_user_id, uid, safe_name, init_password=password, tg_username=tg_username or tg_display_name, tg_display_name=tg_display_name or str(tg_user_id))

                try:
                    conn = sqlite3.connect(SYSTEM_DB_PATH)
                    conn.execute("INSERT INTO tg_reg_logs (tg_user_id, emby_username, emby_user_id, reg_type) VALUES (?, ?, ?, 'open')",
                                 (str(tg_user_id), safe_name, uid))
                    conn.commit()
                    conn.close()
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
                _send(chat_id, f"❌ 注册异常：{e}")
    finally:
        if reserved:
            try:
                _release_quota_slot(committed, quota_mode, quota)
            except Exception:
                logger.exception("[UserBot] 释放 quota 预占失败")
        _leave_reg_queue()


def cmd_check(chat_id, tg_user_id):
    """检查使用限制状态"""
    # 清除缓存，强制重新检查
    _clear_restriction_cache(tg_user_id)
    
    restriction_check = _check_user_restrictions(tg_user_id)
    
    if restriction_check["passed"]:
        _send(chat_id, "✅ <b>验证通过</b>\n\n你已经满足使用条件，可以正常使用机器人功能。")
    else:
        _send(chat_id, _format_restriction_message(restriction_check))


def cmd_code(chat_id, tg_user_id, args):
    if not args:
        _send(chat_id, "❌ 请输入注册码：/code 你的注册码")
        return
    code = args.strip()
    if _get_binding(tg_user_id):
        _send(chat_id, "❌ 你已经绑定了账号，如需续期请使用 /renew 续期码")
        return

    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        # 🔥 只查询注册码（type = 'register' 或 type 为空），不能使用续期码注册
        row = conn.execute("SELECT days, used_count, max_uses, template_user_id, routes, route_mode FROM invitations WHERE code = ? AND status = 0 AND (type = 'register' OR type IS NULL)", (code,)).fetchone()
        if not row:
            conn.close()
            _send(chat_id, "❌ 注册码无效、已被使用或不是注册码")
            return
        days, used, max_uses, tpl_id, routes, route_mode = row
        if used >= max_uses:
            conn.close()
            _send(chat_id, "❌ 该注册码已达使用上限")
            return

        # 验证注册码有效，进入等待用户输入用户名状态
        _user_state[str(tg_user_id)] = {"action": "code_input_name", "code": code, "days": days, "tpl_id": tpl_id, "routes": routes, "route_mode": route_mode}
        _send(chat_id, "🎟️ <b>注册码验证成功！</b>\n\n请输入你想要的用户名（支持字母、数字、中文、下划线(_)、连字符(-)、@、.）：",
              reply_markup={"inline_keyboard": [[{"text": "❌ 取消", "callback_data": "ub_cancel_state"}]]})
        conn.close()
        return
    except Exception as e:
        _send(chat_id, f"❌ 注册码验证失败：{e}")
        return


def _restore_invitation_code(code):
    """Emby 用户创建失败时回滚邀请码消费计数"""
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        conn.execute(
            "UPDATE invitations SET used_count = MAX(used_count - 1, 0), used_by = NULL, used_at = NULL WHERE code = ?",
            (code,)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def _do_code_register(chat_id, tg_user_id, custom_name, code, days, tpl_id, routes=None, route_mode=None, tg_username="", tg_display_name=""):
    """执行注册码激活创建账号逻辑"""
    # 🚀 进入注册队列
    if not _enter_reg_queue(chat_id):
        return
    
    try:
        # 验证用户名格式
        # 检查用户名长度限制
        if len(custom_name) > 16:
            _send(chat_id, f"❌ 用户名最多 16 个字符，当前 {len(custom_name)} 个字符")
            _user_state[str(tg_user_id)] = {"action": "code_input_name", "code": code, "days": days, "tpl_id": tpl_id, "routes": routes, "route_mode": route_mode}
            return
        
        safe_name = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fa5_\-.@]', '', custom_name)
        
        if safe_name != custom_name:
            invalid_chars = set(re.findall(r'[^a-zA-Z0-9\u4e00-\u9fa5_\-.@]', custom_name))
            invalid_str = ', '.join(f"'{c}'" for c in list(invalid_chars)[:5])
            _send(chat_id, f"❌ 用户名包含不支持的字符: {invalid_str}\n\n只允许字母、数字、中文、下划线(_)、连字符(-)、@ 和 .")
            _user_state[str(tg_user_id)] = {"action": "code_input_name", "code": code, "days": days, "tpl_id": tpl_id, "routes": routes, "route_mode": route_mode}
            return
        
        if not safe_name:
            _send(chat_id, "❌ 用户名无效，请使用字母、数字、中文、下划线(_)、连字符(-)、@ 或 .")
            _user_state[str(tg_user_id)] = {"action": "code_input_name", "code": code, "days": days, "tpl_id": tpl_id, "routes": routes, "route_mode": route_mode}
            return
        
        password = secrets.token_urlsafe(8)

        # 🚀 获取用户名锁
        username_lock = _get_username_lock(safe_name.lower())
        
        with username_lock:
            try:
                users = media_api.get("/Users", timeout=5).json()
                if any(u['Name'].lower() == safe_name.lower() for u in users):
                    _send(chat_id, f"❌ 用户名 <b>{safe_name}</b> 已被占用，请换一个")
                    _user_state[str(tg_user_id)] = {"action": "code_input_name", "code": code, "days": days, "tpl_id": tpl_id, "routes": routes, "route_mode": route_mode}
                    return

                # 原子抢占注册码（防 TOCTOU 竞态）
                conn = sqlite3.connect(SYSTEM_DB_PATH)
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    cur = conn.execute(
                        """UPDATE invitations
                           SET used_count = used_count + 1,
                               used_at = datetime('now','localtime'),
                               used_by = ?
                           WHERE code = ? AND status != 1 AND used_count < max_uses""",
                        (safe_name, code)
                    )
                    if cur.rowcount == 0:
                        conn.rollback()
                        conn.close()
                        _send(chat_id, "❌ 注册码已失效或已达到使用上限")
                        return
                    conn.commit()
                except Exception:
                    conn.rollback()
                    conn.close()
                    raise
                conn.close()

                create_res = media_api.post("/Users/New", json={"Name": safe_name}, timeout=10)
                if create_res.status_code not in [200, 201]:
                    # Emby 创建失败，回滚注册码消费
                    _restore_invitation_code(code)
                    _send(chat_id, "❌ 创建账号失败")
                    return
                new_user = create_res.json()
                uid = new_user.get("Id")
                media_api.post(f"/Users/{uid}/Password", json={"NewPw": password}, timeout=5)

                if tpl_id:
                    try:
                        tpl = media_api.get(f"/Users/{tpl_id}", timeout=5).json()
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

                if days == -1 or days == 0 or days >= 36500:
                    expire = None  # 永久有效用 None 表示
                else:
                    expire = (datetime.date.today() + datetime.timedelta(days=days)).strftime("%Y-%m-%d")

                allow_routes = ""
                block_routes = ""
                if routes:
                    if route_mode == 'allow':
                        allow_routes = routes
                    else:
                        block_routes = routes

                conn = sqlite3.connect(SYSTEM_DB_PATH)
                conn.execute("""INSERT OR REPLACE INTO users_meta
                    (user_id, expire_date, allow_routes, block_routes, created_at)
                    VALUES (?, ?, ?, ?, datetime('now','localtime'))""",
                    (uid, expire, allow_routes, block_routes))
                # 标记注册码已用完（如果到达上限）
                conn.execute("UPDATE invitations SET status = 1 WHERE code = ? AND used_count >= max_uses", (code,))
                conn.commit()
                conn.close()

                # 清除用户列表缓存
                try:
                    from app.routers.users import invalidate_emby_users_cache
                    invalidate_emby_users_cache()
                except:
                    pass

                _bind_user(tg_user_id, uid, safe_name, init_password=password, tg_username=tg_username or tg_display_name, tg_display_name=tg_display_name or str(tg_user_id))
                
                if days == -1 or days == 0 or days >= 36500:
                    expire_display = "♾️ 永久有效"
                else:
                    expire_display = f"{days} 天（至 {expire}）"
                
                _send(chat_id, f"🎉 <b>注册码激活成功！</b>\n\n👤 用户名：<code>{safe_name}</code>\n🔑 密码：<code>{password}</code>\n📅 有效期：{expire_display}\n\n💡 密码可在「个人中心」随时查看")

                try:
                    from app.services.bot_service import bot
                    from app.core.database import add_sys_notification
                    days_display = "永久" if (days == -1 or days == 0 or days >= 36500) else f"{days} 天"
                    msg = f"🎟️ <b>新用户注册</b>\n\n👤 {safe_name}\n📅 有效期：{days_display}\n🔗 邀请码：{code}\n📱 注册渠道：TG机器人\n🆔 TG：{tg_user_id}"
                    bot.send_message("sys_notify", msg, platform="all")
                    add_sys_notification("user", f"新用户注册: {safe_name}", f"TG机器人注册，有效期 {days_display}", "/users_manage")
                except Exception: pass
            except Exception as e:
                _send(chat_id, f"❌ 注册码使用失败：{e}")
    finally:
        _leave_reg_queue()


def cmd_renew(chat_id, tg_user_id, args):
    if not args:
        _send(chat_id, "❌ 请输入续期码：/renew 你的续期码")
        return
    binding = _get_binding(tg_user_id)
    if not binding:
        _send(chat_id, "❌ 请先绑定账号：/bind 用户名")
        return
    code = args.strip()
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        conn.execute("BEGIN IMMEDIATE")
        # 🔥 原子抢占续期码（防 TOCTOU 竞态）
        cur = conn.execute(
            """UPDATE invitations
               SET used_count = used_count + 1,
                   used_at = datetime('now','localtime'),
                   used_by = ?
               WHERE code = ? AND status != 1 AND used_count < max_uses
               AND type = 'renew'""",
            (binding['emby_username'], code)
        )
        if cur.rowcount == 0:
            conn.rollback()
            conn.close()
            _send(chat_id, "❌ 续期码无效、已被使用、不是续期码或已达使用上限")
            return

        row = conn.execute("SELECT days FROM invitations WHERE code = ?", (code,)).fetchone()
        days = row[0]

        uid = binding['emby_user_id']
        exp_row = conn.execute("SELECT expire_date FROM users_meta WHERE user_id = ?", (uid,)).fetchone()
        current_exp = exp_row[0] if exp_row and exp_row[0] else ""

        # 永久有效用户不需要续费
        if current_exp and ("2099" in current_exp or "3000" in current_exp or "永久" in current_exp):
            conn.rollback()
            conn.close()
            _send(chat_id, "❌ 您的账号为永久有效，无需续费！")
            return

        # 处理永久续期码：days = -1 或 days = 0 或 days >= 36500
        if days == -1 or days == 0 or days >= 36500:
            new_exp = "2099-12-31"  # 永久有效
            days_display = "永久"
        else:
            today = datetime.date.today()
            try:
                exp_date = datetime.datetime.strptime(current_exp, "%Y-%m-%d").date() if current_exp else today
                if exp_date < today: exp_date = today
            except: exp_date = today
            new_exp = (exp_date + datetime.timedelta(days=days)).strftime("%Y-%m-%d")
            days_display = f"{days} 天"

        conn.execute("UPDATE users_meta SET expire_date = ? WHERE user_id = ?", (new_exp, uid))
        # 标记续期码已用完（如果到达上限）
        conn.execute("UPDATE invitations SET status = 1 WHERE code = ? AND used_count >= max_uses", (code,))
        conn.commit()
        conn.close()

        # 续期不自动解除禁用状态，保留管理员设置的禁用状态

        _send(chat_id, f"✅ <b>续期成功！</b>\n\n📅 新到期日：{new_exp}\n⏳ 延长了 {days_display}")
    except Exception as e:
        _send(chat_id, f"❌ 续期失败：{e}")


def cmd_checkin(chat_id, tg_user_id, msg_id=None, is_group=False, group_name="", user_msg_id=None):
    """签到功能
    
    Args:
        chat_id: 聊天ID
        tg_user_id: Telegram用户ID
        msg_id: 机器人消息ID（用于编辑）
        is_group: 是否群聊
        group_name: 群名称
        user_msg_id: 用户消息ID（群聊时用于删除用户命令）
    """
    binding = _get_binding(tg_user_id)
    if not binding:
        if is_group:
            result = _reply(chat_id, "❌ 请先私聊机器人绑定账号后再签到", msg_id=msg_id)
            # 30秒后删除消息
            if result and user_msg_id:
                _delete_messages_later(chat_id, [result.get("result", {}).get("message_id"), user_msg_id], 30)
            return
        else:
            _reply(chat_id, "❌ 请先绑定账号", msg_id=msg_id)
            return
    
    # 检查 Emby 账号是否仍然有效
    if not _check_emby_account(binding):
        _unbind_user(tg_user_id)
        if is_group:
            result = _reply(chat_id, "⚠️ 你的 Emby 账号已被删除，绑定已自动解除。请联系管理员。", msg_id=msg_id)
            if result and user_msg_id:
                _delete_messages_later(chat_id, [result.get("result", {}).get("message_id"), user_msg_id], 30)
        else:
            _reply(chat_id, "⚠️ 你的 Emby 账号已被删除，绑定已自动解除。请联系管理员。", 
                   reply_markup=_main_menu_keyboard(None), msg_id=msg_id)
        return
    
    uid = binding['emby_user_id']
    uname = binding['emby_username']
    try:
        import random
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        if c.execute("SELECT 1 FROM point_logs WHERE user_id = ? AND action LIKE '每日签到%' AND date(created_at, 'localtime') = date('now', 'localtime')", (uid,)).fetchone():
            conn.close()
            result = _reply(chat_id, "😊 今天已经签到过了，明天再来吧！", reply_markup={"inline_keyboard": [[{"text": "🔙 主菜单", "callback_data": "ub_back_menu"}]]} if not is_group else None, msg_id=msg_id)
            # 群聊30秒后删除消息
            if is_group and result and user_msg_id:
                bot_msg_id = result.get("result", {}).get("message_id")
                if bot_msg_id:
                    _delete_messages_later(chat_id, [bot_msg_id, user_msg_id], 30)
            return
        config = {r[0]: r[1] for r in c.execute("SELECT key, value FROM point_config").fetchall()}
        reward = random.randint(int(config.get('checkin_min', 10)), int(config.get('checkin_max', 30)))
        
        # 连续签到奖励
        streak_bonus = 0
        streak_count = 0
        import datetime
        if int(config.get('enable_streak_bonus', 0)) == 1:
            today = datetime.date.today()
            yesterday = today - datetime.timedelta(days=1)
            
            # 获取连续签到记录
            streak_row = c.execute("SELECT streak_count, last_checkin FROM point_checkin_streak WHERE user_id = ?", (uid,)).fetchone()
            
            if streak_row:
                last_checkin = streak_row[1]
                if last_checkin == str(yesterday):
                    # 连续签到
                    streak_count = streak_row[0] + 1
                elif last_checkin == str(today):
                    # 今天已签到（理论上不会走到这里）
                    streak_count = streak_row[0]
                else:
                    # 断签
                    if int(config.get('streak_reset_on_miss', 1)) == 1:
                        streak_count = 1
                    else:
                        streak_count = streak_row[0] + 1
            else:
                streak_count = 1
            
            # 计算连续签到奖励
            if streak_count >= 7 and streak_count % 7 == 0:
                streak_bonus = int(config.get('streak_7_days', 100))
            if streak_count >= 30 and streak_count % 30 == 0:
                streak_bonus += int(config.get('streak_30_days', 500))
            
            # 更新连续签到记录
            c.execute("INSERT OR REPLACE INTO point_checkin_streak (user_id, streak_count, last_checkin) VALUES (?, ?, ?)", 
                     (uid, streak_count, str(today)))
        
        total_reward = reward + streak_bonus
        
        row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (uid,)).fetchone()
        new_pts = (row[0] or 0) + total_reward if row else total_reward
        if row: c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_pts, uid))
        else: c.execute("INSERT INTO users_meta (user_id, points) VALUES (?, ?)", (uid, new_pts))
        
        action_desc = "每日签到"
        if streak_bonus > 0:
            action_desc += f" (连续{streak_count}天奖励+{streak_bonus})"
        
        c.execute("INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)", (uid, uname, action_desc, total_reward, new_pts))
        conn.commit()
        conn.close()
        
        # 构建签到消息
        msg_lines = [f"🎉 签到成功！", f"", f"🎲 获得 <b>{reward}</b> 积分"]
        if streak_bonus > 0:
            msg_lines.append(f"🔥 连续签到 <b>{streak_count}</b> 天，额外奖励 <b>{streak_bonus}</b> 积分")
        msg_lines.append(f"💰 当前余额：<b>{new_pts}</b> 积分")
        
        # 群聊签到显示群名
        if is_group and group_name:
            result = _reply(chat_id, f"🎉 <b>{uname}</b> 在 <b>{group_name}</b> 签到成功！\n\n" + "\n".join(msg_lines[1:]), msg_id=msg_id)
        else:
            result = _reply(chat_id, "\n".join(msg_lines),
                  reply_markup={"inline_keyboard": [[{"text": "🏪 去商城逛逛", "callback_data": "ub_menu_shop"}, {"text": "🔙 主菜单", "callback_data": "ub_back_menu"}]]} if not is_group else None, msg_id=msg_id)
        
        # 群聊30秒后删除消息
        if is_group and result and user_msg_id:
            bot_msg_id = result.get("result", {}).get("message_id")
            if bot_msg_id:
                _delete_messages_later(chat_id, [bot_msg_id, user_msg_id], 30)
    except Exception as e:
        _send(chat_id, f"❌ 签到失败：{e}")


def _delete_messages_later(chat_id, message_ids, delay_seconds=30):
    """延迟删除消息（用于群聊签到自动清理）"""
    import threading
    def delete_messages():
        import time
        time.sleep(delay_seconds)
        token = cfg.get("tg_user_bot_token")
        if not token:
            return
        for msg_id in message_ids:
            if msg_id:
                try:
                    requests.post(
                        f"https://api.telegram.org/bot{token}/deleteMessage",
                        json={"chat_id": chat_id, "message_id": msg_id},
                        proxies=_get_proxies(),
                        timeout=10
                    )
                except:
                    pass
    threading.Thread(target=delete_messages, daemon=True).start()


def cmd_points(chat_id, tg_user_id, msg_id=None, is_group=False):
    binding = _get_binding(tg_user_id)
    if not binding:
        if is_group:
            return _reply(chat_id, "❌ 请先私聊机器人绑定账号", msg_id=msg_id)
        else:
            return _reply(chat_id, "❌ 请先绑定账号", msg_id=msg_id)
    
    # 检查 Emby 账号是否仍然有效
    if not _check_emby_account(binding):
        _unbind_user(tg_user_id)
        if is_group:
            return _reply(chat_id, "⚠️ 你的 Emby 账号已被删除，绑定已自动解除。请联系管理员。", msg_id=msg_id)
        else:
            return _reply(chat_id, "⚠️ 你的 Emby 账号已被删除，绑定已自动解除。请联系管理员。", 
                          reply_markup=_main_menu_keyboard(None), msg_id=msg_id)
    
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        row = conn.execute("SELECT points FROM users_meta WHERE user_id = ?", (binding['emby_user_id'],)).fetchone()
        pts = row[0] if row and row[0] else 0
        conn.close()
        if is_group:
            return _reply(chat_id, f"💰 <b>{binding['emby_username']}</b> 的积分余额：<b>{pts}</b>", msg_id=msg_id)
        else:
            return _reply(chat_id, f"💰 <b>{binding['emby_username']}</b> 的积分余额\n\n🪙 当前积分：<b>{pts}</b>",
                  reply_markup={"inline_keyboard": [[{"text": "✅ 签到", "callback_data": "ub_menu_checkin"}, {"text": "🏪 商城", "callback_data": "ub_menu_shop"}, {"text": "🔙 主菜单", "callback_data": "ub_back_menu"}]]}, msg_id=msg_id)
    except:
        return _reply(chat_id, "❌ 查询失败", msg_id=msg_id)

# ==================== 🔥 新增群聊积分命令 ====================

def cmd_rank(chat_id, tg_user_id, is_group=False):
    """积分排行榜"""
    try:
        # 先获取 Emby 用户列表，用于过滤已删除的用户
        try:
            from app.core.media_adapter import media_api
            emby_users = media_api.get("/Users", timeout=5).json()
            emby_user_ids = {u['Id'] for u in emby_users}
            emby_name_map = {u['Id']: u['Name'] for u in emby_users}
        except:
            emby_user_ids = set()
            emby_name_map = {}
        
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        c.execute("SELECT user_id, points FROM users_meta WHERE points > 0 ORDER BY points DESC LIMIT 20")
        rows = c.fetchall()
        
        if not rows:
            conn.close()
            return _send(chat_id, "📭 暂无积分数据")
        
        # 过滤掉不存在的用户
        valid_rows = [(uid, pts) for uid, pts in rows if uid in emby_user_ids]
        
        if not valid_rows:
            conn.close()
            return _send(chat_id, "📭 暂无积分数据")
        
        # 只取前10个有效用户
        valid_rows = valid_rows[:10]
        
        # 获取 TG 用户名和显示名称映射
        c.execute("SELECT emby_user_id, tg_username, tg_display_name FROM tg_user_bindings")
        tg_rows = c.fetchall()
        tg_name_map = {}
        for row in tg_rows:
            # 优先使用显示名称，其次使用 @username
            if row[2]:  # tg_display_name
                tg_name_map[row[0]] = row[2]
            elif row[1]:  # tg_username
                tg_name_map[row[0]] = f"@{row[1]}"
        conn.close()
        
        msg = "🏆 <b>积分排行榜 Top 10</b>\n\n"
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        for i, row in enumerate(valid_rows):
            user_id = row[0]
            # 优先显示 TG 用户名(@username)或显示名称
            # 如果没有绑定 TG，隐藏 Emby 用户名（显示“用户***”）
            if user_id in tg_name_map:
                user_name = tg_name_map[user_id]
            else:
                emby_name = emby_name_map.get(user_id, "用户")
                # 隐藏部分用户名：显示前2个字符 + ***
                if len(emby_name) > 2:
                    user_name = emby_name[:2] + "***"
                else:
                    user_name = "用户***"
            msg += f"{medals[i]} <b>{user_name}</b> - {row[1]} 积分\n"
        
        return _send(chat_id, msg.strip())
    except Exception as e:
        logger.error(f"[UserBot] 排行榜查询失败: {e}")
        return _send(chat_id, "❌ 查询失败")

def cmd_rob(chat_id, tg_user_id, text, is_group=False, entities=None):
    """打劫功能"""
    binding = _get_binding(tg_user_id)
    if not binding:
        return _send(chat_id, "❌ 请先私聊机器人绑定账号")
    
    # 解析参数: /rob @用户 或 /打劫 用户名
    parts = text.split()
    if len(parts) < 2:
        return _send(chat_id, "💡 使用方法：/rob @用户\n示例：/rob @张三\n\n💡 也可以直接使用 Emby 用户名")
    
    try:
        # 用户名可能是多个部分
        target = ' '.join(parts[1:]).lstrip('@')
        
        if not target:
            return _send(chat_id, "❌ 请指定要打劫的用户")
        
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        
        # 获取配置
        config = {r[0]: r[1] for r in c.execute("SELECT key, value FROM point_config").fetchall()}
        
        # 检查是否启用打劫
        if int(config.get('enable_rob', 0)) == 0:
            conn.close()
            return _send(chat_id, "❌ 打劫功能未开启")
        
        # 获取配置参数
        success_rate = int(config.get('rob_success_rate', 50))
        rob_min = int(config.get('rob_min', 1))
        rob_max = int(config.get('rob_max', 10))
        counter_rate = int(config.get('rob_counter_rate', 30))
        counter_min = int(config.get('rob_counter_min', 1))
        counter_max = int(config.get('rob_counter_max', 5))
        protect_threshold = int(config.get('rob_protect_threshold', 50))
        max_per_day = int(config.get('rob_max_per_day', 5))
        max_be_robbed = int(config.get('rob_max_be_robbed', 3))
        cooldown_hours = int(config.get('rob_cooldown_hours', 2))
        
        # 🔥 优先从 entities 获取被 @ 用户的真实 TG ID
        mentioned_user_id = None
        if entities:
            for ent in entities:
                if ent.get("type") == "mention" or ent.get("type") == "text_mention":
                    if ent.get("type") == "text_mention" and ent.get("user"):
                        mentioned_user_id = str(ent["user"].get("id", ""))
                        break
                    elif ent.get("type") == "mention":
                        offset = ent.get("offset", 0)
                        length = ent.get("length", 0)
                        mentioned_username = text[offset:offset+length].lstrip('@')
                        c.execute("SELECT tg_user_id FROM tg_user_bindings WHERE tg_username = ?", (mentioned_username,))
                        row = c.fetchone()
                        if row:
                            mentioned_user_id = row[0]
                        break
        
        # 通过 TG 用户ID或用户名查找绑定的 Emby 用户
        to_user_id = None
        to_user_name = None
        to_tg_display_name = None
        
        if mentioned_user_id:
            c.execute("SELECT emby_user_id, emby_username, tg_display_name FROM tg_user_bindings WHERE tg_user_id = ?", (mentioned_user_id,))
            row = c.fetchone()
            if row:
                to_user_id = row[0]
                to_user_name = row[1]
                to_tg_display_name = row[2] or row[1]
        
        if not to_user_id:
            c.execute("SELECT emby_user_id, emby_username, tg_display_name FROM tg_user_bindings WHERE tg_user_id = ? OR tg_username = ?", (target, target))
            row = c.fetchone()
            
            if not row:
                try:
                    from app.core.media_adapter import media_api
                    emby_users = media_api.get("/Users", timeout=5).json()
                    user_map = {u['Name']: u['Id'] for u in emby_users}
                    to_user_id = user_map.get(target)
                    to_user_name = target
                    to_tg_display_name = target
                except:
                    pass
            else:
                to_user_id = row[0]
                to_user_name = row[1]
                to_tg_display_name = row[2] or row[1]
        
        # 显示名称优先使用 TG 显示名称
        display_name = to_tg_display_name or to_user_name
        
        if not to_user_id:
            conn.close()
            return _send(chat_id, f"❌ 未找到用户：{target}\n\n💡 请确认对方已绑定机器人，或直接使用 Emby 用户名")
        
        # 不能打劫自己
        if to_user_id == binding['emby_user_id']:
            conn.close()
            return _send(chat_id, "❌ 不能打劫自己")
        
        # 获取攻击者积分
        from_row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (binding['emby_user_id'],)).fetchone()
        from_points = from_row[0] if from_row else 0
        
        # 获取目标用户积分
        to_row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (to_user_id,)).fetchone()
        to_points = to_row[0] if to_row else 0
        
        # 🔥 检查攻击者积分是否低于保护阈值
        if from_points < protect_threshold:
            conn.close()
            return _send(chat_id, f"🛡️ 你的积分低于 {protect_threshold}，无法打劫他人")
        
        # 检查目标用户积分是否低于保护阈值
        if to_points < protect_threshold:
            conn.close()
            return _send(chat_id, f"🛡️ 对方积分低于 {protect_threshold}，处于保护状态")
        
        # 检查攻击者今日打劫次数
        today_rob_count = c.execute(
            "SELECT COUNT(*) FROM point_rob_logs WHERE from_user_id = ? AND date(created_at, 'localtime') = date('now', 'localtime')",
            (binding['emby_user_id'],)
        ).fetchone()[0]
        if today_rob_count >= max_per_day:
            conn.close()
            return _send(chat_id, f"❌ 今日打劫次数已达上限（{max_per_day}次）")
        
        # 检查目标用户今日被被打劫次数
        today_be_robbed_count = c.execute(
            "SELECT COUNT(*) FROM point_rob_logs WHERE to_user_id = ? AND date(created_at, 'localtime') = date('now', 'localtime')",
            (to_user_id,)
        ).fetchone()[0]
        if today_be_robbed_count >= max_be_robbed:
            conn.close()
            return _send(chat_id, f"❌ 对方今日已被打劫 {max_be_robbed} 次，休息一下吧")
        
        # 检查冷却时间
        last_rob = c.execute(
            "SELECT created_at FROM point_rob_logs WHERE from_user_id = ? AND to_user_id = ? ORDER BY created_at DESC LIMIT 1",
            (binding['emby_user_id'], to_user_id)
        ).fetchone()
        if last_rob:
            from datetime import datetime, timedelta
            try:
                last_time = datetime.fromisoformat(last_rob[0].replace('Z', '+00:00'))
                cooldown_end = last_time + timedelta(hours=cooldown_hours)
                if datetime.now(last_time.tzinfo) < cooldown_end:
                    remaining = int((cooldown_end - datetime.now(last_time.tzinfo)).total_seconds() / 60)
                    conn.close()
                    return _send(chat_id, f"❌ 冷却中，还需等待 {remaining} 分钟")
            except:
                pass
        
        # 随机打劫金额
        import random as rand_module
        rob_amount = rand_module.randint(rob_min, rob_max)
        
        # 判断是否成功
        is_success = rand_module.randint(1, 100) <= success_rate
        
        if is_success:
            # 打劫成功
            actual_amount = min(rob_amount, to_points)
            
            new_from_points = from_points + actual_amount
            new_to_points = to_points - actual_amount
            
            c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_from_points, binding['emby_user_id']))
            c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_to_points, to_user_id))
            
            c.execute("INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                     (binding['emby_user_id'], binding['emby_username'], f"打劫 {to_user_name}", actual_amount, new_from_points))
            c.execute("INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                     (to_user_id, to_user_name, f"被 {binding['emby_username']} 打劫", -actual_amount, new_to_points))
            c.execute("INSERT INTO point_rob_logs (from_user_id, from_user_name, to_user_id, to_user_name, amount, success, counter_amount) VALUES (?, ?, ?, ?, ?, 1, 0)",
                     (binding['emby_user_id'], binding['emby_username'], to_user_id, to_user_name, actual_amount))
            
            conn.commit()
            conn.close()
            
            return _send(chat_id, f"🎉 <b>打劫成功！</b>\n\n👤 从 <b>{display_name}</b> 身上抢到 <b>{actual_amount}</b> 积分\n💰 当前余额：<b>{new_from_points}</b> 积分")
        else:
            # 打劫失败，触发反杀
            counter_amount = rand_module.randint(counter_min, counter_max)
            actual_counter = min(counter_amount, from_points)
            
            new_from_points = from_points - actual_counter
            new_to_points = to_points + actual_counter
            
            c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_from_points, binding['emby_user_id']))
            c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_to_points, to_user_id))
            
            c.execute("INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                     (binding['emby_user_id'], binding['emby_username'], f"打劫 {to_user_name} 失败", -actual_counter, new_from_points))
            c.execute("INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                     (to_user_id, to_user_name, f"反杀 {binding['emby_username']}", actual_counter, new_to_points))
            c.execute("INSERT INTO point_rob_logs (from_user_id, from_user_name, to_user_id, to_user_name, amount, success, counter_amount) VALUES (?, ?, ?, ?, ?, 0, ?)",
                     (binding['emby_user_id'], binding['emby_username'], to_user_id, to_user_name, 0, actual_counter))
            
            conn.commit()
            conn.close()
            
            return _send(chat_id, f"😢 <b>打劫失败！</b>\n\n💥 被 <b>{display_name}</b> 反杀，损失 <b>{actual_counter}</b> 积分\n💰 当前余额：<b>{new_from_points}</b> 积分")
            
    except Exception as e:
        logger.error(f"[UserBot] 打劫失败: {e}")
        return _send(chat_id, f"❌ 打劫失败：{e}")

# PK命令代码片段 - 需要追加到 user_bot_service.py


def _handle_pk_accept_callback(chat_id, tg_user_id, invite_id, cq_id, msg_id):
    """处理PK接受回调"""
    binding = _get_binding(tg_user_id)
    if not binding:
        _tg_api("answerCallbackQuery", {"callback_query_id": cq_id, "text": "请先绑定账号", "show_alert": True})
        return
    
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        config = {r[0]: r[1] for r in c.execute("SELECT key, value FROM point_config").fetchall()}
        
        # 获取邀请（包含 TG 名称和消息ID）
        invite = c.execute(
            "SELECT id, challenger_id, challenger_name, challenger_tg_name, target_id, target_name, target_tg_name, points, chat_id, expires_at, message_id, command_message_id FROM pk_invitations WHERE id = ? AND status = 'pending'",
            (invite_id,)
        ).fetchone()
        
        if not invite:
            conn.close()
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id, "text": "邀请不存在或已处理", "show_alert": True})
            _edit(chat_id, msg_id, "❌ PK邀请已不存在或已处理")
            return
        
        # 检查是否是目标用户
        if invite[4] != binding['emby_user_id']:
            conn.close()
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id, "text": "这不是发给你的PK邀请", "show_alert": True})
            return
        
        # 检查是否过期
        from datetime import datetime
        try:
            expires_at = datetime.fromisoformat(invite[9])
            if datetime.now() > expires_at:
                c.execute("UPDATE pk_invitations SET status = 'expired' WHERE id = ?", (invite_id,))
                conn.commit()
                conn.close()
                _tg_api("answerCallbackQuery", {"callback_query_id": cq_id, "text": "PK邀请已过期", "show_alert": True})
                _edit(chat_id, msg_id, "❌ PK邀请已过期")
                return
        except:
            pass
        
        challenger_id = invite[1]
        challenger_name = invite[2]
        challenger_tg_name = invite[3] or challenger_name
        target_id = invite[4]
        target_name = invite[5]
        target_tg_name = invite[6] or target_name
        points = invite[7]
        original_chat_id = invite[8]
        invite_msg_id = invite[10]  # 邀请消息ID
        command_msg_id = invite[11]  # 命令消息ID
        
        # 🔥 重新检查积分范围（防止配置被修改后绕过）
        min_points = int(config.get('user_pk_min_points', 10))
        max_points = int(config.get('user_pk_max_points', 500))
        if points < min_points or points > max_points:
            c.execute("UPDATE pk_invitations SET status = 'cancelled' WHERE id = ?", (invite_id,))
            conn.commit()
            conn.close()
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id, "text": f"积分范围已变更，PK取消（需在 {min_points}-{max_points} 之间）", "show_alert": True})
            _edit(chat_id, msg_id, f"❌ 积分范围已变更，PK取消（需在 {min_points}-{max_points} 之间）")
            return
        
        # 获取双方积分
        challenger_points_row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (challenger_id,)).fetchone()
        challenger_points = challenger_points_row[0] if challenger_points_row else 0
        
        target_points_row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (target_id,)).fetchone()
        target_points = target_points_row[0] if target_points_row else 0
        
        # 再次检查双方积分
        if challenger_points < points or target_points < points:
            c.execute("UPDATE pk_invitations SET status = 'cancelled' WHERE id = ?", (invite_id,))
            conn.commit()
            conn.close()
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id, "text": "双方积分不足，PK取消", "show_alert": True})
            _edit(chat_id, msg_id, "❌ 双方积分不足，PK取消")
            return
        
        # 🔥 更新邀请状态为进行中
        c.execute("UPDATE pk_invitations SET status = 'processing' WHERE id = ?", (invite_id,))
        conn.commit()
        
        # 🔥 发送骰子动画
        _tg_api("answerCallbackQuery", {"callback_query_id": cq_id, "text": "🎲 掷骰子中..."})
        _edit(chat_id, msg_id, f"🎲 <b>PK开始！</b>\n\n{challenger_tg_name} vs {target_tg_name}\n💰 下注：{points} 积分\n\n🎲 正在掷骰子...")
        
        # 发送发起者的骰子
        dice1_resp = _tg_api("sendDice", {"chat_id": chat_id})
        import time
        time.sleep(2)  # 等待动画完成
        
        # 发送被挑战者的骰子
        dice2_resp = _tg_api("sendDice", {"chat_id": chat_id})
        time.sleep(2)
        
        # 获取骰子消息ID
        dice1_msg_id = dice1_resp.get("result", {}).get("message_id") if dice1_resp and dice1_resp.get("ok") else None
        dice2_msg_id = dice2_resp.get("result", {}).get("message_id") if dice2_resp and dice2_resp.get("ok") else None
        
        # 获取骰子结果（1-6）
        challenger_roll = dice1_resp.get("result", {}).get("dice", {}).get("value", 1) if dice1_resp and dice1_resp.get("ok") else 1
        target_roll = dice2_resp.get("result", {}).get("dice", {}).get("value", 1) if dice2_resp and dice2_resp.get("ok") else 1
        
        # 获取手续费率
        tax_rate = int(config.get('user_pk_tax', 5))
        
        # 判断胜负
        if challenger_roll > target_roll:
            winner_id = challenger_id
            winner_name = challenger_tg_name
            loser_id = target_id
            loser_name = target_tg_name
        elif target_roll > challenger_roll:
            winner_id = target_id
            winner_name = target_tg_name
            loser_id = challenger_id
            loser_name = challenger_tg_name
        else:
            # 平局
            c.execute("UPDATE pk_invitations SET status = 'completed' WHERE id = ?", (invite_id,))
            conn.commit()
            conn.close()
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id, "text": "平局！积分退还"})
            result_msg = f"⚖️ <b>平局！</b>\n\n{challenger_tg_name}({challenger_roll}点) vs {target_tg_name}({target_roll}点)\n\n积分退还，不扣手续费"
            _send(chat_id, result_msg)
            # 5秒后删除消息
            import time
            time.sleep(5)
            _tg_api("deleteMessage", {"chat_id": chat_id, "message_id": msg_id})
            return
        
        # 计算积分转移
        win_amount = points
        tax = int(win_amount * tax_rate / 100)
        actual_win = win_amount - tax
        
        # 🔥 再次检查积分是否足够（防止并发问题）
        challenger_points_now = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (challenger_id,)).fetchone()
        target_points_now = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (target_id,)).fetchone()
        challenger_balance = challenger_points_now[0] if challenger_points_now else 0
        target_balance = target_points_now[0] if target_points_now else 0
        
        # 🔥 检查输家是否有足够积分
        loser_balance = challenger_balance if loser_id == challenger_id else target_balance
        if loser_balance < points:
            c.execute("UPDATE pk_invitations SET status = 'cancelled' WHERE id = ?", (invite_id,))
            conn.commit()
            conn.close()
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id, "text": "积分不足，PK取消", "show_alert": True})
            _send(chat_id, f"❌ 积分不足，PK取消（输家积分：{loser_balance}，需要：{points}）")
            return
        
        # 更新积分
        c.execute("UPDATE users_meta SET points = points + ? WHERE user_id = ?", (actual_win, winner_id))
        c.execute("UPDATE users_meta SET points = points - ? WHERE user_id = ?", (points, loser_id))
        
        # 记录日志
        c.execute(
            "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, (SELECT points FROM users_meta WHERE user_id = ?))",
            (winner_id, winner_name, f"PK战胜 {loser_name}", actual_win, winner_id)
        )
        c.execute(
            "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, (SELECT points FROM users_meta WHERE user_id = ?))",
            (loser_id, loser_name, f"PK败给 {winner_name}", -points, loser_id)
        )
        
        # 记录PK日志
        c.execute(
            "INSERT INTO pk_logs (challenger_id, challenger_name, target_id, target_name, points, challenger_roll, target_roll, winner_id, winner_name, tax) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (challenger_id, challenger_name, target_id, target_name, points, challenger_roll, target_roll, winner_id, winner_name, tax)
        )
        
        # 更新邀请状态
        c.execute("UPDATE pk_invitations SET status = 'completed' WHERE id = ?", (invite_id,))
        
        conn.commit()
        conn.close()
        
        # 发送结果
        _tg_api("answerCallbackQuery", {"callback_query_id": cq_id, "text": f"{winner_name}获胜！"})
        result_msg = f"🎲 <b>PK结果</b>\n\n{challenger_tg_name}({challenger_roll}点) vs {target_tg_name}({target_roll}点)\n\n🎉 <b>{winner_name}</b> 获胜！\n💰 获得 <b>{actual_win}</b> 积分（扣{tax_rate}%手续费）"
        result_resp = _send(chat_id, result_msg)
        
        # 🔥 5秒后自动删除所有消息
        import time
        time.sleep(5)
        
        # 删除命令消息
        if command_msg_id:
            _tg_api("deleteMessage", {"chat_id": chat_id, "message_id": command_msg_id})
        
        # 删除邀请消息
        if invite_msg_id:
            _tg_api("deleteMessage", {"chat_id": chat_id, "message_id": invite_msg_id})
        
        # 删除骰子消息
        if dice1_msg_id:
            _tg_api("deleteMessage", {"chat_id": chat_id, "message_id": dice1_msg_id})
        if dice2_msg_id:
            _tg_api("deleteMessage", {"chat_id": chat_id, "message_id": dice2_msg_id})
        
        # 删除结果消息
        if result_resp and result_resp.get('ok'):
            result_msg_id = result_resp.get('result', {}).get('message_id')
            _tg_api("deleteMessage", {"chat_id": chat_id, "message_id": result_msg_id})
        
    except Exception as e:
        logger.error(f"[UserBot] PK接受回调失败: {e}")
        _tg_api("answerCallbackQuery", {"callback_query_id": cq_id, "text": f"处理失败: {e}", "show_alert": True})


def _handle_pk_reject_callback(chat_id, tg_user_id, invite_id, cq_id, msg_id):
    """处理PK拒绝回调"""
    binding = _get_binding(tg_user_id)
    if not binding:
        _tg_api("answerCallbackQuery", {"callback_query_id": cq_id, "text": "请先绑定账号", "show_alert": True})
        return
    
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        
        # 获取邀请（包含 TG 名称）
        invite = c.execute(
            "SELECT id, challenger_id, challenger_name, challenger_tg_name, target_id, target_name, target_tg_name, chat_id, message_id, command_message_id FROM pk_invitations WHERE id = ? AND status = 'pending'",
            (invite_id,)
        ).fetchone()
        
        if not invite:
            conn.close()
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id, "text": "邀请不存在或已处理", "show_alert": True})
            _edit(chat_id, msg_id, "❌ PK邀请已不存在或已处理")
            return
        
        # 检查是否是目标用户
        if invite[4] != binding['emby_user_id']:
            conn.close()
            _tg_api("answerCallbackQuery", {"callback_query_id": cq_id, "text": "这不是发给你的PK邀请", "show_alert": True})
            return
        
        challenger_name = invite[2]
        challenger_tg_name = invite[3] or challenger_name
        target_tg_name = invite[6] or invite[5]
        original_chat_id = invite[7]
        invite_msg_id = invite[8]
        command_msg_id = invite[9]
        
        # 更新状态
        c.execute("UPDATE pk_invitations SET status = 'rejected' WHERE id = ?", (invite_id,))
        conn.commit()
        conn.close()
        
        # 发送结果
        _tg_api("answerCallbackQuery", {"callback_query_id": cq_id, "text": "已拒绝PK邀请"})
        
        # 获取拒绝者的 TG 名称
        rejecter_tg_name = binding.get('tg_name') or binding['emby_username']
        
        # 编辑邀请消息
        _edit(chat_id, msg_id, f"❌ <b>{rejecter_tg_name}</b> 已拒绝 <b>{challenger_tg_name}</b> 的PK邀请")
        
        # 通知发起者
        if original_chat_id and str(original_chat_id) != str(chat_id):
            _send(original_chat_id, f"❌ <b>{rejecter_tg_name}</b> 拒绝了你的PK邀请")
        
        # 🔥 5秒后自动删除消息
        import time
        time.sleep(5)
        
        # 删除命令消息
        if command_msg_id:
            _tg_api("deleteMessage", {"chat_id": chat_id, "message_id": command_msg_id})
        
        # 删除邀请消息
        if invite_msg_id:
            _tg_api("deleteMessage", {"chat_id": chat_id, "message_id": invite_msg_id})
        
        # 删除拒绝消息（当前消息）
        _tg_api("deleteMessage", {"chat_id": chat_id, "message_id": msg_id})
        
    except Exception as e:
        logger.error(f"[UserBot] PK拒绝回调失败: {e}")
        _tg_api("answerCallbackQuery", {"callback_query_id": cq_id, "text": f"处理失败: {e}", "show_alert": True})

def cmd_pk_invite(chat_id, tg_user_id, text, is_group=False, entities=None, user_msg_id=None):
    """用户PK邀请"""
    binding = _get_binding(tg_user_id)
    if not binding:
        return _send(chat_id, "❌ 请先私聊机器人绑定账号")
    
    # 解析参数: /pk @用户 积分
    parts = text.split()
    if len(parts) < 3:
        return _send(chat_id, "💡 使用方法：/upk @用户 积分\n示例：/upk @张三 100\n\n💡 也可以直接使用 Emby 用户名")
    
    try:
        # 最后一个参数是积分
        try:
            points = int(parts[-1])
        except ValueError:
            return _send(chat_id, "❌ 下注积分必须是数字")
        
        # 用户名可能是多个部分
        target = ' '.join(parts[1:-1]).lstrip('@')
        
        if not target:
            return _send(chat_id, "❌ 请指定要PK的用户")
        
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        
        # 获取配置
        config = {r[0]: r[1] for r in c.execute("SELECT key, value FROM point_config").fetchall()}
        
        # 检查是否启用用户PK
        if int(config.get('enable_user_pk', 0)) == 0:
            conn.close()
            return _send(chat_id, "❌ 用户PK功能未开启")
        
        # 检查下注范围
        min_points = int(config.get('user_pk_min_points', 10))
        max_points = int(config.get('user_pk_max_points', 500))
        if points < min_points or points > max_points:
            conn.close()
            return _send(chat_id, f"❌ 下注积分需在 {min_points}-{max_points} 之间")
        
        # 查找目标用户（参考打劫功能的实现）
        mentioned_user_id = None
        if entities:
            for ent in entities:
                if ent.get("type") == "mention" or ent.get("type") == "text_mention":
                    if ent.get("type") == "text_mention" and ent.get("user"):
                        mentioned_user_id = str(ent["user"].get("id", ""))
                        break
                    elif ent.get("type") == "mention":
                        offset = ent.get("offset", 0)
                        length = ent.get("length", 0)
                        mentioned_username = text[offset:offset+length].lstrip('@')
                        c.execute("SELECT tg_user_id FROM tg_user_bindings WHERE tg_username = ?", (mentioned_username,))
                        row = c.fetchone()
                        if row:
                            mentioned_user_id = row[0]
                        break
        
        # 查找目标用户
        to_user_id = None
        to_user_name = None
        
        if mentioned_user_id:
            c.execute("SELECT emby_user_id, emby_username FROM tg_user_bindings WHERE tg_user_id = ?", (mentioned_user_id,))
            row = c.fetchone()
            if row:
                to_user_id = row[0]
                to_user_name = row[1]
        
        if not to_user_id:
            c.execute("SELECT emby_user_id, emby_username FROM tg_user_bindings WHERE tg_user_id = ? OR tg_username = ?", (target, target))
            row = c.fetchone()
            
            if not row:
                try:
                    from app.core.media_adapter import media_api
                    emby_users = media_api.get("/Users", timeout=5).json()
                    user_map = {u['Name']: u['Id'] for u in emby_users}
                    to_user_id = user_map.get(target)
                    to_user_name = target
                except:
                    pass
            else:
                to_user_id = row[0]
                to_user_name = row[1]
        
        if not to_user_id:
            conn.close()
            return _send(chat_id, f"❌ 未找到用户：{target}\n\n💡 请确认对方已绑定机器人，或直接使用 Emby 用户名")
        
        # 不能PK自己
        if to_user_id == binding['emby_user_id']:
            conn.close()
            return _send(chat_id, "❌ 不能PK自己")
        
        # 获取双方积分
        from_row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (binding['emby_user_id'],)).fetchone()
        from_points = from_row[0] if from_row else 0
        
        to_row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (to_user_id,)).fetchone()
        to_points = to_row[0] if to_row else 0
        
        if from_points < points:
            conn.close()
            return _send(chat_id, f"❌ 积分不足，当前积分：{from_points}")
        
        if to_points < points:
            conn.close()
            return _send(chat_id, f"❌ 对方积分不足（{to_points}），无法接受此PK")
        
        # 检查今日PK次数
        today_pk_count = c.execute(
            "SELECT COUNT(*) FROM pk_logs WHERE challenger_id = ? AND date(created_at, 'localtime') = date('now', 'localtime')",
            (binding['emby_user_id'],)
        ).fetchone()[0]
        max_per_day = int(config.get('user_pk_max_per_day', 5))
        if today_pk_count >= max_per_day:
            conn.close()
            return _send(chat_id, f"❌ 今日PK次数已达上限（{max_per_day}次）")
        
        # 清理过期邀请
        c.execute("UPDATE pk_invitations SET status = 'expired' WHERE expires_at < datetime('now', 'localtime') AND status = 'pending'")
        
        # 检查是否有待处理的邀请（已过期的已被标记为expired）
        pending = c.execute(
            "SELECT id FROM pk_invitations WHERE challenger_id = ? AND target_id = ? AND status = 'pending'",
            (binding['emby_user_id'], to_user_id)
        ).fetchone()
        if pending:
            conn.close()
            return _send(chat_id, "❌ 已有待处理的PK邀请，请等待对方回应")
        
        # 创建邀请
        from datetime import datetime, timedelta
        timeout_minutes = int(config.get('user_pk_timeout', 5))
        expires_at = datetime.now() + timedelta(minutes=timeout_minutes)
        
        # 获取 TG 名称
        target_binding = _get_binding_by_emby_id(to_user_id)
        target_tg_name = target_binding.get('tg_name') if target_binding else None
        challenger_tg_name = binding.get('tg_name') or binding['emby_username']
        
        c.execute(
            "INSERT INTO pk_invitations (challenger_id, challenger_name, challenger_tg_name, target_id, target_name, target_tg_name, points, chat_id, command_message_id, created_at, expires_at, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'), ?, 'pending')",
            (binding['emby_user_id'], binding['emby_username'], challenger_tg_name, to_user_id, to_user_name, target_tg_name, points, str(chat_id), str(user_msg_id) if user_msg_id else None, expires_at.isoformat())
        )
        invite_id = c.lastrowid
        
        conn.commit()
        conn.close()
        
        # 🔥 发送邀请通知（只在群聊发送，不私发）
        # 创建 Inline Keyboard 按钮
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ 接受PK", "callback_data": f"pk_accept:{invite_id}"},
                    {"text": "❌ 拒绝PK", "callback_data": f"pk_reject:{invite_id}"}
                ]
            ]
        }
        
        # 获取目标的 TG username 用于 @ 提及
        target_tg_username = target_binding.get('tg_username') if target_binding else None
        target_mention = f"@{target_tg_username}" if target_tg_username else (target_tg_name or to_user_name)
        
        # 在群聊中发送带按钮的消息
        invite_msg = f"🎯 <b>{challenger_tg_name}</b> 向 {target_mention} 发起PK挑战！\n\n💰 下注：<b>{points}</b> 积分\n⏰ 请在 <b>{timeout_minutes}</b> 分钟内回应\n\n💡 点击下方按钮选择接受或拒绝"
        invite_result = _send(chat_id, invite_msg, reply_markup=keyboard)
        
        # 记录邀请消息 ID
        if invite_result and invite_result.get('ok'):
            invite_msg_id = invite_result.get('result', {}).get('message_id')
            conn = sqlite3.connect(SYSTEM_DB_PATH)
            c = conn.cursor()
            c.execute("UPDATE pk_invitations SET message_id = ? WHERE id = ?", (str(invite_msg_id), invite_id))
            conn.commit()
            conn.close()
        
    except Exception as e:
        logger.error(f"[UserBot] PK邀请失败: {e}")
        return _send(chat_id, f"❌ PK邀请失败：{e}")

def cmd_pk_accept(chat_id, tg_user_id, text, is_group=False):
    """接受PK邀请"""
    binding = _get_binding(tg_user_id)
    if not binding:
        return _send(chat_id, "❌ 请先私聊机器人绑定账号")
    
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        config = {r[0]: r[1] for r in c.execute("SELECT key, value FROM point_config").fetchall()}
        
        # 清理过期邀请
        c.execute("UPDATE pk_invitations SET status = 'expired' WHERE expires_at < datetime('now', 'localtime') AND status = 'pending'")
        
        # 获取发给当前用户的最新待处理邀请
        invite = c.execute(
            "SELECT id, challenger_id, challenger_name, target_id, target_name, points, chat_id FROM pk_invitations WHERE target_id = ? AND status = 'pending' ORDER BY created_at DESC LIMIT 1",
            (binding['emby_user_id'],)
        ).fetchone()
        
        if not invite:
            conn.close()
            return _send(chat_id, "❌ 没有待处理的PK邀请")
        
        invite_id = invite[0]
        challenger_id = invite[1]
        challenger_name = invite[2]
        target_id = invite[3]
        target_name = invite[4]
        points = invite[5]
        original_chat_id = invite[6]
        
        # 🔥 重新检查积分范围（防止配置被修改后绕过）
        min_points = int(config.get('user_pk_min_points', 10))
        max_points = int(config.get('user_pk_max_points', 500))
        if points < min_points or points > max_points:
            c.execute("UPDATE pk_invitations SET status = 'cancelled' WHERE id = ?", (invite_id,))
            conn.commit()
            conn.close()
            return _send(chat_id, f"❌ 积分范围已变更，PK取消（需在 {min_points}-{max_points} 之间）")
        
        # 获取双方积分
        challenger_points_row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (challenger_id,)).fetchone()
        challenger_points = challenger_points_row[0] if challenger_points_row else 0
        
        target_points_row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (target_id,)).fetchone()
        target_points = target_points_row[0] if target_points_row else 0
        
        # 再次检查双方积分
        if challenger_points < points or target_points < points:
            c.execute("UPDATE pk_invitations SET status = 'cancelled' WHERE id = ?", (invite_id,))
            conn.commit()
            conn.close()
            return _send(chat_id, "❌ 双方积分不足，PK取消")
        
        # 掷骰子
        import random
        challenger_roll = random.randint(1, 100)
        target_roll = random.randint(1, 100)
        
        # 获取手续费率
        tax_rate = int(config.get('user_pk_tax', 5))
        
        # 判断胜负
        if challenger_roll > target_roll:
            winner_id = challenger_id
            winner_name = challenger_name
            loser_id = target_id
            loser_name = target_name
        elif target_roll > challenger_roll:
            winner_id = target_id
            winner_name = target_name
            loser_id = challenger_id
            loser_name = challenger_name
        else:
            # 平局
            c.execute("UPDATE pk_invitations SET status = 'completed' WHERE id = ?", (invite_id,))
            conn.commit()
            conn.close()
            # 通知双方
            _send(original_chat_id, f"⚖️ <b>平局！</b>\n\n{challenger_name}({challenger_roll}点) vs {target_name}({target_roll}点)\n\n积分退还，不扣手续费")
            return _send(chat_id, f"⚖️ <b>平局！</b>\n\n{challenger_name}({challenger_roll}点) vs {target_name}({target_roll}点)\n\n积分退还，不扣手续费")
        
        # 计算积分转移
        win_amount = points
        tax = int(win_amount * tax_rate / 100)
        actual_win = win_amount - tax
        
        # 🔥 再次检查积分是否足够（防止并发问题）
        challenger_points_now = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (challenger_id,)).fetchone()
        target_points_now = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (target_id,)).fetchone()
        challenger_balance = challenger_points_now[0] if challenger_points_now else 0
        target_balance = target_points_now[0] if target_points_now else 0
        
        # 🔥 检查输家是否有足够积分
        loser_balance = challenger_balance if loser_id == challenger_id else target_balance
        if loser_balance < points:
            c.execute("UPDATE pk_invitations SET status = 'cancelled' WHERE id = ?", (invite_id,))
            conn.commit()
            conn.close()
            return _send(chat_id, f"❌ 积分不足，PK取消（输家积分：{loser_balance}，需要：{points}）")
        
        # 更新积分
        c.execute("UPDATE users_meta SET points = points + ? WHERE user_id = ?", (actual_win, winner_id))
        c.execute("UPDATE users_meta SET points = points - ? WHERE user_id = ?", (points, loser_id))
        
        # 记录日志
        c.execute(
            "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, (SELECT points FROM users_meta WHERE user_id = ?))",
            (winner_id, winner_name, f"PK战胜 {loser_name}", actual_win, winner_id)
        )
        c.execute(
            "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, (SELECT points FROM users_meta WHERE user_id = ?))",
            (loser_id, loser_name, f"PK败给 {winner_name}", -points, loser_id)
        )
        
        # 记录PK日志
        c.execute(
            "INSERT INTO pk_logs (challenger_id, challenger_name, target_id, target_name, points, challenger_roll, target_roll, winner_id, winner_name, tax) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (challenger_id, challenger_name, target_id, target_name, points, challenger_roll, target_roll, winner_id, winner_name, tax)
        )
        
        # 更新邀请状态
        c.execute("UPDATE pk_invitations SET status = 'completed' WHERE id = ?", (invite_id,))
        
        conn.commit()
        conn.close()
        
        # 通知双方
        result_msg = f"🎲 <b>PK结果</b>\n\n{challenger_name}({challenger_roll}点) vs {target_name}({target_roll}点)\n\n🎉 <b>{winner_name}</b> 获胜！\n💰 获得 <b>{actual_win}</b> 积分（扣{tax_rate}%手续费）"
        _send(original_chat_id, result_msg)
        return _send(chat_id, result_msg)
        
    except Exception as e:
        logger.error(f"[UserBot] 接受PK失败: {e}")
        return _send(chat_id, f"❌ 接受PK失败：{e}")

def cmd_pk_reject(chat_id, tg_user_id, text, is_group=False):
    """拒绝PK邀请"""
    binding = _get_binding(tg_user_id)
    if not binding:
        return _send(chat_id, "❌ 请先私聊机器人绑定账号")
    
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        
        # 获取发给当前用户的最新待处理邀请
        invite = c.execute(
            "SELECT id, challenger_id, challenger_name, chat_id FROM pk_invitations WHERE target_id = ? AND status = 'pending' ORDER BY created_at DESC LIMIT 1",
            (binding['emby_user_id'],)
        ).fetchone()
        
        if not invite:
            conn.close()
            return _send(chat_id, "❌ 没有待处理的PK邀请")
        
        invite_id = invite[0]
        challenger_name = invite[2]
        original_chat_id = invite[3]
        
        # 更新状态
        c.execute("UPDATE pk_invitations SET status = 'rejected' WHERE id = ?", (invite_id,))
        conn.commit()
        conn.close()
        
        # 通知发起者
        if original_chat_id:
            _send(original_chat_id, f"❌ <b>{binding['emby_username']}</b> 拒绝了你的PK邀请")
        
        return _send(chat_id, f"✅ 已拒绝 <b>{challenger_name}</b> 的PK邀请")
        
    except Exception as e:
        logger.error(f"[UserBot] 拒绝PK失败: {e}")
        return _send(chat_id, f"❌ 拒绝PK失败：{e}")

def cmd_transfer(chat_id, tg_user_id, text, is_group=False, entities=None):
    """转赠积分"""
    binding = _get_binding(tg_user_id)
    if not binding:
        return _send(chat_id, "❌ 请先私聊机器人绑定账号")
    
    # 解析参数: /transfer @用户 积分 或 /转赠 用户名 积分
    parts = text.split()
    if len(parts) < 3:
        return _send(chat_id, "💡 使用方法：/transfer @用户 积分\n示例：/transfer @张三 100\n\n💡 也可以直接使用 Emby 用户名")
    
    try:
        # 最后一个参数是积分，前面的是用户名
        try:
            amount = int(parts[-1])
        except ValueError:
            return _send(chat_id, "❌ 积分必须是数字")
        
        # 用户名可能是多个部分（如 /转赠 小宇 乐 50）
        target = ' '.join(parts[1:-1]).lstrip('@')
        
        if not target:
            return _send(chat_id, "❌ 请指定要转赠的用户")
        
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        
        # 🔥 优先从 entities 获取被 @ 用户的真实 TG ID
        mentioned_user_id = None
        if entities:
            for ent in entities:
                if ent.get("type") == "mention" or ent.get("type") == "text_mention":
                    # text_mention 直接包含用户信息
                    if ent.get("type") == "text_mention" and ent.get("user"):
                        mentioned_user_id = str(ent["user"].get("id", ""))
                        break
                    # mention 需要从文本中提取用户名
                    elif ent.get("type") == "mention":
                        offset = ent.get("offset", 0)
                        length = ent.get("length", 0)
                        mentioned_username = text[offset:offset+length].lstrip('@')
                        # 通过用户名查找绑定的用户
                        c.execute("SELECT tg_user_id FROM tg_user_bindings WHERE tg_username = ?", (mentioned_username,))
                        row = c.fetchone()
                        if row:
                            mentioned_user_id = row[0]
                        break
        
        # 通过 TG 用户ID或用户名查找绑定的 Emby 用户
        to_user_id = None
        to_user_name = None
        
        if mentioned_user_id:
            # 通过被 @ 用户的 TG ID 查找
            c.execute("SELECT emby_user_id, emby_username FROM tg_user_bindings WHERE tg_user_id = ?", (mentioned_user_id,))
            row = c.fetchone()
            if row:
                to_user_id = row[0]
                to_user_name = row[1]
        
        if not to_user_id:
            # 尝试通过 TG 用户名或 Emby 用户名查找
            c.execute("SELECT emby_user_id, emby_username FROM tg_user_bindings WHERE tg_user_id = ? OR tg_username = ?", (target, target))
            row = c.fetchone()
            
            if not row:
                # 尝试通过 Emby 用户名查找
                try:
                    from app.core.media_adapter import media_api
                    emby_users = media_api.get("/Users", timeout=5).json()
                    user_map = {u['Name']: u['Id'] for u in emby_users}
                    to_user_id = user_map.get(target)
                    to_user_name = target
                except:
                    pass
            else:
                to_user_id = row[0]
                to_user_name = row[1]
        
        if not to_user_id:
            conn.close()
            return _send(chat_id, f"❌ 未找到用户：{target}\n\n💡 请确认对方已绑定机器人，或直接使用 Emby 用户名")
        
        # 获取配置
        config = {r[0]: r[1] for r in c.execute("SELECT key, value FROM point_config").fetchall()}
        
        # 检查是否启用转赠
        if int(config.get('enable_transfer', 0)) == 0:
            conn.close()
            return _send(chat_id, "❌ 积分转赠功能未开启")
        
        # 检查金额范围
        min_amount = int(config.get('transfer_min', 10))
        max_amount = int(config.get('transfer_max', 1000))
        if amount < min_amount or amount > max_amount:
            conn.close()
            return _send(chat_id, f"❌ 转赠金额需在 {min_amount}-{max_amount} 之间")
        
        # 不能转给自己
        if to_user_id == binding['emby_user_id']:
            conn.close()
            return _send(chat_id, "❌ 不能转赠给自己")
        
        # 获取发送者积分
        row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (binding['emby_user_id'],)).fetchone()
        from_points = row[0] if row else 0
        
        if from_points < amount:
            conn.close()
            return _send(chat_id, f"❌ 积分不足！当前积分: {from_points}")
        
        # 计算手续费
        fee_rate = int(config.get('transfer_fee_rate', 10))
        fee = int(amount * fee_rate / 100)
        actual_amount = amount - fee
        
        # 获取目标用户积分
        to_row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (to_user_id,)).fetchone()
        to_points = (to_row[0] or 0) + actual_amount if to_row else actual_amount
        
        # 获取目标用户的 TG 用户名和显示名称
        to_tg_row = c.execute("SELECT tg_username, tg_display_name FROM tg_user_bindings WHERE emby_user_id = ?", (to_user_id,)).fetchone()
        to_tg_username = to_tg_row[0] if to_tg_row and to_tg_row[0] else None
        to_tg_display_name = to_tg_row[1] if to_tg_row and to_tg_row[1] else None
        logger.info(f"[转赠] 目标用户 emby_user_id={to_user_id}, tg_username={to_tg_username}, tg_display_name={to_tg_display_name}, emby_name={to_user_name}")
        
        # 更新积分
        new_from_points = from_points - amount
        if to_row:
            c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (to_points, to_user_id))
        else:
            c.execute("INSERT INTO users_meta (user_id, points) VALUES (?, ?)", (to_user_id, to_points))
        
        c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_from_points, binding['emby_user_id']))
        
        # 记录日志
        c.execute("INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                 (binding['emby_user_id'], binding['emby_username'], f"转赠给 {to_user_name} (手续费{fee})", -amount, new_from_points))
        c.execute("INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                 (to_user_id, to_user_name, f"收到 {binding['emby_username']} 转赠", actual_amount, to_points))
        
        conn.commit(); conn.close()
        
        # 显示优先级：TG显示名称 > @username > Emby用户名
        if to_tg_display_name:
            display_name = to_tg_display_name
        elif to_tg_username:
            display_name = f"@{to_tg_username}"
        else:
            display_name = to_user_name
        
        result = _send(chat_id, f"✅ 转赠成功！\n\n💰 已转赠 <b>{actual_amount}</b> 积分给 <b>{display_name}</b>\n💸 手续费：{fee} 积分\n📊 余额：{new_from_points}")
        
        # 群聊中15秒后删除消息（转赠）
        if is_group and result:
            bot_msg_id = result.get("result", {}).get("message_id")
            if bot_msg_id:
                _delete_messages_later(chat_id, [bot_msg_id], 15)
        
        return result
        
    except ValueError:
        return _send(chat_id, "❌ 积分必须是数字")
    except Exception as e:
        logger.error(f"[UserBot] 转赠失败: {e}")
        return _send(chat_id, f"❌ 转赠失败：{str(e)}")

def cmd_redpacket(chat_id, tg_user_id, text, is_group=False, tg_name="", user_msg_id=None):
    """发红包"""
    binding = _get_binding(tg_user_id)
    if not binding:
        return _send(chat_id, "❌ 请先私聊机器人绑定账号")
    
    # 解析参数: /hb 总积分 数量 或 /红包 1000 10
    parts = text.split()
    if len(parts) < 3:
        return _send(chat_id, "💡 使用方法：/hb 总积分 数量\n示例：/hb 1000 10")
    
    try:
        total_amount = int(parts[1])
        total_count = int(parts[2])
        
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        config = {r[0]: r[1] for r in c.execute("SELECT key, value FROM point_config").fetchall()}
        
        # 检查是否启用红包
        if int(config.get('enable_red_packet', 0)) == 0:
            conn.close()
            return _send(chat_id, "❌ 积分红包功能未开启")
        
        # 检查是否仅管理员可发
        if int(config.get('red_packet_admin_only', 1)) == 1:
            # 检查是否是管理员 - 从 Emby API 获取用户信息
            try:
                user_info = media_api.get(f"/Users/{binding['emby_user_id']}", timeout=5).json()
                is_admin = user_info.get('Policy', {}).get('IsAdministrator', False)
            except:
                is_admin = False
            if not is_admin:
                conn.close()
                return _send(chat_id, "❌ 仅管理员可发红包")
        
        # 检查红包数量
        if total_count < 1 or total_count > 100:
            conn.close()
            return _send(chat_id, "❌ 红包数量需在 1-100 之间")
        
        # 检查积分
        row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (binding['emby_user_id'],)).fetchone()
        current_points = row[0] if row else 0
        
        if current_points < total_amount:
            conn.close()
            return _send(chat_id, f"❌ 积分不足！当前积分: {current_points}")
        
        # 计算过期时间
        expire_hours = int(config.get('red_packet_expire_hours', 24))
        expires_at = datetime.datetime.now() + datetime.timedelta(hours=expire_hours)
        
        # 扣除积分
        new_points = current_points - total_amount
        c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_points, binding['emby_user_id']))
        
        # 创建红包
        creator_display = tg_name or binding['emby_username']
        c.execute("INSERT INTO point_red_packets (total_amount, remain_amount, total_count, remain_count, creator_id, creator_name, chat_id, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                 (total_amount, total_amount, total_count, total_count, binding['emby_user_id'], creator_display, str(chat_id), expires_at))
        packet_id = c.lastrowid
        
        c.execute("INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                 (binding['emby_user_id'], binding['emby_username'], f"发放红包 #{packet_id}", -total_amount, new_points))
        
        conn.commit(); conn.close()
        
        result = _send(chat_id, f"🧧 <b>积分红包</b>\n\n"
                            f"🆔 红包ID：<b>#{packet_id}</b>\n"
                            f"💰 总金额：<b>{total_amount}</b> 积分\n"
                            f"📦 共 <b>{total_count}</b> 个\n"
                            f"⏰ {expire_hours}小时后过期\n\n"
                            f"💡 发送 /grab {packet_id} 抢红包")
        
        # 群聊中只删除用户命令消息，红包消息等抢完或过期后再删
        if is_group and user_msg_id:
            _delete_messages_later(chat_id, [user_msg_id], 15)
        
        return result
        
    except ValueError:
        return _send(chat_id, "❌ 参数必须是数字")
    except Exception as e:
        logger.error(f"[UserBot] 发红包失败: {e}")
        return _send(chat_id, f"❌ 发红包失败：{str(e)}")

def cmd_pk(chat_id, tg_user_id, text, is_group=False, tg_name="", user_msg_id=None):
    """PK掷骰子游戏 - 使用Telegram骰子动画"""
    binding = _get_binding(tg_user_id)
    if not binding:
        return _send(chat_id, "❌ 请先私聊机器人绑定账号")
    
    # 解析参数: /pk 积分 或 /PK 100
    parts = text.split()
    if len(parts) < 2:
        return _send(chat_id, "💡 使用方法：/pk 积分\n示例：/pk 100\n\n🎲 和机器人掷骰子比大小，赢了翻倍，输了扣分")
    
    try:
        amount = int(parts[1])
        
        if amount <= 0:
            return _send(chat_id, "❌ 积分必须大于0")
        
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        
        # 获取配置
        config = {r[0]: r[1] for r in c.execute("SELECT key, value FROM point_config").fetchall()}
        
        # 检查是否启用 PK
        if int(config.get('enable_pk', 0)) == 0:
            conn.close()
            return _send(chat_id, "❌ PK功能未开启")
        
        # 检查积分范围
        min_pk = int(config.get('pk_min', 10))
        max_pk = int(config.get('pk_max', 500))
        if amount < min_pk or amount > max_pk:
            conn.close()
            return _send(chat_id, f"❌ PK积分需在 {min_pk}-{max_pk} 之间")
        
        # 检查每日次数限制
        pk_max_per_day = int(config.get('pk_max_per_day', 10))
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        today_count = c.execute("SELECT COUNT(*) FROM point_logs WHERE user_id = ? AND action LIKE 'PK%' AND date(created_at) = ?",
                               (binding['emby_user_id'], today)).fetchone()[0]
        if today_count >= pk_max_per_day:
            conn.close()
            return _send(chat_id, f"❌ 今天PK次数已达上限 ({pk_max_per_day}次)\n\n💡 明天再来吧！")
        
        # 获取用户积分
        row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (binding['emby_user_id'],)).fetchone()
        current_points = row[0] if row else 0
        
        if current_points < amount:
            conn.close()
            return _send(chat_id, f"❌ 积分不足！当前积分: {current_points}")
        
        # 🔥 群聊中 @ 发起者
        display_name = tg_name or binding['emby_username']
        user_at = f"<a href='tg://user?id={tg_user_id}'>{display_name}</a>" if is_group else "你"
        
        # 发送提示消息
        start_msg = _send(chat_id, f"🎲 <b>PK 开始！</b>\n\n👤 {user_at} 发起挑战\n💰 赌注：<b>{amount}</b> 积分\n\n⏳ 正在掷骰子...")
        start_msg_id = start_msg.get("result", {}).get("message_id") if start_msg else None
        
        # 发送用户的骰子（使用 Telegram 骰子动画）
        user_dice_msg = _tg_api("sendDice", {"chat_id": chat_id, "emoji": "🎲"})
        if not user_dice_msg:
            conn.close()
            return _send(chat_id, "❌ 发送骰子失败，请稍后重试")
        user_dice_msg_id = user_dice_msg.get("result", {}).get("message_id")
        user_dice = user_dice_msg.get("result", {}).get("dice", {}).get("value", random.randint(1, 6))
        
        # 等待一下，让动画效果更好
        time.sleep(1.5)
        
        # 发送机器人的骰子
        bot_dice_msg = _tg_api("sendDice", {"chat_id": chat_id, "emoji": "🎲"})
        if not bot_dice_msg:
            conn.close()
            return _send(chat_id, "❌ 发送骰子失败，请稍后重试")
        bot_dice_msg_id = bot_dice_msg.get("result", {}).get("message_id")
        bot_dice = bot_dice_msg.get("result", {}).get("dice", {}).get("value", random.randint(1, 6))
        
        # 判断胜负
        if user_dice > bot_dice:
            # 用户赢
            new_points = current_points + amount
            result_text = f"🎉 <b>{user_at} 赢了！</b>\n\n🎲 掷出 <b>{user_dice}</b> 点，机器人掷出 <b>{bot_dice}</b> 点\n💰 获得 <b>+{amount}</b> 积分\n📊 余额：<b>{new_points}</b> 积分"
            log_action = f"PK赢了 (骰子{user_dice}vs{bot_dice})"
            log_amount = amount
        elif user_dice < bot_dice:
            # 用户输
            new_points = current_points - amount
            result_text = f"😢 <b>{user_at} 输了！</b>\n\n🎲 掷出 <b>{user_dice}</b> 点，机器人掷出 <b>{bot_dice}</b> 点\n💰 扣除 <b>-{amount}</b> 积分\n📊 余额：<b>{new_points}</b> 积分"
            log_action = f"PK输了 (骰子{user_dice}vs{bot_dice})"
            log_amount = -amount
        else:
            # 平局
            new_points = current_points
            result_text = f"🤝 <b>平局！</b>\n\n🎲 {user_at} 掷出 <b>{user_dice}</b> 点，机器人掷出 <b>{bot_dice}</b> 点\n💰 积分不变\n📊 余额：<b>{new_points}</b> 积分"
            log_action = f"PK平局 (骰子{user_dice}vs{bot_dice})"
            log_amount = 0
        
        # 更新积分
        c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_points, binding['emby_user_id']))
        
        # 记录日志
        c.execute("INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                 (binding['emby_user_id'], binding['emby_username'], log_action, log_amount, new_points))
        
        conn.commit(); conn.close()
        
        result = _send(chat_id, result_text)
        
        # 群聊中15秒后删除所有消息
        if is_group:
            msgs_to_delete = []
            if user_msg_id:
                msgs_to_delete.append(user_msg_id)
            if start_msg_id:
                msgs_to_delete.append(start_msg_id)
            if user_dice_msg_id:
                msgs_to_delete.append(user_dice_msg_id)
            if bot_dice_msg_id:
                msgs_to_delete.append(bot_dice_msg_id)
            if result:
                bot_msg_id = result.get("result", {}).get("message_id")
                if bot_msg_id:
                    msgs_to_delete.append(bot_msg_id)
            if msgs_to_delete:
                _delete_messages_later(chat_id, msgs_to_delete, 15)
        
        return result
        
    except ValueError:
        return _send(chat_id, "❌ 积分必须是数字")
    except Exception as e:
        logger.error(f"[UserBot] PK失败: {e}")
        return _send(chat_id, f"❌ PK失败：{str(e)}")

def cmd_grab(chat_id, tg_user_id, text, is_group=False, tg_name="", user_msg_id=None):
    """抢红包"""
    binding = _get_binding(tg_user_id)
    if not binding:
        return _send(chat_id, "❌ 请先私聊机器人绑定账号")
    
    # 解析参数: /grab 红包ID 或 /抢 123
    parts = text.split()
    if len(parts) < 2:
        return _send(chat_id, "💡 使用方法：/grab 红包ID\n示例：/grab 123")
    
    try:
        packet_id = int(parts[1])
        
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        
        # 🔥 使用 EXCLUSIVE 事务锁，防止并发抢红包
        c.execute("BEGIN EXCLUSIVE")
        
        # 获取红包信息
        packet_row = c.execute("SELECT id, total_amount, remain_amount, total_count, remain_count, creator_id, creator_name, expires_at FROM point_red_packets WHERE id = ?", (packet_id,)).fetchone()
        if not packet_row:
            conn.rollback()
            conn.close()
            return _send(chat_id, "❌ 红包不存在")
        
        _, total_amount, remain_amount, total_count, remain_count, creator_id, creator_name, expires_at = packet_row
        
        # 检查红包是否过期
        if expires_at and datetime.datetime.fromisoformat(str(expires_at)) < datetime.datetime.now():
            conn.rollback()
            conn.close()
            return _send(chat_id, "❌ 红包已过期")
        
        # 检查是否已抢完
        if remain_count <= 0 or remain_amount <= 0:
            conn.rollback()
            conn.close()
            return _send(chat_id, "❌ 红包已抢完")
        
        # 检查是否已抢过
        grab_row = c.execute("SELECT id FROM point_red_packet_logs WHERE packet_id = ? AND user_id = ?", (packet_id, binding['emby_user_id'])).fetchone()
        if grab_row:
            conn.rollback()
            conn.close()
            return _send(chat_id, "❌ 你已经抢过这个红包了")
        
        # 不能抢自己的红包
        if creator_id == binding['emby_user_id']:
            conn.rollback()
            conn.close()
            return _send(chat_id, "❌ 不能抢自己发的红包")
        
        # 二倍均值法计算金额
        if remain_count == 1:
            grab_amount = remain_amount
        else:
            avg = remain_amount / remain_count
            max_grab = min(int(avg * 2), remain_amount - remain_count + 1)
            grab_amount = random.randint(1, max_grab) if max_grab > 0 else 1
        
        # 更新红包
        new_remain_amount = remain_amount - grab_amount
        new_remain_count = remain_count - 1
        c.execute("UPDATE point_red_packets SET remain_amount = ?, remain_count = ? WHERE id = ?",
                 (new_remain_amount, new_remain_count, packet_id))
        
        # 记录抢红包
        grab_display_name = tg_name or binding['emby_username']
        c.execute("INSERT INTO point_red_packet_logs (packet_id, user_id, user_name, amount) VALUES (?, ?, ?, ?)",
                 (packet_id, binding['emby_user_id'], grab_display_name, grab_amount))
        
        # 更新用户积分
        user_row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (binding['emby_user_id'],)).fetchone()
        current_points = (user_row[0] or 0) + grab_amount if user_row else grab_amount
        if user_row:
            c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (current_points, binding['emby_user_id']))
        else:
            c.execute("INSERT INTO users_meta (user_id, points) VALUES (?, ?)", (binding['emby_user_id'], current_points))
        
        # 记录日志
        c.execute("INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                 (binding['emby_user_id'], binding['emby_username'], f"抢红包 #{packet_id}", grab_amount, current_points))
        
        # 🔥 检查是否是最后一个红包，发送抢完通知
        is_last_one = (new_remain_count == 0)
        if is_last_one:
            # 获取红包领取记录
            c.execute("SELECT user_name, amount FROM point_red_packet_logs WHERE packet_id = ? ORDER BY created_at", (packet_id,))
            grab_logs = c.fetchall()
            
            # 构建抢完通知消息
            notify_msg = f"🧧 <b>红包已抢完</b>\n\n"
            notify_msg += f"👤 <b>发红包</b>: {creator_name}\n"
            notify_msg += f"💰 <b>总金额</b>: {total_amount} 积分\n"
            notify_msg += f"📦 <b>总个数</b>: {total_count} 个\n\n"
            notify_msg += f"📋 <b>领取明细</b>:\n"
            for i, (uname, amt) in enumerate(grab_logs, 1):
                notify_msg += f"{i}. {uname}: {amt} 积分\n"
            
            # 获取红包的 chat_id
            chat_row = c.execute("SELECT chat_id FROM point_red_packets WHERE id = ?", (packet_id,)).fetchone()
            packet_chat_id = chat_row[0] if chat_row else None
            
            # 发送通知
            try:
                if packet_chat_id:
                    _send(packet_chat_id, notify_msg)
                    # 🔥 删除原始红包消息（抢完后）
                    msg_row = c.execute("SELECT message_id FROM point_red_packets WHERE id = ?", (packet_id,)).fetchone()
                    if msg_row and msg_row[0]:
                        _delete_messages_later(int(packet_chat_id), [msg_row[0]], 15)
                else:
                    # 发送到系统通知
                    from app.services.bot_service import bot
                    bot.send_message("sys_notify", notify_msg, platform="all")
            except Exception as e:
                logger.error(f"[红包] 发送抢完通知失败: {e}")
        
        conn.commit(); conn.close()
        
        result = _send(chat_id, f"🎉 <b>恭喜你！</b>\n\n"
                            f"🧧 抢到 <b>{grab_amount}</b> 积分\n"
                            f"💰 余额：<b>{current_points}</b> 积分")
        
        # 群聊中15秒后删除消息（抢红包）
        if is_group and result:
            bot_msg_id = result.get("result", {}).get("message_id")
            if bot_msg_id:
                msgs_to_delete = [bot_msg_id]
                if user_msg_id:
                    msgs_to_delete.append(user_msg_id)
                _delete_messages_later(chat_id, msgs_to_delete, 15)
        
        return result
        
    except ValueError:
        try: conn.rollback()
        except Exception: pass
        return _send(chat_id, "❌ 红包ID必须是数字")
    except Exception as e:
        logger.error(f"[UserBot] 抢红包失败: {e}")
        try: conn.rollback()
        except Exception: pass
        return _send(chat_id, f"❌ 抢红包失败：{str(e)}")

def cmd_lottery(chat_id, tg_user_id, text, is_group=False, user_msg_id=None):
    """彩票系统"""
    logger.info(f"[彩票] 命令调用: chat_id={chat_id}, text={text}")
    binding = _get_binding(tg_user_id)
    if not binding:
        return _send(chat_id, "❌ 请先私聊机器人绑定账号")
    
    parts = text.split()
    logger.info(f"[彩票] parts={parts}")
    
    # 获取配置
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    config = {r[0]: r[1] for r in c.execute("SELECT key, value FROM point_config").fetchall()}
    
    # 检查是否启用
    if int(config.get('enable_lottery', 0)) == 0:
        conn.close()
        return _send(chat_id, "❌ 彩票功能未开启")
    
    lottery_cost = int(config.get('lottery_cost', 10))
    lottery_max = int(config.get('lottery_max_per_day', 10))
    draw_hour = int(config.get('lottery_draw_hour', 20))
    
    # 获取今天的日期
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    
    # 查看我的彩票
    if len(parts) == 1 or parts[1] in ['my', '我的']:
        # 获取所有未过期的彩票（最近7天）
        tickets = c.execute("""SELECT numbers, cost, draw_date, created_at FROM lottery_tickets 
                             WHERE user_id = ? AND draw_date >= date('now', '-7 days') 
                             ORDER BY draw_date DESC, created_at DESC""",
                           (binding['emby_user_id'],)).fetchall()
        
        if not tickets:
            conn.close()
            return _send(chat_id, f"🎫 <b>我的彩票</b>\n\n最近没有购买彩票\n\n💡 发送 /lottery 1234 购买")
        
        msg = f"🎫 <b>我的彩票</b>\n\n"
        current_date = None
        for t in tickets:
            numbers, cost, draw_date, created_at = t
            
            # 检查该日期是否已开奖
            result_row = c.execute("SELECT winning_numbers FROM lottery_results WHERE draw_date = ? AND winning_numbers != ''", (draw_date,)).fetchone()
            
            if result_row:
                winning_numbers = result_row[0]
                # 检查是否中了幸运奖
                lucky_row = c.execute("SELECT 1 FROM lottery_winners WHERE user_id = ? AND draw_date = ? AND prize_level = 5", (binding['emby_user_id'], draw_date)).fetchone()
                if lucky_row:
                    status = "🍀 幸运奖"
                else:
                    # 计算中奖状态
                    match_count = sum(1 for i in range(4) if numbers[i] == winning_numbers[i])
                    if match_count == 4:
                        status = "🏆 一等奖"
                    elif match_count == 3:
                        status = "🥈 二等奖"
                    elif match_count == 2:
                        # 检查是否连续
                        if numbers[0:2] == winning_numbers[0:2] or numbers[1:3] == winning_numbers[1:3] or numbers[2:4] == winning_numbers[2:4]:
                            status = "🥉 三等奖"
                        else:
                            status = "🎁 安慰奖"
                    else:
                        status = "❌ 未中奖"
            else:
                status = "⏳ 未开奖"
            
            # 按日期分组显示
            if draw_date != current_date:
                if current_date:
                    msg += "\n"
                msg += f"📅 {draw_date}\n"
                current_date = draw_date
            
            msg += f"  {numbers} | {status}\n"
        
        conn.close()
        return _send(chat_id, msg)
    
    # 查看开奖结果
    if parts[1] in ['result', '结果', '开奖']:
        # 只查询已开奖的记录（winning_numbers 不为空）
        result = c.execute("SELECT draw_date, winning_numbers, total_pool FROM lottery_results WHERE winning_numbers != '' ORDER BY draw_date DESC LIMIT 1").fetchone()
        
        if not result:
            conn.close()
            return _send(chat_id, "🎫 <b>开奖结果</b>\n\n暂无开奖记录")
        
        draw_date, winning_numbers, total_pool = result
        
        # 查询中奖者
        winners = c.execute("SELECT username, prize_level, prize_amount FROM lottery_winners WHERE draw_date = ? ORDER BY prize_level",
                           (draw_date,)).fetchall()
        conn.close()
        
        msg = f"🎫 <b>开奖结果</b> ({draw_date})\n\n"
        msg += f"🎲 中奖号码: <b>{winning_numbers}</b>\n"
        msg += f"💰 奖池: {total_pool} 积分\n\n"
        
        if winners:
            msg += "🏆 中奖名单:\n"
            level_names = {1: "一等奖", 2: "二等奖", 3: "三等奖", 4: "安慰奖"}
            for w in winners:
                msg += f"• {w[0]} - {level_names.get(w[1], '未知')} {w[2]} 积分\n"
        else:
            msg += "😢 本期无人中奖，奖池累积到下期"
        
        return _send(chat_id, msg)
    
    # 查看当前奖池
    if parts[1] in ['pool', '奖池']:
        # 检查今天是否已开奖
        today_drawn = c.execute("SELECT winning_numbers FROM lottery_results WHERE draw_date = ? AND winning_numbers != ''", (today,)).fetchone()
        
        if today_drawn:
            # 今天已开奖，显示明天的奖池
            target_date = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
            draw_status = "✅ 已开奖"
            next_draw = f"明天 {draw_hour}:00"
        else:
            target_date = today
            draw_status = "⏳ 未开奖"
            next_draw = f"今天 {draw_hour}:00"
        
        # 获取目标日期奖池
        target_pool = c.execute("SELECT total_pool FROM lottery_results WHERE draw_date = ?", (target_date,)).fetchone()
        target_pool = target_pool[0] if target_pool else 0
        
        # 获取目标日期购票数
        target_tickets = c.execute("SELECT COUNT(*) FROM lottery_tickets WHERE draw_date = ?", (target_date,)).fetchone()[0]
        
        # 获取奖池分配比例
        ratio_1 = int(config.get('lottery_pool_ratio_1', 50))
        ratio_2 = int(config.get('lottery_pool_ratio_2', 20))
        ratio_3 = int(config.get('lottery_pool_ratio_3', 10))
        ratio_4 = int(config.get('lottery_pool_ratio_4', 5))
        
        conn.close()
        
        msg = f"🎰 <b>当前奖池</b> ({target_date})\n\n"
        msg += f"💰 奖池总额: <b>{target_pool}</b> 积分\n"
        msg += f"🎫 本期购票: <b>{target_tickets}</b> 张\n\n"
        msg += f"📋 本期状态: {draw_status}\n"
        msg += f"⏰ 下次开奖: {next_draw}\n\n"
        msg += f"📊 奖池分配:\n"
        msg += f"• 一等奖: {ratio_1}% = {int(target_pool * ratio_1 / 100)} 积分\n"
        msg += f"• 二等奖: {ratio_2}% = {int(target_pool * ratio_2 / 100)} 积分\n"
        msg += f"• 三等奖: {ratio_3}% = {int(target_pool * ratio_3 / 100)} 积分\n"
        msg += f"• 三等奖: {ratio_3}% = {int(target_pool * ratio_3 / 100)} 积分\n"
        msg += f"• 安慰奖: {ratio_4}% = {int(target_pool * ratio_4 / 100)} 积分\n"
        
        # 显示幸运奖信息
        lucky_count = int(config.get('lottery_lucky_count', 0))
        if lucky_count > 0:
            lucky_ratio = int(config.get('lottery_lucky_ratio', 5))
            msg += f"• 幸运奖: {lucky_ratio}% = {int(target_pool * lucky_ratio / 100)} 积分 (抽{lucky_count}人)\n"
        
        return _send(chat_id, msg)
    
    # 购买彩票
    numbers_list = []
    for p in parts[1:]:
        # 验证号码格式（4位数字）
        logger.info(f"[彩票] 验证号码: p={p}, len={len(p)}, isdigit={p.isdigit()}")
        if len(p) == 4 and p.isdigit():
            numbers_list.append(p)
    
    logger.info(f"[彩票] numbers_list={numbers_list}")
    
    if not numbers_list:
        logger.warning(f"[彩票] 号码验证失败，返回使用说明")
        return _send(chat_id, "💡 使用方法：\n/lottery 1234 - 购买一张彩票\n/lottery 1234 5678 - 购买多张\n/lottery my - 查看我的彩票\n/lottery result - 查看开奖结果\n\n🎫 彩票为4位数字(0000-9999)")
    
    logger.info(f"[彩票] 开始检查购买数量和积分")
    
    # 检查今天是否已开奖
    today_drawn = c.execute("SELECT winning_numbers FROM lottery_results WHERE draw_date = ? AND winning_numbers != ''", (today,)).fetchone()
    if today_drawn:
        # 今天已开奖，购票计入明天
        tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        draw_date_for_ticket = tomorrow
        draw_date_display = f"明天 ({tomorrow}) {draw_hour}:00"
    else:
        draw_date_for_ticket = today
        draw_date_display = f"今天 {draw_hour}:00"
    
    # 检查该开奖日期已购买数量
    today_count = c.execute("SELECT COUNT(*) FROM lottery_tickets WHERE user_id = ? AND draw_date = ?",
                           (binding['emby_user_id'], draw_date_for_ticket)).fetchone()[0]
    logger.info(f"[彩票] {draw_date_for_ticket} 已购买: {today_count}, 限购: {lottery_max}")
    
    if today_count + len(numbers_list) > lottery_max:
        conn.close()
        return _send(chat_id, f"❌ 每人每天最多购买 {lottery_max} 张彩票\n\n今天已购买: {today_count} 张")
    
    # 检查积分
    total_cost = len(numbers_list) * lottery_cost
    logger.info(f"[彩票] 彩票价格: {lottery_cost}, 数量: {len(numbers_list)}, 总花费: {total_cost}")
    row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (binding['emby_user_id'],)).fetchone()
    current_points = row[0] if row else 0
    logger.info(f"[彩票] 积分: {current_points}, 需要: {total_cost}")
    
    if current_points < total_cost:
        conn.close()
        logger.warning(f"[彩票] 积分不足")
        return _send(chat_id, f"❌ 积分不足！需要 {total_cost} 积分，当前: {current_points}")
    
    logger.info(f"[彩票] 积分检查通过，开始扣除积分")
    
    try:
        # 扣除积分
        new_points = current_points - total_cost
        c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_points, binding['emby_user_id']))
        logger.info(f"[彩票] 积分已扣除: {current_points} -> {new_points}")
        
        # 记录彩票
        for num in numbers_list:
            c.execute("INSERT INTO lottery_tickets (user_id, username, numbers, cost, draw_date) VALUES (?, ?, ?, ?, ?)",
                     (binding['emby_user_id'], binding['emby_username'], num, lottery_cost, draw_date_for_ticket))
        logger.info(f"[彩票] 彩票已记录，开奖日期: {draw_date_for_ticket}")
        
        # 更新奖池（计入对应日期）
        c.execute("INSERT OR IGNORE INTO lottery_results (draw_date, winning_numbers, total_pool) VALUES (?, '', 0)", (draw_date_for_ticket,))
        c.execute("UPDATE lottery_results SET total_pool = total_pool + ? WHERE draw_date = ?", (total_cost, draw_date_for_ticket))
        logger.info(f"[彩票] 奖池已更新")
        
        # 记录日志
        c.execute("INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                 (binding['emby_user_id'], binding['emby_username'], f"购买彩票 {len(numbers_list)}张", -total_cost, new_points))
        
        conn.commit(); conn.close()
        logger.info(f"[彩票] 购买成功，发送消息")
    except Exception as e:
        logger.error(f"[彩票] 数据库操作失败: {e}")
        conn.close()
        return _send(chat_id, f"❌ 购买失败：{str(e)}")
    
    msg = f"🎫 <b>购买成功！</b>\n\n"
    for i, num in enumerate(numbers_list, 1):
        msg += f"{i}. 号码: <b>{num}</b>\n"
    msg += f"\n💰 花费: {total_cost} 积分\n📊 余额: {new_points} 积分\n\n⏰ 开奖时间: {draw_date_display}"
    
    result = _send(chat_id, msg)
    
    # 群聊中15秒后删除（彩票）
    if is_group and result:
        bot_msg_id = result.get("result", {}).get("message_id")
        if bot_msg_id:
            msgs_to_delete = [bot_msg_id]
            if user_msg_id:
                msgs_to_delete.append(user_msg_id)
            _delete_messages_later(chat_id, msgs_to_delete, 15)
    
    return result

def cmd_scratch(chat_id, tg_user_id, text, is_group=False, tg_name="", user_msg_id=None):
    """刮刮乐"""
    try:
        return _cmd_scratch_impl(chat_id, tg_user_id, text, is_group, tg_name, user_msg_id)
    except Exception as e:
        logger.error(f"[刮刮乐] 命令执行失败: {e}")
        _send(chat_id, f"❌ 刮刮乐出错：{str(e)}")


def _cmd_scratch_impl(chat_id, tg_user_id, text, is_group=False, tg_name="", user_msg_id=None):
    """刮刮乐(内部实现)"""
    binding = _get_binding(tg_user_id)
    if not binding:
        return _send(chat_id, "❌ 请先私聊机器人绑定账号")
    
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    config = {r[0]: r[1] for r in c.execute("SELECT key, value FROM point_config").fetchall()}
    
    # 检查是否启用
    if int(config.get('enable_scratch', 0)) == 0:
        conn.close()
        return _send(chat_id, "❌ 刮刮乐功能未开启")
    
    scratch_cost = int(config.get('scratch_cost', 100))
    
    parts = text.split()
    
    # 查看当前刮刮乐
    if len(parts) == 1 or parts[1] in ['info', '当前']:
        card = c.execute("SELECT id, total_slots, filled_slots, price, status FROM scratch_cards WHERE status = 'active' ORDER BY created_at DESC LIMIT 1").fetchone()
        
        if not card:
            conn.close()
            return _send(chat_id, "🎰 <b>刮刮乐</b>\n\n当前没有进行中的刮刮乐\n\n💡 发送 /scratch 开始 创建新刮刮乐")
        
        card_id, total_slots, filled_slots, price, status = card
        
        # 获取格子状态
        slots = c.execute("SELECT slot_number, is_scratched, username FROM scratch_card_slots WHERE card_id = ? ORDER BY slot_number", (card_id,)).fetchall()
        
        # 🔥 显示可交互的按钮（已刮的显示✅，未刮的显示数字）
        msg = f"🎰 <b>刮刮乐 #{card_id}</b>\n\n"
        msg += f"💰 售价: {price} 积分/次\n"
        msg += f"📊 进度: {filled_slots}/{total_slots} 已刮\n\n"
        msg += f"⚠️ 点击下方按钮刮奖，每人只能刮一次！"
        
        # 构建按钮
        buttons = []
        for num, is_scratched, username in slots:
            if is_scratched:
                buttons.append({"text": f"{num}✅", "callback_data": f"scratch_done_{card_id}_{num}"})
            else:
                buttons.append({"text": str(num), "callback_data": f"scratch_{card_id}_{num}"})
        
        keyboard = []
        for i in range(0, len(buttons), 3):
            keyboard.append(buttons[i:i+3])
        
        conn.close()
        return _send(chat_id, msg, reply_markup={"inline_keyboard": keyboard})
    
    # 创建刮刮乐
    if parts[1] in ['start', '开始', 'create', '创建']:
        # 🔥 使用事务锁防止并发创建
        conn.execute("BEGIN EXCLUSIVE")
        
        # 检查是否已有活跃的刮刮乐
        existing = c.execute("SELECT id FROM scratch_cards WHERE status = 'active'").fetchone()
        if existing:
            conn.rollback()
            conn.close()
            return _send(chat_id, "❌ 已有进行中的刮刮乐，请先刮完再创建新的")
        
        # 检查仅管理员限制
        if int(config.get('scratch_admin_only', 0)) == 1:
            try:
                user_info = media_api.get(f"/Users/{binding['emby_user_id']}", timeout=5).json()
                is_admin = user_info.get('Policy', {}).get('IsAdministrator', False)
            except:
                is_admin = False
            if not is_admin:
                conn.rollback()
                conn.close()
                return _send(chat_id, "❌ 仅管理员可发起刮刮乐")
        
        total_slots = int(config.get('scratch_slots', 9))
        price = scratch_cost
        
        # 获取大奖概率
        big_prize_rate = float(config.get('scratch_big_prize_rate', 1)) / 100
        medium_prize_rate = float(config.get('scratch_medium_prize_rate', 10)) / 100
        
        # 生成奖品池
        prizes = []
        for i in range(total_slots):
            rand = random.random()
            if rand < big_prize_rate:
                prizes.append(random.choice([666, 888, 999]))
            elif rand < big_prize_rate + medium_prize_rate:
                prizes.append(random.randint(50, 200))
            elif rand < big_prize_rate + medium_prize_rate + 0.3:
                prizes.append(random.randint(10, 50))
            else:
                prizes.append(random.randint(1, 10))
        
        random.shuffle(prizes)
        
        # 创建刮刮乐
        display_name = tg_name or binding['emby_username']
        c.execute("INSERT INTO scratch_cards (total_slots, price, created_by, chat_id) VALUES (?, ?, ?, ?)",
                 (total_slots, price, display_name, str(chat_id)))
        card_id = c.lastrowid
        
        # 创建格子
        for i, prize in enumerate(prizes, 1):
            c.execute("INSERT INTO scratch_card_slots (card_id, slot_number, prize_amount) VALUES (?, ?, ?)",
                     (card_id, i, prize))
        
        conn.commit()
        
        # 构建消息
        msg = f"🎰 <b>刮刮乐开始！</b>\n\n"
        msg += f"👤 发起人: {display_name}\n"
        msg += f"💰 售价: {price} 积分/次\n"
        msg += f"🎯 共 {total_slots} 个格子\n\n"
        msg += f"🏆 大奖: 666/888/999 积分\n"
        msg += f"🎯 中奖: 50-200 积分\n"
        msg += f"🎁 小奖: 10-50 积分\n"
        msg += f"😅 保底: 1-10 积分\n\n"
        msg += f"⚠️ 每人只能刮一次！"
        
        # 构建按钮
        buttons = []
        for i in range(1, total_slots + 1):
            buttons.append({"text": str(i), "callback_data": f"scratch_{card_id}_{i}"})
        
        keyboard = []
        for i in range(0, len(buttons), 3):
            keyboard.append(buttons[i:i+3])
        
        conn.close()
        
        result = _send(chat_id, msg, reply_markup={"inline_keyboard": keyboard})
        
        # 保存消息ID
        if result and result.get('result', {}).get('message_id'):
            msg_id = result['result']['message_id']
            conn = sqlite3.connect(SYSTEM_DB_PATH)
            conn.execute("UPDATE scratch_cards SET message_id = ? WHERE id = ?", (msg_id, card_id))
            conn.commit()
            conn.close()
        
        # 群聊中只删除用户命令消息（不删除刮刮乐消息，等刮完后再删）
        if is_group and user_msg_id:
            _delete_messages_later(chat_id, [user_msg_id], 15)
        
        return result
    
    conn.close()
    return _send(chat_id, "💡 使用方法:\n/scratch - 查看当前刮刮乐\n/scratch 开始 - 创建新刮刮乐")


def _handle_scratch(chat_id, tg_user_id, card_id, slot_number, tg_name=""):
    """处理刮刮乐点击"""
    binding = _get_binding(tg_user_id)
    if not binding:
        return _send(chat_id, "❌ 请先私聊机器人绑定账号")
    
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    
    try:
        # 🔥 使用事务锁防止并发问题
        conn.execute("BEGIN EXCLUSIVE")
        
        # 检查刮刮乐是否存在
        card = c.execute("SELECT id, total_slots, filled_slots, price, status, chat_id, message_id FROM scratch_cards WHERE id = ?", (card_id,)).fetchone()
        if not card:
            conn.rollback()
            conn.close()
            return _send(chat_id, "❌ 刮刮乐不存在")
        
        _, total_slots, filled_slots, price, status, orig_chat_id, orig_msg_id = card
        
        if status != 'active':
            conn.rollback()
            conn.close()
            return _send(chat_id, "❌ 刮刮乐已结束")
        
        # 检查格子是否已被刮
        slot = c.execute("SELECT id, is_scratched, prize_amount FROM scratch_card_slots WHERE card_id = ? AND slot_number = ?", (card_id, slot_number)).fetchone()
        if not slot:
            conn.rollback()
            conn.close()
            return _send(chat_id, "❌ 格子不存在")
        
        if slot[1]:  # 已刮
            conn.rollback()
            conn.close()
            return _send(chat_id, "❌ 这个格子已经被刮过了")
        
        # 检查这个人是否已经刮过
        already_scratched = c.execute("SELECT id FROM scratch_card_slots WHERE card_id = ? AND user_id = ? AND is_scratched = 1", 
                                     (card_id, binding['emby_user_id'])).fetchone()
        if already_scratched:
            conn.rollback()
            conn.close()
            return _send(chat_id, "❌ 你已经刮过这个刮刮乐了，每人只能刮一次！")
        
        # 检查积分
        row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (binding['emby_user_id'],)).fetchone()
        current_points = row[0] if row else 0
        
        if current_points < price:
            conn.rollback()
            conn.close()
            return _send(chat_id, f"❌ 积分不足！需要 {price} 积分，当前: {current_points}")
        
        # 扣除积分
        new_points = current_points - price
        c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_points, binding['emby_user_id']))
        
        # 标记格子为已刮
        prize_amount = slot[2]
        display_name = tg_name or binding['emby_username']
        c.execute("UPDATE scratch_card_slots SET is_scratched = 1, user_id = ?, username = ?, scratched_at = CURRENT_TIMESTAMP WHERE id = ?",
                 (binding['emby_user_id'], display_name, slot[0]))
        
        # 更新已刮数量
        new_filled = filled_slots + 1
        c.execute("UPDATE scratch_cards SET filled_slots = ? WHERE id = ?", (new_filled, card_id))
        
        # 记录日志
        c.execute("INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                 (binding['emby_user_id'], binding['emby_username'], f"刮刮乐 #{card_id} 格子{slot_number}", -price, new_points))
        
        # 🔥 判断是否全部刮完
        is_last_one = new_filled >= total_slots
        # 不在这里更新状态，让 _scratch_draw_result 来处理
        
        conn.commit()
        conn.close()
        
        # 编辑原消息，更新按钮状态
        if orig_msg_id and orig_chat_id:
            _update_scratch_message(orig_chat_id, orig_msg_id, card_id)
        
        if is_last_one:
            # 全部刮完，开奖！
            _scratch_draw_result(chat_id, card_id)
        else:
            # 未刮完，显示通知
            _send(chat_id, f"✅ <b>{display_name} 刮开了格子 {slot_number}</b>\n\n📊 进度: {new_filled}/{total_slots} 已刮\n💳 余额: {new_points} 积分\n\n⏳ 等待其他 {total_slots - new_filled} 个格子被刮开...")
        
    except Exception as e:
        logger.error(f"[刮刮乐] 刮奖失败: {e}")
        try: conn.rollback()
        except Exception: pass
        conn.close()
        _send(chat_id, f"❌ 刮奖失败：{str(e)}")


def _update_scratch_message(chat_id, msg_id, card_id):
    """更新刮刮乐消息的按钮状态"""
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        # 获取刮刮乐状态
        card = conn.execute("SELECT status FROM scratch_cards WHERE id = ?", (card_id,)).fetchone()
        status = card[0] if card else 'completed'
        
        slots = conn.execute("SELECT slot_number, is_scratched, username FROM scratch_card_slots WHERE card_id = ? ORDER BY slot_number", (card_id,)).fetchall()
        conn.close()
        
        # 构建按钮（已刮的显示 ✅，未刮的显示数字）
        buttons = []
        for num, is_scratched, username in slots:
            if is_scratched or status == 'completed':
                buttons.append({"text": f"{num}✅", "callback_data": f"scratch_done_{card_id}_{num}"})
            else:
                buttons.append({"text": str(num), "callback_data": f"scratch_{card_id}_{num}"})
        
        keyboard = []
        for i in range(0, len(buttons), 3):
            keyboard.append(buttons[i:i+3])
        
        _tg_api("editMessageReplyMarkup", {
            "chat_id": chat_id,
            "message_id": msg_id,
            "reply_markup": {"inline_keyboard": keyboard}
        })
    except Exception as e:
        logger.error(f"[刮刮乐] 更新消息失败: {e}")


def _scratch_draw_result(chat_id, card_id):
    """刮刮乐开奖"""
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    
    try:
        # 🔥 使用事务锁，检查状态
        conn.execute("BEGIN EXCLUSIVE")
        
        # 检查是否已经开奖
        card = c.execute("SELECT status FROM scratch_cards WHERE id = ?", (card_id,)).fetchone()
        if not card or card[0] != 'active':
            conn.rollback()
            conn.close()
            logger.info(f"[刮刮乐] #{card_id} 已经开奖或不存在，跳过")
            return
        
        # 更新状态
        c.execute("UPDATE scratch_cards SET status = 'completed' WHERE id = ?", (card_id,))
        conn.commit()
        
        # 获取所有刮奖记录
        slots = c.execute("SELECT slot_number, prize_amount, user_id, username FROM scratch_card_slots WHERE card_id = ? AND is_scratched = 1 ORDER BY slot_number", (card_id,)).fetchall()
        
        if not slots:
            conn.close()
            logger.warning(f"[刮刮乐] #{card_id} 没有人刮奖")
            return
        
        summary = f"🎊 <b>刮刮乐 #{card_id} 开奖！</b>\n\n"
        summary += f"📋 中奖明细:\n"
        total_prize = 0
        
        for num, prize, user_id, uname in slots:
            # 发放奖励
            if user_id:
                row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (user_id,)).fetchone()
                if row:
                    new_points = row[0] + prize
                    c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_points, user_id))
                    # 更新日志
                    display_name = uname or f"用户{user_id}"
                    c.execute("INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                             (user_id, display_name, f"刮刮乐 #{card_id} 中奖", prize, new_points))
            
            if prize >= 666:
                emoji = "🏆"
            elif prize >= 50:
                emoji = "🎉"
            elif prize >= 10:
                emoji = "🎁"
            else:
                emoji = "😅"
            
            summary += f"{num}. {emoji} {uname or '未知'}: {prize} 积分\n"
            total_prize += prize
        
        summary += f"\n💰 总发放: {total_prize} 积分"
        
        conn.commit()
        
        # 🔥 刮刮乐结束，删除刮刮乐消息（群聊）
        card_info = c.execute("SELECT chat_id, message_id FROM scratch_cards WHERE id = ?", (card_id,)).fetchone()
        if card_info:
            orig_chat_id, orig_msg_id = card_info
            if orig_chat_id and orig_msg_id:
                # 延迟15秒删除，让玩家看到结果
                _delete_messages_later(int(orig_chat_id), [orig_msg_id], 15)
        
        conn.close()
        
        _send(chat_id, summary)
        
    except Exception as e:
        logger.error(f"[刮刮乐] 开奖失败: {e}")
        try: conn.rollback()
        except Exception: pass
        conn.close()


def cmd_shop(chat_id, tg_user_id, msg_id=None):
    binding = _get_binding(tg_user_id)
    if not binding:
        _send(chat_id, "❌ 请先绑定账号：/bind 用户名")
        return
    
    # 检查 Emby 账号是否仍然有效
    if not _check_emby_account(binding):
        _unbind_user(tg_user_id)
        _send(chat_id, "⚠️ 你的 Emby 账号已被删除，绑定已自动解除。请联系管理员。", 
              reply_markup=_main_menu_keyboard(None))
        return
    
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        row = conn.execute("SELECT points FROM users_meta WHERE user_id = ?", (binding['emby_user_id'],)).fetchone()
        pts = row[0] if row and row[0] else 0
        items_row = conn.execute("SELECT value FROM point_config WHERE key = 'store_items'").fetchone()
        conn.close()
        items = json.loads(items_row[0]) if items_row and items_row[0] else []
        if not items:
            _send(chat_id, "🏪 积分商城暂无商品")
            return
        msg = f"🏪 <b>积分商城</b>\n💰 你的余额：<b>{pts}</b> 积分\n\n"
        keyboard = {"inline_keyboard": []}
        for item in items:
            # 随机延期商品显示特殊信息
            if item.get("type") == "random_renew":
                base_days = item.get("base_days", 30)
                random_min = item.get("random_min", -10)
                random_max = item.get("random_max", 60)
                min_days = base_days + random_min
                max_days = base_days + random_max
                msg += f"🎲 <b>{item['name']}</b> — {item['cost']} 积分\n  {item.get('desc', '')}\n  ⚡ 基础{base_days}天 + 随机{random_min}~{random_max}天 ({min_days}~{max_days}天)\n\n"
            else:
                msg += f"• <b>{item['name']}</b> — {item['cost']} 积分\n  {item.get('desc', '')}\n\n"
            keyboard["inline_keyboard"].append([{"text": f"🛒 {item['name']} ({item['cost']}积分)", "callback_data": f"ub_redeem_{item['id']}"}])
        _reply(chat_id, msg.strip(), reply_markup=keyboard, msg_id=msg_id)
    except Exception as e:
        _reply(chat_id, f"❌ 商城加载失败：{e}", msg_id=msg_id)


def cmd_redeem_callback(chat_id, tg_user_id, item_id, cq_id):
    _tg_api("answerCallbackQuery", {"callback_query_id": cq_id})
    binding = _get_binding(tg_user_id)
    if not binding:
        _send(chat_id, "❌ 未绑定账号")
        return
    
    # 检查 Emby 账号是否仍然有效
    if not _check_emby_account(binding):
        _unbind_user(tg_user_id)
        _send(chat_id, "⚠️ 你的 Emby 账号已被删除，绑定已自动解除。请联系管理员。", 
              reply_markup=_main_menu_keyboard(None))
        return
    
    uid = binding['emby_user_id']
    uname = binding['emby_username']
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)  # 🔥 修复：使用系统数据库
        c = conn.cursor()
        items_row = c.execute("SELECT value FROM point_config WHERE key = 'store_items'").fetchone()
        items = json.loads(items_row[0]) if items_row else []
        target = next((x for x in items if x.get("id") == item_id), None)
        if not target:
            conn.close()
            _send(chat_id, "❌ 商品不存在")
            return
        cost = int(target.get('cost', 0))
        row = c.execute("SELECT points, expire_date FROM users_meta WHERE user_id = ?", (uid,)).fetchone()
        pts = row[0] if row else 0
        exp = row[1] if row else None
        
        # 🔥 先检查永久账号（在扣积分之前）
        if target.get("type") in ["renew", "random_renew"]:
            is_permanent = not exp or exp == "" or "2099" in exp or "3000" in exp or "永久" in exp
            if is_permanent:
                conn.close()
                _send(chat_id, "❌ 你的账号为永久有效，无需续期！")
                return
        
        if pts < cost:
            conn.close()
            _send(chat_id, f"❌ 余额不足！需要 {cost} 积分，当前 {pts}")
            return

        new_pts = pts - cost
        c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_pts, uid))
        result_msg = ""
        actual_days = 0
        
        if target.get("type") == "renew":
            today = datetime.date.today()
            try:
                exp_date = datetime.datetime.strptime(exp, "%Y-%m-%d").date() if exp else today
                if exp_date < today: exp_date = today
            except: exp_date = today
            days = int(target.get("val", 30))
            new_exp = (exp_date + datetime.timedelta(days=days)).strftime("%Y-%m-%d")
            c.execute("UPDATE users_meta SET expire_date = ? WHERE user_id = ?", (new_exp, uid))
            try: media_api.post(f"/Users/{uid}/Policy", json={"IsDisabled": False}, timeout=3)
            except Exception: pass
            result_msg = f"📅 账号已续期至 {new_exp}"
            
        elif target.get("type") == "random_renew":
            # 🎲 随机定价延期（永久账号已在前面统一检查）
            
            base_days = int(target.get("base_days", 30))
            random_min = int(target.get("random_min", -10))
            random_max = int(target.get("random_max", 60))
            
            # 计算随机天数（简化的概率调节）
            luck_mode = target.get("luck_mode", "normal")
            luck_value = int(target.get("luck_value", 50))
            
            if luck_mode == "lucky":
                import random as rand_module
                times = max(1, int(luck_value / 25))
                random_bonus = max(rand_module.randint(random_min, random_max) for _ in range(times))
            elif luck_mode == "unlucky":
                import random as rand_module
                times = max(1, int(luck_value / 25))
                random_bonus = min(rand_module.randint(random_min, random_max) for _ in range(times))
            else:
                random_bonus = random.randint(random_min, random_max)
            
            actual_days = base_days + random_bonus
            actual_days = max(1, actual_days)
            
            today = datetime.date.today()
            try:
                exp_date = datetime.datetime.strptime(exp, "%Y-%m-%d").date() if exp else today
                if exp_date < today: exp_date = today
            except: exp_date = today
            
            new_exp = (exp_date + datetime.timedelta(days=actual_days)).strftime("%Y-%m-%d")
            c.execute("UPDATE users_meta SET expire_date = ? WHERE user_id = ?", (new_exp, uid))
            try: media_api.post(f"/Users/{uid}/Policy", json={"IsDisabled": False}, timeout=3)
            except Exception: pass
            
            bonus_text = f"+{random_bonus}" if random_bonus >= 0 else str(random_bonus)
            
            # 🔥 判断盲盒结果类型
            range_span = random_max - random_min
            if random_bonus >= random_max - range_span * 0.1:
                result_emoji = "👑✨"
                luck_text = "天选之人！欧皇降临！"
            elif random_bonus >= random_max - range_span * 0.3:
                result_emoji = "🍀🎉"
                luck_text = "运气不错！"
            elif random_bonus >= random_min + range_span * 0.3:
                result_emoji = "✨"
                luck_text = "还算可以"
            elif random_bonus >= random_min:
                result_emoji = "📦"
                luck_text = "中规中矩"
            elif random_bonus >= random_min - range_span * 0.2:
                result_emoji = "😅"
                luck_text = "稍微有点亏"
            else:
                result_emoji = "🌧️"
                luck_text = "运气不佳..."
            
            result_msg = f"🎲 {result_emoji} {luck_text}\n随机结果：基础{base_days}天 {bonus_text} = {actual_days}天\n📅 账号已续期至 {new_exp}"
        else:
            result_msg = "⚠️ 此商品需人工发货，请联系管理员"

        # 记录日志
        if target.get("type") == "random_renew":
            bonus_text = f"+{actual_days - base_days}" if (actual_days - base_days) >= 0 else str(actual_days - base_days)
            log_desc = f"🎲商城兑换: {target['name']} (基础{base_days}天{bonus_text}={actual_days}天)"
        else:
            log_desc = f"商城兑换: {target['name']}"
        
        c.execute("INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                  (uid, uname, log_desc, -cost, new_pts))
        conn.commit()
        conn.close()
        
        _send(chat_id, f"✅ <b>兑换成功！</b>\n\n🛒 {target['name']}\n💰 花费 {cost} 积分，余额 {new_pts}\n{result_msg}")

        try:
            from app.services.bot_service import bot
            from app.core.database import add_sys_notification
            notify_msg = f"🎁 <b>积分商城兑换</b>\n\n👤 {uname}\n🛒 {target['name']}\n💰 {cost} 积分\n📱 来源：TG 用户机器人"
            if target.get("type") == "random_renew":
                notify_msg += f"\n🎲 随机结果：{actual_days}天"
            bot.send_message("sys_notify", notify_msg, platform="all")
            add_sys_notification("points", f"商城订单: {target['name']}", f"用户 {uname} 通过TG机器人兑换", "/points")
        except Exception: pass
    except Exception as e:
        _send(chat_id, f"❌ 兑换失败：{e}")


def cmd_request(chat_id, tg_user_id, args):
    binding = _get_binding(tg_user_id)
    if not binding:
        _send(chat_id, "❌ 请先绑定账号：/bind 用户名")
        return
    
    # 检查 Emby 账号是否仍然有效
    if not _check_emby_account(binding):
        _unbind_user(tg_user_id)
        _send(chat_id, "⚠️ 你的 Emby 账号已被删除，绑定已自动解除。请联系管理员。", 
              reply_markup=_main_menu_keyboard(None))
        return
    
    if not args:
        _send(chat_id, "🔍 请输入要搜索的影视名称：/request 剧名")
        return
    tmdb_key = cfg.get("tmdb_api_key")
    if not tmdb_key:
        _send(chat_id, "❌ 服务器未配置 TMDB，求片功能不可用")
        return
    try:
        proxies = get_safe_proxies()
        res = requests.get(f"https://api.themoviedb.org/3/search/multi?api_key={tmdb_key}&query={args}&language=zh-CN&page=1", proxies=proxies, timeout=10)
        results = [r for r in res.json().get("results", []) if r.get("media_type") in ["movie", "tv"]][:5]
        if not results:
            _send(chat_id, f"📭 未找到与 <b>{args}</b> 相关的影视")
            return
        msg = f"🔍 <b>搜索结果：{args}</b>\n\n"
        keyboard = {"inline_keyboard": []}
        for r in results:
            name = r.get("title") or r.get("name", "未知")
            year = (r.get("release_date") or r.get("first_air_date") or "")[:4]
            mtype = "🎬" if r["media_type"] == "movie" else "📺"
            msg += f"{mtype} {name} ({year})\n"
            keyboard["inline_keyboard"].append([{"text": f"{mtype} {name} ({year})", "callback_data": f"ub_req_{r['media_type']}_{r['id']}"}])
        _send(chat_id, msg + "\n点击下方按钮提交求片：", reply_markup=keyboard)
    except Exception as e:
        _send(chat_id, f"❌ 搜索失败：{e}")


def cmd_request_callback(chat_id, tg_user_id, media_type, tmdb_id, cq_id):
    _tg_api("answerCallbackQuery", {"callback_query_id": cq_id})
    binding = _get_binding(tg_user_id)
    if not binding:
        _send(chat_id, "❌ 未绑定账号")
        return

    # 电视剧需要先选季
    if media_type == "tv":
        try:
            tmdb_key = cfg.get("tmdb_api_key")
            proxies = get_safe_proxies()
            detail = requests.get(f"https://api.themoviedb.org/3/tv/{tmdb_id}?api_key={tmdb_key}&language=zh-CN", proxies=proxies, timeout=10).json()
            title = detail.get("name", "未知")
            seasons = detail.get("seasons", [])
            real_seasons = [s for s in seasons if s.get("season_number", 0) > 0]
            if len(real_seasons) <= 1:
                # 只有一季，直接提交第1季
                _submit_request(chat_id, tg_user_id, "tv", tmdb_id, 1)
            else:
                msg = f"📺 <b>{title}</b>\n\n请选择要求片的季数："
                keyboard = {"inline_keyboard": []}
                row = []
                for s in real_seasons:
                    sn = s.get("season_number", 1)
                    row.append({"text": f"第 {sn} 季", "callback_data": f"ub_reqsn_{tmdb_id}_{sn}"})
                    if len(row) == 3:
                        keyboard["inline_keyboard"].append(row)
                        row = []
                if row:
                    keyboard["inline_keyboard"].append(row)
                keyboard["inline_keyboard"].append([{"text": "🔙 返回", "callback_data": "ub_back_menu"}])
                _send(chat_id, msg, reply_markup=keyboard)
        except Exception as e:
            _send(chat_id, f"❌ 获取季数失败：{e}")
        return

    # 电影直接提交
    _submit_request(chat_id, tg_user_id, "movie", tmdb_id, 0)


def _submit_request(chat_id, tg_user_id, media_type, tmdb_id, season):
    """实际提交求片逻辑"""
    binding = _get_binding(tg_user_id)
    if not binding: return
    
    # 检查 Emby 账号是否仍然有效
    if not _check_emby_account(binding):
        _unbind_user(tg_user_id)
        _send(chat_id, "⚠️ 你的 Emby 账号已被删除，绑定已自动解除。请联系管理员。", 
              reply_markup=_main_menu_keyboard(None))
        return
    
    uid = binding['emby_user_id']
    uname = binding['emby_username']
    try:
        tmdb_key = cfg.get("tmdb_api_key")
        proxies = get_safe_proxies()
        mtype = "movie" if media_type == "movie" else "tv"
        detail = requests.get(f"https://api.themoviedb.org/3/{mtype}/{tmdb_id}?api_key={tmdb_key}&language=zh-CN", proxies=proxies, timeout=10).json()
        title = detail.get("title") or detail.get("name", "未知")
        year = (detail.get("release_date") or detail.get("first_air_date") or "")[:4]
        poster_path = detail.get("poster_path", "")
        poster = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else ""

        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        
        # 🔥 求片积分配置
        enable_cost_row = c.execute("SELECT value FROM point_config WHERE key = 'enable_req_cost'").fetchone()
        global_enable_cost = (enable_cost_row[0] == "1") if enable_cost_row else False
        
        # 🔥 获取用户求片权限
        c.execute("SELECT req_free, req_free_count FROM users_meta WHERE user_id = ?", (uid,))
        user_req_row = c.fetchone()
        user_req_free = user_req_row[0] if user_req_row else 0  # 0=跟随全局, 1=免费, 2=付费
        user_req_free_count = user_req_row[1] if user_req_row else -1  # -1=无限次
        
        # 🔥 判断用户是否需要付费
        # user_req_free: 0=跟随全局, 1=免费, 2=付费
        need_cost = False
        if user_req_free == 1:
            # 用户设置为免费
            need_cost = False
            # 检查免费次数
            if user_req_free_count == 0:
                conn.close()
                _send(chat_id, "❌ 您的免费求片次数已用完，请联系管理员。")
                return
        elif user_req_free == 2:
            # 用户设置为付费
            need_cost = True
        else:
            # 跟随全局设置
            need_cost = global_enable_cost
        
        req_cost = 0
        current_pts = 0
        
        if need_cost:
            cost_row = c.execute("SELECT value FROM point_config WHERE key = 'req_cost'").fetchone()
            req_cost = int(cost_row[0]) if cost_row else 50
            pt_row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (uid,)).fetchone()
            current_pts = pt_row[0] if pt_row else 0
            if current_pts < req_cost:
                conn.close()
                _send(chat_id, f"❌ 积分不足！求片需消耗 {req_cost} 积分，当前仅有 {current_pts} 积分。")
                return

        existing = c.execute("SELECT status FROM media_requests WHERE tmdb_id = ? AND season = ?", (int(tmdb_id), season)).fetchone()
        if existing:
            conn.close()
            status_map = {0: "处理中", 1: "下载中", 2: "已完成", 3: "已拒绝", 4: "待手动处理"}
            _send(chat_id, f"❌ 该资源工单已存在，当前状态：{status_map.get(existing[0], '未知')}")
            return

        # 🔥 扣费逻辑
        if need_cost and req_cost > 0:
            new_pts = current_pts - req_cost
            c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_pts, uid))
            c.execute("INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                      (uid, uname, f"提交求片心愿: {title}", -req_cost, new_pts))
        
        # 🔥 免费用户扣减次数（非无限次的情况）
        if user_req_free == 1 and user_req_free_count > 0:
            c.execute("UPDATE users_meta SET req_free_count = req_free_count - 1 WHERE user_id = ?", (uid,))

        c.execute("INSERT OR IGNORE INTO media_requests (tmdb_id, media_type, title, year, poster_path, status, season) VALUES (?, ?, ?, ?, ?, 0, ?)",
                  (int(tmdb_id), media_type, title, year, poster, season))
        c.execute("INSERT OR IGNORE INTO request_users (tmdb_id, user_id, username, season) VALUES (?, ?, ?, ?)",
                  (int(tmdb_id), uid, uname, season))
        conn.commit()
        conn.close()

        season_str = f" 第 {season} 季" if media_type == "tv" and season > 0 else ""
        # 🔥 显示扣费或免费信息
        if need_cost and req_cost > 0:
            cost_msg = f"\n💰 消耗 {req_cost} 积分"
        elif user_req_free == 1:
            remaining = user_req_free_count - 1 if user_req_free_count > 0 else "无限"
            cost_msg = f"\n🎁 免费求片（剩余 {remaining} 次）" if remaining != "无限" else "\n🎁 免费求片（无限次）"
        else:
            cost_msg = ""
        _send(chat_id, f"✅ <b>求片已提交！</b>\n\n🎬 {title} ({year}){season_str}{cost_msg}\n📋 状态：等待管理员审批",
              reply_markup={"inline_keyboard": [[{"text": "📋 我的求片", "callback_data": "ub_menu_myrequests"}, {"text": "🔙 主菜单", "callback_data": "ub_back_menu"}]]})

        try:
            from app.services.bot_service import bot
            from app.core.database import add_sys_notification
            from app.core.config import REPORT_COVER_URL
            add_sys_notification("request", f"收到新求片: {title}", f"用户 {uname} 通过TG机器人求片", "/requests_admin")
            msg = f"🎬 <b>收到新求片心愿</b>\n\n👤 <b>用户：</b>{uname}\n📺 <b>内容：</b>{title} ({year}){season_str}\n📱 <b>来源：</b>TG 用户机器人\n\n请及时前往后台审批处理。"
            admin_url = cfg.get("pulse_url") or cfg.get_main_public_url() or "http://127.0.0.1:10307"
            keyboard = {"inline_keyboard": [
                [{"text": "🚀 推送 MP", "callback_data": f"req_approve_{tmdb_id}"}, {"text": "✋ 手动接单", "callback_data": f"req_manual_{tmdb_id}"}],
                [{"text": "❌ 拒绝求片", "callback_data": f"req_reject_menu_{tmdb_id}"}, {"text": "💻 网页审批", "url": f"{admin_url.rstrip('/')}/requests_admin"}]
            ]}
            poster_url = f"https://image.tmdb.org/t/p/w500{poster}" if poster else REPORT_COVER_URL
            bot.send_photo("sys_notify", poster_url, msg, reply_markup=keyboard, platform="all")
        except Exception: pass
    except Exception as e:
        _send(chat_id, f"❌ 求片提交失败：{e}")


# 🔥 追新功能已删除 - 请使用用户社区追新功能

def cmd_myrequests(chat_id, tg_user_id, msg_id=None):
    binding = _get_binding(tg_user_id)
    if not binding:
        _reply(chat_id, "❌ 请先绑定账号", msg_id=msg_id)
        return
    
    # 检查 Emby 账号是否仍然有效
    if not _check_emby_account(binding):
        _unbind_user(tg_user_id)
        _reply(chat_id, "⚠️ 你的 Emby 账号已被删除，绑定已自动解除。请联系管理员。", 
               reply_markup=_main_menu_keyboard(None), msg_id=msg_id)
        return
    
    uid = binding['emby_user_id']
    try:
        rows = query_db("SELECT mr.title, mr.year, mr.status, mr.season, mr.media_type FROM media_requests mr INNER JOIN request_users ru ON mr.tmdb_id = ru.tmdb_id AND mr.season = ru.season WHERE ru.user_id = ? ORDER BY mr.rowid DESC LIMIT 10", (uid,))
        if not rows:
            _reply(chat_id, "📋 <b>我的求片</b>\n\n暂无求片记录",
                  reply_markup={"inline_keyboard": [[{"text": "🎬 去求片", "callback_data": "ub_menu_request"}, {"text": "🔙 主菜单", "callback_data": "ub_back_menu"}]]}, msg_id=msg_id)
            return
        status_map = {0: "⏳ 待审批", 1: "📥 下载中", 2: "✅ 已完成", 3: "❌ 已拒绝", 4: "🔧 手动处理中"}
        msg = "📋 <b>我的求片</b>\n\n"
        for r in rows:
            s_str = f" 第{r['season']}季" if r['media_type'] == 'tv' and r['season'] > 0 else ""
            icon = "🎬" if r['media_type'] == 'movie' else "📺"
            msg += f"{icon} <b>{r['title']}</b> ({r['year']}){s_str}\n   {status_map.get(r['status'], '未知')}\n\n"
        _reply(chat_id, msg.strip(),
              reply_markup={"inline_keyboard": [[{"text": "🎬 继续求片", "callback_data": "ub_menu_request"}, {"text": "🔙 主菜单", "callback_data": "ub_back_menu"}]]}, msg_id=msg_id)
    except Exception as e:
        _reply(chat_id, f"❌ 查询失败：{e}", msg_id=msg_id)


def cmd_profile(chat_id, tg_user_id, msg_id=None):
    binding = _get_binding(tg_user_id)
    if not binding:
        _send(chat_id, "❌ 请先绑定账号")
        return
    
    # 检查 Emby 账号是否仍然有效
    if not _check_emby_account(binding):
        _unbind_user(tg_user_id)
        _send(chat_id, "⚠️ 你的 Emby 账号已被删除，绑定已自动解除。请联系管理员。", 
              reply_markup=_main_menu_keyboard(None))
        return
    
    uid = binding['emby_user_id']
    uname = binding['emby_username']
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        meta = conn.execute("SELECT points, expire_date FROM users_meta WHERE user_id = ?", (uid,)).fetchone()
        conn.close()

        # 获取最后一次播放记录（从播放数据库查询）
        last_play_display = "暂无播放记录"
        try:
            last_play = query_db(
                "SELECT ItemName, PlayDuration, DateCreated FROM PlaybackActivity WHERE UserId = ? ORDER BY DateCreated DESC LIMIT 1",
                (uid,), one=True
            )
            if last_play:
                item_name = last_play.get('ItemName') or last_play[0]
                play_duration = last_play.get('PlayDuration') or last_play[1]
                play_date = last_play.get('DateCreated') or last_play[2]
                minutes = int(play_duration / 60) if play_duration else 0
                # 格式化日期时间
                play_time = play_date[:16].replace("T", " ") if play_date else "未知"
                last_play_display = f"🎬 {item_name[:20]}{'...' if len(item_name) > 20 else ''}\n   📊 播放 {minutes} 分钟 • {play_time}"
        except Exception as e:
            logger.warning(f"获取播放记录失败: {e}")
            last_play_display = "暂无播放记录"
        pts = meta[0] if meta and meta[0] else 0
        expire = meta[1] if meta and meta[1] else "未设置"

        # 从 Emby 获取账号状态
        status_str = "正常"
        created_str = "未知"
        try:
            u_res = media_api.get(f"/Users/{uid}", timeout=5)
            if u_res.status_code == 200:
                u_data = u_res.json()
                if u_data.get("Policy", {}).get("IsDisabled"):
                    status_str = "⛔ 已禁用"
                else:
                    status_str = "✅ 正常"
                dc = u_data.get("DateCreated", "")
                if dc:
                    created_str = dc[:10]
        except:
            pass

        # 到期状态判断
        expire_display = expire
        if expire and expire != "未设置":
            try:
                exp_date = datetime.datetime.strptime(expire, "%Y-%m-%d").date()
                days_left = (exp_date - datetime.date.today()).days
                if "2099" in expire or "3000" in expire:
                    expire_display = "♾️ 永久有效"
                elif days_left < 0:
                    expire_display = f"❌ 已过期 ({expire})"
                elif days_left <= 7:
                    expire_display = f"⚠️ {expire}（剩余 {days_left} 天）"
                else:
                    expire_display = f"{expire}（剩余 {days_left} 天）"
            except:
                pass

        pwd_display = f"<tg-spoiler>{binding['init_password']}</tg-spoiler>" if binding.get('init_password') else "（手动绑定，未记录）"

        msg = (f"👤 <b>个人中心</b>\n\n"
               f"━━━━━━━━━━━━━━━━\n"
               f"📛 <b>用户名：</b><code>{uname}</code>\n"
               f"🔑 <b>密码：</b>{pwd_display}\n"
               f"🆔 <b>用户 ID：</b><code>{uid[:8]}...</code>\n"
               f"📅 <b>注册时间：</b>{created_str}\n"
               f"🔰 <b>账号状态：</b>{status_str}\n"
               f"━━━━━━━━━━━━━━━━\n"
               f"💰 <b>积分余额：</b>{pts}\n"
               f"⏳ <b>有效期至：</b>{expire_display}\n"
               f"🎬 <b>最后播放：</b>{last_play_display}\n"
               f"━━━━━━━━━━━━━━━━")

        _reply(chat_id, msg, reply_markup={"inline_keyboard": [
            [{"text": "✅ 签到领积分", "callback_data": "ub_menu_checkin"}, {"text": "🎟️ 续期", "callback_data": "ub_menu_renew"}],
            [{"text": "🔙 主菜单", "callback_data": "ub_back_menu"}]
        ]}, msg_id=msg_id)
    except Exception as e:
        _reply(chat_id, f"❌ 获取信息失败：{e}", msg_id=msg_id)


def cmd_unbind(chat_id, tg_user_id):
    binding = _get_binding(tg_user_id)
    if not binding:
        _send(chat_id, "❌ 你还没有绑定账号")
        return
    _send(chat_id, f"🔓 <b>确认解绑？</b>\n\n当前绑定：<b>{binding['emby_username']}</b>\n\n解绑后将无法使用签到、商城等功能。\n\n发送 /unbind_confirm 确认解绑")


def cmd_unbind_confirm(chat_id, tg_user_id):
    _unbind_user(tg_user_id)
    _send(chat_id, "✅ 已成功解绑账号。", reply_markup=_main_menu_keyboard(None))


def cmd_bind_channel(chat_id, tg_user_id, args):
    """绑定频道到当前用户账号"""
    binding = _get_binding(tg_user_id)
    if not binding:
        _send(chat_id, "❌ 请先绑定 Emby 账号后再绑定频道")
        return
    
    if not args:
        _send(chat_id, "💡 使用方法：/bind_channel 频道ID\n\n获取频道ID：\n1. 将频道消息转发给 @userinfobot\n2. 或查看频道链接中的数字\n\n示例：/bind_channel -1001234567890")
        return
    
    try:
        channel_id = args.strip().split()[0]
        # 绑定频道
        if _bind_channel(channel_id, tg_user_id, ""):
            _send(chat_id, f"✅ 频道绑定成功！\n\n频道ID：<code>{channel_id}</code>\n绑定账号：<b>{binding['emby_username']}</b>\n\n现在用频道身份发送命令将使用此账号")
        else:
            _send(chat_id, "❌ 绑定失败，请稍后重试")
    except Exception as e:
        _send(chat_id, f"❌ 绑定失败：{e}")


def cmd_unbind_channel(chat_id, tg_user_id, args):
    """解绑频道"""
    if not args:
        _send(chat_id, "💡 使用方法：/unbind_channel 频道ID")
        return
    
    channel_id = args.strip().split()[0]
    if _unbind_channel(channel_id):
        _send(chat_id, f"✅ 频道 <code>{channel_id}</code> 已解绑")
    else:
        _send(chat_id, "❌ 解绑失败")


def cmd_password(chat_id, tg_user_id, args):
    """修改密码"""
    binding = _get_binding(tg_user_id)
    if not binding:
        _send(chat_id, "❌ 请先绑定账号")
        return
    
    # 检查 Emby 账号是否仍然有效
    if not _check_emby_account(binding):
        _unbind_user(tg_user_id)
        _send(chat_id, "⚠️ 你的 Emby 账号已被删除，绑定已自动解除。请联系管理员。", 
              reply_markup=_main_menu_keyboard(None))
        return

    uname = binding['emby_username']

    # 检查是否在修改密码流程中
    state = _user_state.get(str(tg_user_id))
    if state and state.get("action") == "change_pwd_step2":
        # 用户已输入新密码，等待确认
        new_pwd = args.strip() if args else ""
        pw_valid, pw_error = validate_password_strength(new_pwd)
        if not pw_valid:
            _send(chat_id, f"❌ {pw_error}，请重新输入：")
            return
        # 确认新密码
        _user_state[str(tg_user_id)] = {"action": "change_pwd_confirm", "new_pwd": new_pwd}
        _send(chat_id, f"🔐 <b>确认新密码</b>\n\n请再次输入新密码进行确认：",
              reply_markup={"inline_keyboard": [[{"text": "❌ 取消", "callback_data": "ub_cancel_state"}]]})
        return

    if state and state.get("action") == "change_pwd_confirm":
        # 用户确认密码
        confirm_pwd = args.strip() if args else ""
        new_pwd = state.get("new_pwd", "")
        if confirm_pwd != new_pwd:
            _send(chat_id, "❌ 两次密码不一致，修改失败。",
                  reply_markup={"inline_keyboard": [[{"text": "🔙 返回", "callback_data": "ub_back_menu"}]]})
            _user_state.pop(str(tg_user_id), None)
            return

        # 执行修改密码
        uid = binding['emby_user_id']
        try:
            res = media_api.post(f"/Users/{uid}/Password", json={"NewPw": new_pwd}, timeout=5)
            if res.status_code in [200, 204]:
                _send(chat_id, f"✅ <b>密码修改成功！</b>\n\n新密码：<code>{new_pwd}</code>\n\n请妥善保管你的密码",
                      reply_markup={"inline_keyboard": [[{"text": "🔙 返回", "callback_data": "ub_back_menu"}]]})
            else:
                _send(chat_id, "❌ 修改密码失败，请稍后重试")
        except Exception as e:
            _send(chat_id, f"❌ 修改密码失败：{e}")
        _user_state.pop(str(tg_user_id), None)
        return

    # 开始修改密码流程
    if not args or ' ' not in args.strip():
        _send(chat_id, "🔐 <b>修改密码</b>\n\n请发送命令（当前密码和新密码用空格隔开）：\n<code>/password 当前密码 新密码</code>\n\n例如：<code>/password 当前密码 NewPass1</code>\n\n⚠️ 新密码至少 8 位，需包含小写字母 + 大写字母或数字",
              reply_markup={"inline_keyboard": [[{"text": "❌ 取消", "callback_data": "ub_back_menu"}]]})
        return

    parts = args.strip().split(' ', 1)
    old_pwd = parts[0].strip()
    new_pwd = parts[1].strip() if len(parts) > 1 else ""

    pw_valid, pw_error = validate_password_strength(new_pwd)
    if not pw_valid:
        _send(chat_id, f"❌ {pw_error}，请检查后重试")
        return

    # 验证当前密码 - 通过登录 API 验证
    uid = binding['emby_user_id']
    try:
        # 先通过登录验证当前密码
        auth_url = f"{cfg.get('emby_host')}/emby/Users/AuthenticateByName"
        auth_headers = {"X-Emby-Authorization": 'MediaBrowser Client="EmbyPulse", Device="TGBot", DeviceId="UserBot", Version="1.0.0"'}
        auth_res = requests.post(auth_url, json={"Username": uname, "Pw": old_pwd}, headers=auth_headers, timeout=10)
        if auth_res.status_code != 200:
            _send(chat_id, "❌ 当前密码错误，请检查后重试")
            return

        # 验证成功后修改密码 - 使用 media_api
        res = media_api.post(f"/Users/{uid}/Password", json={"NewPw": new_pwd}, timeout=10)
        if res.status_code in [200, 204]:
            # 如果是初始化密码，更新绑定记录
            if binding.get('init_password'):
                conn = sqlite3.connect(SYSTEM_DB_PATH)
                conn.execute("UPDATE tg_user_bindings SET init_password = ? WHERE tg_user_id = ?", (new_pwd, str(tg_user_id)))
                conn.commit()
                conn.close()

            _send(chat_id, f"✅ <b>密码修改成功！</b>\n\n新密码：<code>{new_pwd}</code>\n\n请妥善保管你的密码",
                  reply_markup={"inline_keyboard": [[{"text": "🔙 返回", "callback_data": "ub_back_menu"}]]})
        else:
            _send(chat_id, "❌ 修改密码失败，请稍后重试")
    except Exception as e:
        _send(chat_id, f"❌ 修改密码失败：{e}")


def cmd_server(chat_id, tg_user_id, msg_id=None):
    binding = _get_binding(tg_user_id)
    
    # 检查 Emby 账号是否仍然有效（如果有绑定）
    if binding and not _check_emby_account(binding):
        _unbind_user(tg_user_id)
        _reply(chat_id, "⚠️ 你的 Emby 账号已被删除，绑定已自动解除。请联系管理员。", 
               reply_markup=_main_menu_keyboard(None), msg_id=msg_id)
        return
    
    emby_uid = binding.get("emby_user_id") if binding else None
    try:
        routes = cfg.get_user_routes(emby_uid)

        if not routes:
            _send(chat_id, "📡 管理员未配置公网地址")
            return

        msg = "📡 <b>服务器线路状态</b>\n\n"
        for r in routes:
            name = r.get("name", "未命名")
            url = r.get("url", "").rstrip('/')
            if url:
                try:
                    start = time.time()
                    requests.get(f"{url}/web/favicon.ico", timeout=3)
                    delay = int((time.time() - start) * 1000)
                    icon = "🟢" if delay < 100 else ("🟡" if delay < 300 else "🔴")
                    msg += f"{icon} <b>{name}</b>：{delay}ms\n🔗 {url}\n\n"
                except:
                    msg += f"🔴 <b>{name}</b>：超时/离线\n🔗 {url}\n\n"
        _reply(chat_id, msg.strip(), reply_markup={"inline_keyboard": [[{"text": "🔙 主菜单", "callback_data": "ub_back_menu"}]]}, msg_id=msg_id)
    except:
        _reply(chat_id, "❌ 查询失败", msg_id=msg_id)


def cmd_library(chat_id, tg_user_id, msg_id=None):
    binding = _get_binding(tg_user_id)
    
    # 未绑定用户也可以查看媒体库统计，不需要检查绑定状态
    # 检查 Emby 账号是否仍然有效（如果有绑定）
    if binding and not _check_emby_account(binding):
        _unbind_user(tg_user_id)
        _reply(chat_id, "⚠️ 你的 Emby 账号已被删除，绑定已自动解除。请联系管理员。", 
               reply_markup=_main_menu_keyboard(None), msg_id=msg_id)
        return
    
    try:
        res = media_api.get("/Items/Counts", timeout=5)
        if res.status_code == 200:
            d = res.json()
            _reply(chat_id, f"📊 <b>媒体库统计</b>\n\n"
                  f"🎬 电影：<b>{d.get('MovieCount', 0)}</b> 部\n"
                  f"📺 剧集：<b>{d.get('SeriesCount', 0)}</b> 部\n"
                  f"🎞️ 总集数：<b>{d.get('EpisodeCount', 0)}</b> 集",
                  reply_markup={"inline_keyboard": [[{"text": "🔙 主菜单", "callback_data": "ub_back_menu"}]]}, msg_id=msg_id)
        else:
            _send(chat_id, "❌ 无法获取媒体库信息")
    except:
        _send(chat_id, "❌ 连接服务器失败")

def cmd_calendar(chat_id, tg_user_id, msg_id=None):
    """今日剧集更新"""
    binding = _get_binding(tg_user_id)
    
    # 检查 Emby 账号是否仍然有效（如果有绑定）
    if binding and not _check_emby_account(binding):
        _unbind_user(tg_user_id)
        _reply(chat_id, "⚠️ 你的 Emby 账号已被删除，绑定已自动解除。请联系管理员。", 
               reply_markup=_main_menu_keyboard(None), msg_id=msg_id)
        return
    
    try:
        from app.routers.calendar_notify import get_today_updates, format_notify_message
        updates = get_today_updates()
        message = format_notify_message(updates)
        _reply(chat_id, message, 
               reply_markup={"inline_keyboard": [[{"text": "🔙 主菜单", "callback_data": "ub_back_menu"}]]}, 
               msg_id=msg_id)
    except Exception as e:
        logger.error(f"[calendar命令] 执行失败: {e}")
        _reply(chat_id, "❌ 获取今日更新失败，请稍后重试", 
               reply_markup={"inline_keyboard": [[{"text": "🔙 主菜单", "callback_data": "ub_back_menu"}]]}, 
               msg_id=msg_id)


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

    def start(self):
        if not _is_pro():
            logger.info("🤖 [UserBot] 非 Pro 用户，用户机器人未启动")
            return
        token = cfg.get("tg_user_bot_token")
        if not token:
            return
        if self.running:
            return
        self.running = True
        self._set_commands()
        self.poll_thread = threading.Thread(target=self._polling_loop, daemon=True)
        self.poll_thread.start()
        # 🔥 启动定时任务线程
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        # 🔒 加载 batch_used 内存值 + 启动定时落盘线程
        _load_batch_used_from_cfg()
        _start_batch_flush_thread()
        logger.info("🤖 [Pro] 用户 TG 机器人已启动")

    def stop(self):
        self.running = False
        # 同步 flush 一次防止丢失增量
        _batch_flush_stop.set()
        try:
            _flush_batch_used(force=True)
        except Exception:
            logger.exception("[UserBot] stop 时 flush batch_used 失败")

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
        token = cfg.get("tg_user_bot_token")
        while self.running:
            try:
                # 使用 long polling，timeout=30 秒
                res = requests.get(f"https://api.telegram.org/bot{token}/getUpdates",
                                   params={"offset": self.offset, "timeout": 30},
                                   proxies=_get_proxies(), timeout=35)
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
                    time.sleep(3)
            except Exception as e:
                logger.debug(f"[UserBot] polling 异常: {e}")
                time.sleep(5)

    def _scheduler_loop(self):
        """定时任务循环"""
        import time as _time
        _time.sleep(30)  # 等待服务完全启动
        
        while self.running:
            try:
                # 检查是否需要执行彩票开奖
                conn = sqlite3.connect(SYSTEM_DB_PATH)
                config = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM point_config").fetchall()}
                conn.close()
                
                if int(config.get('enable_lottery', 0)) == 1:
                    draw_hour = int(config.get('lottery_draw_hour', 20))
                    now = datetime.datetime.now()
                    current_hour = now.hour
                    current_minute = now.minute
                    
                    # 检查是否到了开奖时间（整点后5分钟内执行）
                    if current_hour == draw_hour and current_minute < 5:
                        # 检查今天是否已开奖
                        today = now.strftime('%Y-%m-%d')
                        conn = sqlite3.connect(SYSTEM_DB_PATH)
                        result = conn.execute("SELECT winning_numbers FROM lottery_results WHERE draw_date = ?", (today,)).fetchone()
                        conn.close()
                        
                        if not result or not result[0]:
                            logger.info(f"[彩票] 到达开奖时间 {draw_hour}:00，执行自动开奖...")
                            do_lottery_draw()
                
                # 🔥 处理过期的 PK 邀请
                try:
                    conn = sqlite3.connect(SYSTEM_DB_PATH)
                    c = conn.cursor()
                    # 获取刚过期的邀请（有消息ID的）
                    expired_invites = c.execute(
                        "SELECT id, chat_id, message_id, challenger_tg_name, target_tg_name FROM pk_invitations WHERE expires_at < datetime('now', 'localtime') AND status = 'pending' AND message_id IS NOT NULL"
                    ).fetchall()
                    
                    for invite in expired_invites:
                        invite_id = invite[0]
                        chat_id = invite[1]
                        msg_id = invite[2]
                        challenger_name = invite[3] or '用户'
                        target_name = invite[4] or '用户'
                        
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
                        c.execute("UPDATE pk_invitations SET status = 'expired' WHERE id = ?", (invite_id,))
                    
                    conn.commit()
                    if expired_invites:
                        logger.info(f"[PK] 已处理 {len(expired_invites)} 个过期邀请")
                    conn.close()
                except Exception as e:
                    logger.error(f"[PK] 处理过期邀请失败: {e}")
                
                # 每60秒检查一次
                _time.sleep(60)
                
            except Exception as e:
                logger.error(f"[UserBot] 定时任务异常: {e}")
                _time.sleep(60)

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
            if not cfg.get("user_bot_group_enabled", False):
                return
            
            # 检查群是否在白名单中
            allowed_groups = cfg.get("user_bot_allowed_groups", "")
            if allowed_groups:
                allowed_list = [g.strip() for g in allowed_groups.split("\n") if g.strip()]
                if chat_id not in allowed_list and f"@{chat.get('username', '')}" not in allowed_list:
                    return  # 不在白名单，忽略
            
            # 获取群内允许的指令
            group_commands = cfg.get("user_bot_group_commands", "checkin,help")
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
            if member.get("is_bot") and str(member.get("id")) == str(cfg.get("tg_user_bot_token", "").split(":")[0] if ":" in cfg.get("tg_user_bot_token", "") else ""):
                # 机器人被加入群，发送欢迎消息
                welcome_msg = cfg.get("user_bot_welcome_msg", "")
                if welcome_msg:
                    _send(chat_id, welcome_msg)
                else:
                    _send(chat_id, f"👋 你好！我是 EmbyPulse 用户机器人，已加入 <b>{group_name}</b>\n\n"
                          "✅ 发送 /checkin 或 /签到 获取积分\n"
                          "✅ 发送 /help 查看群内可用指令\n\n"
                          "💡 更多功能请私聊机器人使用")
                break


user_bot = UserBot()

def do_lottery_draw():
    """执行彩票开奖（由定时任务调用）"""
    try:
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        
        # 检查今天是否已开奖
        result = c.execute("SELECT winning_numbers FROM lottery_results WHERE draw_date = ?", (today,)).fetchone()
        if result and result[0]:
            logger.info(f"[彩票] 今天已开奖: {result[0]}")
            conn.close()
            return
        
        # 生成中奖号码
        winning_numbers = ''.join([str(random.randint(0, 9)) for _ in range(4)])
        
        # 获取奖池
        pool_row = c.execute("SELECT total_pool FROM lottery_results WHERE draw_date = ?", (today,)).fetchone()
        total_pool = pool_row[0] if pool_row else 0
        
        # 获取所有今天的彩票（排除已删除的账号）
        raw_tickets = c.execute("SELECT id, user_id, username, numbers FROM lottery_tickets WHERE draw_date = ?", (today,)).fetchall()
        
        # 过滤已删除的账号
        tickets = []
        for ticket_id, user_id, username, numbers in raw_tickets:
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
            conn.close()
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
        config = {r[0]: r[1] for r in c.execute("SELECT key, value FROM point_config").fetchall()}
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
        
        for level, winner_list in winners.items():
            if not winner_list or prize_pools[level] <= 0:
                continue
            
            # 每人奖金 = 该奖项奖池 / 中奖人数
            prize_per_person = prize_pools[level] // len(winner_list)
            if prize_per_person <= 0:
                prize_per_person = 1  # 最低1积分
            
            for ticket_id, user_id, username in winner_list:
                # 更新用户积分
                row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (user_id,)).fetchone()
                current_points = (row[0] or 0) + prize_per_person if row else prize_per_person
                
                if row:
                    c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (current_points, user_id))
                else:
                    c.execute("INSERT INTO users_meta (user_id, points) VALUES (?, ?)", (user_id, current_points))
                
                # 记录中奖
                c.execute("INSERT INTO lottery_winners (user_id, username, ticket_id, prize_level, prize_amount, draw_date) VALUES (?, ?, ?, ?, ?, ?)",
                         (user_id, username, ticket_id, level, prize_per_person, today))
                
                # 记录日志
                level_names = {1: "一等奖", 2: "二等奖", 3: "三等奖", 4: "安慰奖"}
                c.execute("INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                         (user_id, username, f"彩票{level_names[level]}", prize_per_person, current_points))
        
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
                    # 更新积分
                    row = c.execute("SELECT points FROM users_meta WHERE user_id = ?", (user_id,)).fetchone()
                    current_points = (row[0] or 0) + prize_per_lucky if row else prize_per_lucky
                    if row:
                        c.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (current_points, user_id))
                    else:
                        c.execute("INSERT INTO users_meta (user_id, points) VALUES (?, ?)", (user_id, current_points))
                    
                    # 记录中奖
                    c.execute("INSERT INTO lottery_winners (user_id, username, ticket_id, prize_level, prize_amount, draw_date) VALUES (?, ?, ?, ?, ?, ?)",
                             (user_id, username, ticket_id, 5, prize_per_lucky, today))
                    c.execute("INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                             (user_id, username, "彩票幸运奖", prize_per_lucky, current_points))
                    
                    lucky_winners.append((user_id, username, prize_per_lucky))
                    logger.info(f"[彩票] 幸运奖: {username} 获得 {prize_per_lucky} 积分")
        
        # 更新开奖结果
        c.execute("UPDATE lottery_results SET winning_numbers = ? WHERE draw_date = ?", (winning_numbers, today))
        
        # 🔥 计算剩余奖池并累积到下期
        # 已分配的奖金（实际发放的）
        total_distributed = 0
        for level, winner_list in winners.items():
            if winner_list and level in prize_pools and prize_pools[level] > 0:
                # 实际分配 = 奖池金额（即使无人中奖，该奖项的奖池也算未分配）
                total_distributed += prize_pools[level]
        # 幸运奖也算已分配
        if lucky_winners and prize_pools.get(5, 0) > 0:
            total_distributed += prize_pools[5]
        
        # 剩余奖池 = 总奖池 - 已分配
        remaining_pool = total_pool - total_distributed
        if remaining_pool < 0:
            remaining_pool = 0
        
        if remaining_pool > 0:
            # 累积到明天
            tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
            c.execute("INSERT OR IGNORE INTO lottery_results (draw_date, winning_numbers, total_pool) VALUES (?, '', 0)", (tomorrow,))
            c.execute("UPDATE lottery_results SET total_pool = total_pool + ? WHERE draw_date = ?", (remaining_pool, tomorrow))
            logger.info(f"[彩票] 剩余奖池 {remaining_pool} 已累积到 {tomorrow}")
        
        conn.commit(); conn.close()
        
        logger.info(f"[彩票] 开奖完成: {winning_numbers}, 奖池: {total_pool}, 中奖人数: {sum(len(w) for w in winners.values())}")
        
        # 🔥 发送开奖结果到群
        # 获取允许彩票的群
        allowed_groups = cfg.get("user_bot_allowed_groups", "")
        logger.info(f"[彩票] 允许的群: {allowed_groups}")
        if allowed_groups:
            group_list = [g.strip() for g in allowed_groups.split("\n") if g.strip()]
            logger.info(f"[彩票] 群列表: {group_list}")
            
            # 构建开奖消息
            msg = f"🎰 <b>彩票开奖结果</b> ({today})\n\n"
            msg += f"🎲 中奖号码: <b>{winning_numbers}</b>\n"
            msg += f"💰 奖池: {total_pool} 积分\n\n"
            
            total_winners = sum(len(w) for w in winners.values()) + len(lucky_winners)
            if total_winners > 0:
                msg += "🏆 中奖名单:\n"
                level_names = {1: "一等奖", 2: "二等奖", 3: "三等奖", 4: "安慰奖"}
                for level, winner_list in winners.items():
                    if winner_list:
                        # 计算每人奖金
                        prize_per_person = prize_pools[level] // len(winner_list) if prize_pools[level] > 0 else 0
                        for _, user_id, emby_username in winner_list:
                            # 获取TG名称
                            binding = _get_binding_by_emby_id(user_id)
                            display = ''
                            if binding and binding.get('tg_user_id'):
                                # 从tg_bot_users表获取显示名称
                                try:
                                    conn_tg = sqlite3.connect(SYSTEM_DB_PATH)
                                    tg_row = conn_tg.execute("SELECT tg_name FROM tg_bot_users WHERE tg_user_id = ?", (binding['tg_user_id'],)).fetchone()
                                    conn_tg.close()
                                    if tg_row and tg_row[0]:
                                        display = f"<a href='tg://user?id={binding['tg_user_id']}'>{tg_row[0]}</a>"
                                except:
                                    pass
                            # fallback: 显示 emby 用户名
                            if not display:
                                display = emby_username or f"用户{user_id}"
                            msg += f"• {display} - {level_names[level]} (+{prize_per_person}积分)\n"
                if lucky_winners:
                    for user_id, emby_username, amount in lucky_winners:
                        binding = _get_binding_by_emby_id(user_id)
                        display = ''
                        if binding and binding.get('tg_user_id'):
                            try:
                                conn_tg = sqlite3.connect(SYSTEM_DB_PATH)
                                tg_row = conn_tg.execute("SELECT tg_name FROM tg_bot_users WHERE tg_user_id = ?", (binding['tg_user_id'],)).fetchone()
                                conn_tg.close()
                                if tg_row and tg_row[0]:
                                    display = f"<a href='tg://user?id={binding['tg_user_id']}'>{tg_row[0]}</a>"
                            except:
                                pass
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
