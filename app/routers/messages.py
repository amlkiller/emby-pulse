from fastapi import APIRouter, Request, Depends
from pydantic import BaseModel
from typing import Optional
from app.core.database import query_db, SYSTEM_DB_PATH
from app.core.media_adapter import media_api
from app.core.security_utils import sanitize_html, sanitize_rich_html
from app.core.security import require_admin
from app.routers.auth import is_admin_user
import sqlite3
import datetime
import sys
import os
from app.core.security_utils import safe_error_message

router = APIRouter()

# 简单日志函数，强制刷新
def log_msg(msg):
    print(msg, flush=True)


def _check_user_exists(user_id: str) -> bool:
    """检查 Emby 用户是否仍然存在"""
    if not user_id:
        return False
    try:
        if media_api and media_api.host and media_api.api_key:
            res = media_api.get(f"/Users/{user_id}", timeout=5)
            return res.status_code == 200
    except:
        pass
    return True  # 网络异常时不误判，允许继续操作


class SendMessageModel(BaseModel):
    user_id: str
    content: str


class ReplyModel(BaseModel):
    conversation_id: int
    content: str


class UserSendMessageModel(BaseModel):
    content: str


# ==================== 管理端 API ====================

@router.get("/api/users/all")
def get_all_users(request: Request, _admin: dict = Depends(require_admin)):
    """获取所有用户列表（用于发起对话） - 仅管理员"""
    log_msg(f"[消息中心] get_all_users: 开始获取用户列表")
    log_msg(f"[消息中心] get_all_users: media_api.host = {media_api.host}")
    log_msg(f"[消息中心] get_all_users: media_api.api_key = {'***' if media_api.api_key else 'None'}")
    
    try:
        # 从 Emby 获取所有用户
        if media_api and media_api.host and media_api.api_key:
            log_msg(f"[消息中心] get_all_users: 调用 media_api.get('/Users')")
            users_res = media_api.get("/Users")
            log_msg(f"[消息中心] get_all_users: users_res={users_res is not None}, status={users_res.status_code if users_res else 'None'}")
            if users_res and users_res.status_code == 200:
                all_users = users_res.json()
                log_msg(f"[消息中心] get_all_users: 获取到 {len(all_users)} 个用户")
                
                # 获取用户备注
                conn = sqlite3.connect(SYSTEM_DB_PATH)
                c = conn.cursor()
                user_remarks = {}
                try:
                    # 从 users_meta 获取备注（Emby 用户备注）
                    c.execute("SELECT user_id, remark FROM users_meta WHERE remark IS NOT NULL AND remark != ''")
                    for row in c.fetchall():
                        user_remarks[row[0]] = row[1]
                    log_msg(f"[消息中心] get_all_users: 获取到 {len(user_remarks)} 个用户备注")
                except Exception as e:
                    log_msg(f"[消息中心] get_all_users: 获取备注失败: {e}")
                conn.close()
                
                users = []
                for u in all_users:
                    user_id = u.get("Id", "")
                    remark = user_remarks.get(user_id, "")
                    users.append({
                        "Id": user_id,
                        "Name": u.get("Name", ""),
                        "PrimaryImageTag": u.get("PrimaryImageTag"),
                        "Remark": remark
                    })
                    if remark:
                        log_msg(f"[消息中心] get_all_users: 用户 {user_id} 备注为 {remark}")
                # 按名称排序
                users.sort(key=lambda x: (x.get("Remark") or x.get("Name") or "").lower())
                return {"status": "success", "users": users}
            else:
                log_msg(f"[消息中心] 获取用户列表失败: status={users_res.status_code if users_res else 'None'}")
        else:
            log_msg(f"[消息中心] media_api 未初始化或配置缺失: host={media_api.host if media_api else 'N/A'}")
    except Exception as e:
        import traceback
        log_msg(f"[消息中心] 获取用户列表异常: {e}")
        traceback.print_exc()
    
    return {"status": "success", "users": []}


@router.get("/api/users/search")
def search_users(request: Request, q: str = ""):
    """搜索用户（用于发起对话）"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    if not q or len(q) < 2:
        return {"status": "success", "users": []}
    
    try:
        # 从 Emby 搜索用户
        if media_api:
            users_res = media_api.get("/Users")
            if users_res and users_res.status_code == 200:
                all_users = users_res.json()
                
                # 获取用户备注
                conn = sqlite3.connect(SYSTEM_DB_PATH)
                c = conn.cursor()
                user_remarks = {}
                try:
                    # 从 users_meta 获取备注（Emby 用户备注）
                    c.execute("SELECT user_id, remark FROM users_meta WHERE remark IS NOT NULL AND remark != ''")
                    for row in c.fetchall():
                        user_remarks[row[0]] = row[1]
                except:
                    pass
                conn.close()
                
                # 过滤匹配的用户
                matched = []
                q_lower = q.lower()
                for u in all_users:
                    name = u.get("Name", "")
                    user_id = u.get("Id", "")
                    remark = user_remarks.get(user_id, "")
                    # 搜索名称、ID 或备注
                    if q_lower in name.lower() or q_lower in user_id.lower() or q_lower in remark.lower():
                        matched.append({
                            "Id": user_id,
                            "Name": name,
                            "PrimaryImageTag": u.get("PrimaryImageTag"),
                            "Remark": remark
                        })
                        if len(matched) >= 10:
                            break
                return {"status": "success", "users": matched}
            else:
                log_msg(f"[消息中心] 搜索用户失败: status={users_res.status_code if users_res else 'None'}")
        else:
            log_msg("[消息中心] media_api 未初始化")
    except Exception as e:
        log_msg(f"[消息中心] 搜索用户异常: {e}")
    
    return {"status": "success", "users": []}


def _ensure_msg_tables():
    """确保消息表存在"""
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS msg_conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        username TEXT,
        user_avatar TEXT,
        last_message TEXT,
        last_time DATETIME DEFAULT CURRENT_TIMESTAMP,
        unread_admin INTEGER DEFAULT 0,
        unread_user INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS msg_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id INTEGER,
        sender_type TEXT DEFAULT 'admin',
        sender_id TEXT,
        sender_name TEXT,
        content TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    # 消息通知屏蔽表
    c.execute('''CREATE TABLE IF NOT EXISTS msg_notify_block (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()


@router.get("/api/messages/conversations")
def get_conversations(request: Request, page: int = 1, limit: int = 20):
    """获取会话列表（管理端）"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    # 确保表存在
    _ensure_msg_tables()

    offset = (page - 1) * limit
    
    # 直接连接数据库查询
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # 查询会话列表
    c.execute("""
        SELECT c.*, 
               (SELECT COUNT(*) FROM msg_items WHERE conversation_id = c.id AND sender_type = 'user' AND created_at > COALESCE(
                   (SELECT created_at FROM msg_items WHERE conversation_id = c.id AND sender_type = 'admin' ORDER BY created_at DESC LIMIT 1), '1970-01-01'
               )) as new_replies
        FROM msg_conversations c
        ORDER BY c.last_time DESC
        LIMIT ? OFFSET ?
    """, (limit, offset))
    rows = c.fetchall()
    conversations = [dict(row) for row in rows] if rows else []
    
    # 查询总数
    c.execute("SELECT COUNT(*) as cnt FROM msg_conversations")
    total_row = c.fetchone()
    total_count = total_row["cnt"] if total_row else 0
    
    # 获取所有 Emby 用户 ID（用于判断用户是否已删除）
    all_emby_user_ids = set()
    try:
        if media_api and media_api.host and media_api.api_key:
            users_res = media_api.get("/Users")
            if users_res and users_res.status_code == 200:
                all_emby_user_ids = set(u.get("Id") for u in users_res.json())
    except:
        pass
    
    # 获取用户头像和备注
    for conv in conversations:
        # 检查用户是否已删除
        conv["user_deleted"] = conv["user_id"] not in all_emby_user_ids if all_emby_user_ids else False
        
        if conv and not conv.get("user_avatar"):
            # 先从本地数据库获取头像和备注
            try:
                c.execute("SELECT avatar, remark FROM local_users WHERE emby_user_id = ?", (conv["user_id"],))
                row = c.fetchone()
                if row:
                    if row[0]:
                        conv["user_avatar"] = row[0]
                    if row[1]:
                        conv["user_remark"] = row[1]
            except:
                pass
            # 如果没有头像，使用 Emby 用户头像代理
            if not conv.get("user_avatar"):
                conv["user_avatar"] = f"/api/proxy/user_image/{conv['user_id']}"
        
        # 从 users_meta 获取备注
        if conv and not conv.get("user_remark"):
            try:
                c.execute("SELECT remark FROM users_meta WHERE user_id = ?", (conv["user_id"],))
                row = c.fetchone()
                if row and row[0]:
                    conv["user_remark"] = row[0]
            except:
                pass
        
        # 处理 PINNED 标签
        remark = conv.get("user_remark", "")
        if remark:
            is_pinned = remark.startswith("[PINNED]")
            if is_pinned:
                conv["user_remark"] = remark[8:]  # 移除 [PINNED] 前缀
                conv["pinned"] = True
            else:
                conv["pinned"] = False
        else:
            conv["pinned"] = False
    
    conn.close()

    return {
        "status": "success",
        "data": conversations,
        "total": total_count,
        "page": page,
        "limit": limit
    }


@router.get("/api/messages/conversation/{user_id}")
def get_conversation(user_id: str, request: Request, page: int = 1, limit: int = 50):
    """获取与某用户的聊天记录（管理端）"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    # 确保表存在
    _ensure_msg_tables()

    # 直接连接数据库
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # 查找或创建会话
    c.execute("SELECT * FROM msg_conversations WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    
    if not row:
        # 创建会话
        username = user_id
        user_avatar = None
        try:
            if media_api:
                user_info = media_api.get(f"/Users/{user_id}")
                if user_info and user_info.status_code == 200:
                    user_data = user_info.json()
                    username = user_data.get("Name", user_id)
        except:
            pass

        c.execute("""
            INSERT INTO msg_conversations (user_id, username, user_avatar, created_at, last_time)
            VALUES (?, ?, ?, datetime('now','localtime'), datetime('now','localtime'))
        """, (user_id, username, user_avatar))
        conn.commit()
        conv_id = c.lastrowid
        conv = {"id": conv_id, "user_id": user_id, "username": username, "user_avatar": user_avatar}
    else:
        conv = dict(row)
        conv_id = conv["id"]

    # 设置头像代理URL
    if not conv.get("user_avatar"):
        conv["user_avatar"] = f"/api/proxy/user_image/{user_id}"

    # 获取用户备注
    try:
        c.execute("SELECT remark FROM local_users WHERE emby_user_id = ?", (user_id,))
        row = c.fetchone()
        if row and row[0]:
            conv["user_remark"] = row[0]
    except:
        pass
    if not conv.get("user_remark"):
        try:
            c.execute("SELECT remark FROM users_meta WHERE user_id = ?", (user_id,))
            row = c.fetchone()
            if row and row[0]:
                conv["user_remark"] = row[0]
        except:
            pass

    # 获取消息列表
    offset = (page - 1) * limit
    c.execute("""
        SELECT * FROM msg_items
        WHERE conversation_id = ?
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """, (conv_id, limit, offset))
    msg_rows = c.fetchall()
    messages = [dict(m) for m in msg_rows] if msg_rows else []

    # 标记管理员已读
    c.execute("UPDATE msg_conversations SET unread_admin = 0 WHERE id = ?", (conv_id,))
    conn.commit()
    conn.close()

    return {
        "status": "success",
        "data": {
            "conversation": conv,
            "messages": list(reversed(messages))
        }
    }


@router.post("/api/messages/send")
def send_message(data: SendMessageModel, request: Request):
    """管理员发送消息给用户"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    # 确保表存在
    _ensure_msg_tables()

    admin_name = user.get("Name", "管理员")

    # 查找或创建会话
    conv = query_db("SELECT * FROM msg_conversations WHERE user_id = ?", (data.user_id,), one=True)
    if not conv:
        # 获取用户名
        username = data.user_id
        user_avatar = None
        try:
            if media_api:
                user_info = media_api.get(f"/Users/{data.user_id}")
                if user_info and user_info.status_code == 200:
                    user_data = user_info.json()
                    username = user_data.get("Name", data.user_id)
        except:
            pass

        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        c.execute("""
            INSERT INTO msg_conversations (user_id, username, user_avatar, created_at, last_time)
            VALUES (?, ?, ?, datetime('now','localtime'), datetime('now','localtime'))
        """, (data.user_id, username, user_avatar))
        conv_id = c.lastrowid
        conn.commit()
        conn.close()
    else:
        conv_id = conv["id"]

    # 插入消息
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO msg_items (conversation_id, sender_type, sender_id, sender_name, content, created_at)
        VALUES (?, 'admin', ?, ?, ?, datetime('now','localtime'))
    """, (conv_id, user.get("Id"), admin_name, sanitize_html(data.content, max_length=5000)))
    c.execute("""
        UPDATE msg_conversations SET last_message = ?, last_time = datetime('now','localtime'), unread_user = unread_user + 1
        WHERE id = ?
    """, (sanitize_html(data.content[:100]), conv_id))
    conn.commit()
    conn.close()

    return {"status": "success", "message": "发送成功"}


@router.post("/api/messages/reply")
def admin_reply(data: ReplyModel, request: Request):
    """管理员回复消息"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    # 确保表存在
    _ensure_msg_tables()

    admin_name = user.get("Name", "管理员")

    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()

    # 插入消息
    c.execute("""
        INSERT INTO msg_items (conversation_id, sender_type, sender_id, sender_name, content, created_at)
        VALUES (?, 'admin', ?, ?, ?, datetime('now','localtime'))
    """, (data.conversation_id, user.get("Id"), admin_name, sanitize_html(data.content, max_length=5000)))

    # 更新会话
    c.execute("""
        UPDATE msg_conversations SET last_message = ?, last_time = datetime('now','localtime'), unread_user = unread_user + 1
        WHERE id = ?
    """, (sanitize_html(data.content[:100]), data.conversation_id))

    conn.commit()
    conn.close()

    return {"status": "success", "message": "回复成功"}


@router.get("/api/messages/unread")
def get_unread_count(request: Request):
    """获取管理员未读会话数"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    # 确保表存在
    _ensure_msg_tables()

    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM msg_conversations WHERE unread_admin > 0")
    row = c.fetchone()
    conn.close()
    return {"status": "success", "count": row[0] if row else 0}


@router.post("/api/messages/mark_read/{conversation_id}")
def mark_read(conversation_id: int, request: Request):
    """标记会话已读"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE msg_conversations SET unread_admin = 0 WHERE id = ?", (conversation_id,))
    conn.commit()
    conn.close()

    return {"status": "success"}


# ==================== 用户端 API ====================

@router.get("/api/user/messages")
def user_get_messages(request: Request, page: int = 1, limit: int = 50):
    """用户获取自己的消息列表"""
    req_user = request.session.get("req_user")
    if not req_user:
        return {"status": "error", "message": "未登录"}

    user_id = req_user.get("Id")
    
    # 检查 Emby 账号是否仍然存在
    if not _check_user_exists(user_id):
        log_msg(f"[消息中心] 用户 {user_id} 的 Emby 账号已被删除")
        request.session.pop("req_user", None)
        return {"status": "error", "message": "账号已被删除，请重新登录", "account_deleted": True}
    
    # 确保消息表存在
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS msg_conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        username TEXT,
        user_avatar TEXT,
        last_message TEXT,
        last_time DATETIME DEFAULT CURRENT_TIMESTAMP,
        unread_admin INTEGER DEFAULT 0,
        unread_user INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS msg_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id INTEGER,
        sender_type TEXT DEFAULT 'admin',
        sender_id TEXT,
        sender_name TEXT,
        content TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    
    # 查找会话
    c.execute("SELECT * FROM msg_conversations WHERE user_id = ?", (user_id,))
    conv = c.fetchone()
    if not conv:
        conn.close()
        return {"status": "success", "data": {"messages": [], "unread": 0}}
    
    # 获取列名
    columns = [desc[0] for desc in c.description]
    conv_dict = dict(zip(columns, conv))
    conv_id = conv_dict["id"]
    
    # 获取消息列表
    offset = (page - 1) * limit
    c.execute("""
        SELECT * FROM msg_items
        WHERE conversation_id = ?
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """, (conv_id, limit, offset))
    rows = c.fetchall()
    msg_columns = [desc[0] for desc in c.description]
    messages = [dict(zip(msg_columns, row)) for row in rows] if rows else []
    
    # 标记用户已读
    c.execute("UPDATE msg_conversations SET unread_user = 0 WHERE id = ?", (conv_id,))
    conn.commit()
    conn.close()

    return {
        "status": "success",
        "data": {
            "messages": list(reversed(messages)),
            "unread": conv_dict.get("unread_user", 0)
        }
    }


@router.post("/api/user/messages/send")
def user_send_message(data: UserSendMessageModel, request: Request):
    """用户发送消息给管理员"""
    req_user = request.session.get("req_user")
    if not req_user:
        log_msg("[消息中心] user_send_message: 未登录")
        return {"status": "error", "message": "未登录"}

    user_id = req_user.get("Id")
    username = req_user.get("Name", "用户")
    
    # 检查 Emby 账号是否仍然存在
    if not _check_user_exists(user_id):
        log_msg(f"[消息中心] user_send_message: 用户 {user_id} 的 Emby 账号已被删除")
        request.session.pop("req_user", None)
        return {"status": "error", "message": "账号已被删除，请重新登录", "account_deleted": True}
    
    # 检查是否被禁言
    is_muted, mute_info = _is_user_muted(user_id)
    if is_muted:
        reason = mute_info.get("muted_reason", "") if mute_info else ""
        until = mute_info.get("muted_until", "") if mute_info else ""
        msg = "您已被禁言，无法发送消息"
        if reason:
            msg += f"，原因：{reason}"
        if until:
            msg += f"，解禁时间：{until}"
        else:
            msg += "（永久禁言）"
        return {"status": "error", "message": msg}
    
    log_msg(f"[消息中心] user_send_message: 用户 {username}({user_id}) 发送消息: {data.content[:50]}...")
    
    # 确保消息表存在
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS msg_conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        username TEXT,
        user_avatar TEXT,
        last_message TEXT,
        last_time DATETIME DEFAULT CURRENT_TIMESTAMP,
        unread_admin INTEGER DEFAULT 0,
        unread_user INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS msg_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id INTEGER,
        sender_type TEXT DEFAULT 'admin',
        sender_id TEXT,
        sender_name TEXT,
        content TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    
    # 获取用户头像
    try:
        c.execute("SELECT avatar FROM local_users WHERE emby_user_id = ?", (user_id,))
        row = c.fetchone()
        user_avatar = row[0] if row and row[0] else None
    except:
        user_avatar = None

    # 查找或创建会话
    c.execute("SELECT * FROM msg_conversations WHERE user_id = ?", (user_id,))
    conv = c.fetchone()
    if not conv:
        c.execute("""
            INSERT INTO msg_conversations (user_id, username, user_avatar, created_at, last_time)
            VALUES (?, ?, ?, datetime('now','localtime'), datetime('now','localtime'))
        """, (user_id, username, user_avatar))
        conv_id = c.lastrowid
        log_msg(f"[消息中心] user_send_message: 创建新会话 conv_id={conv_id}")
    else:
        conv_id = conv[0]  # id 是第一列
        log_msg(f"[消息中心] user_send_message: 找到已有会话 conv_id={conv_id}")

    # 插入消息
    c.execute("""
        INSERT INTO msg_items (conversation_id, sender_type, sender_id, sender_name, content, created_at)
        VALUES (?, 'user', ?, ?, ?, datetime('now','localtime'))
    """, (conv_id, user_id, username, sanitize_html(data.content, max_length=5000)))
    c.execute("""
        UPDATE msg_conversations SET last_message = ?, last_time = datetime('now','localtime'), unread_admin = unread_admin + 1
        WHERE id = ?
    """, (sanitize_html(data.content[:100]), conv_id))
    
    # 创建系统通知给管理员（检查是否屏蔽）
    try:
        c.execute("SELECT id FROM msg_notify_block WHERE user_id = ?", (user_id,))
        if not c.fetchone():  # 未屏蔽
            c.execute("""
                INSERT INTO sys_notifications (type, title, message, action_url, created_at)
                VALUES ('message', ?, ?, ?, datetime('now','localtime'))
            """, ("新消息", sanitize_html(f"用户 {username} 发来新消息"), f"/messages?user={user_id}"))
    except:
        pass  # 如果表不存在就忽略
    
    conn.commit()
    conn.close()
    
    # 🔥 发送机器人通知给管理员
    _send_bot_notify_for_user_message(user_id, username, data.content, conv_id)
    
    log_msg(f"[消息中心] user_send_message: 消息发送成功")

    return {"status": "success", "message": "发送成功"}


@router.get("/api/user/messages/unread")
def user_get_unread(request: Request):
    """用户获取自己的未读消息数"""
    req_user = request.session.get("req_user")
    if not req_user:
        return {"status": "error", "message": "未登录"}

    user_id = req_user.get("Id")
    
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        c.execute("SELECT unread_user FROM msg_conversations WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        conn.close()
        return {"status": "success", "count": row[0] if row else 0}
    except:
        return {"status": "success", "count": 0}


@router.get("/api/user/mute_status")
def user_get_mute_status(request: Request):
    """用户获取自己的禁言状态"""
    req_user = request.session.get("req_user")
    if not req_user:
        return {"status": "error", "message": "未登录"}

    user_id = req_user.get("Id")
    is_muted, mute_info = _is_user_muted(user_id)
    
    result = {"is_muted": is_muted}
    if is_muted and mute_info:
        result["reason"] = mute_info.get("muted_reason", "")
        result["until"] = mute_info.get("muted_until", "")
    
    return {"status": "success", "data": result}


# ==================== 消息通知屏蔽 API ====================

@router.get("/api/messages/notify_block")
def get_notify_block_list(request: Request):
    """获取屏蔽通知的用户列表"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    _ensure_msg_tables()
    
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT b.id, b.user_id, c.username, c.user_avatar, b.created_at
        FROM msg_notify_block b
        LEFT JOIN msg_conversations c ON b.user_id = c.user_id
        ORDER BY b.created_at DESC
    """)
    rows = c.fetchall()
    conn.close()
    
    blocked = [dict(row) for row in rows] if rows else []
    # 设置头像代理
    for b in blocked:
        if not b.get("user_avatar"):
            b["user_avatar"] = f"/api/proxy/user_image/{b['user_id']}"
    
    return {"status": "success", "data": blocked}


@router.post("/api/messages/notify_block/{user_id}")
def block_notify(user_id: str, request: Request):
    """屏蔽用户的消息通知"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    _ensure_msg_tables()
    
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    # 检查是否已屏蔽
    c.execute("SELECT id FROM msg_notify_block WHERE user_id = ?", (user_id,))
    if c.fetchone():
        conn.close()
        return {"status": "success", "message": "已屏蔽"}
    
    c.execute("INSERT INTO msg_notify_block (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()
    
    return {"status": "success", "message": "已屏蔽该用户的消息通知"}


@router.delete("/api/messages/notify_block/{user_id}")
def unblock_notify(user_id: str, request: Request):
    """取消屏蔽用户的消息通知"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    _ensure_msg_tables()
    
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM msg_notify_block WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    
    return {"status": "success", "message": "已取消屏蔽"}


# ==================== 用户禁言 API ====================

class MuteUserModel(BaseModel):
    user_id: str
    username: Optional[str] = None
    duration: Optional[int] = None  # 禁言时长(小时)，None=永久
    reason: Optional[str] = None

class BatchMuteModel(BaseModel):
    user_ids: list
    duration: Optional[int] = None
    reason: Optional[str] = None

class UnmuteModel(BaseModel):
    user_ids: list


def _ensure_mute_table():
    """确保禁言表存在"""
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS user_mutes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        username TEXT,
        is_muted INTEGER DEFAULT 1,
        muted_until TEXT,
        muted_reason TEXT,
        muted_by TEXT,
        muted_by_name TEXT,
        muted_at TEXT DEFAULT CURRENT_TIMESTAMP,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id)
    )''')
    conn.commit()
    conn.close()


def _is_user_muted(user_id: str) -> tuple:
    """检查用户是否被禁言，返回 (is_muted, mute_info)"""
    _ensure_mute_table()
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM user_mutes WHERE user_id = ? AND is_muted = 1", (user_id,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        return False, None
    
    mute_info = dict(row)
    # 检查是否过期
    if mute_info.get("muted_until"):
        from datetime import datetime
        try:
            until = datetime.strptime(mute_info["muted_until"], "%Y-%m-%d %H:%M:%S")
            if datetime.now() > until:
                # 已过期，自动解禁
                _unmute_user(user_id)
                return False, None
        except:
            pass
    
    return True, mute_info


def _unmute_user(user_id: str):
    """解除用户禁言"""
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE user_mutes SET is_muted = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def _get_user_info(user_id: str) -> dict:
    """获取用户信息（头像、备注）"""
    info = {"avatar": f"/api/proxy/user_image/{user_id}", "remark": ""}
    
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        # 从 local_users 获取备注
        c.execute("SELECT remark FROM local_users WHERE emby_user_id = ?", (user_id,))
        row = c.fetchone()
        if row and row["remark"]:
            info["remark"] = row["remark"]
        # 从 users_meta 获取备注
        if not info["remark"]:
            c.execute("SELECT remark FROM users_meta WHERE user_id = ?", (user_id,))
            row = c.fetchone()
            if row and row["remark"]:
                info["remark"] = row["remark"]
        conn.close()
    except:
        pass
    
    return info


@router.get("/api/messages/mutes")
def get_mute_list(request: Request, page: int = 1, limit: int = 20):
    """获取禁言用户列表"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    _ensure_mute_table()
    
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # 查询禁言用户
    offset = (page - 1) * limit
    c.execute("""
        SELECT * FROM user_mutes 
        WHERE is_muted = 1 
        ORDER BY muted_at DESC 
        LIMIT ? OFFSET ?
    """, (limit, offset))
    rows = c.fetchall()
    
    # 查询总数
    c.execute("SELECT COUNT(*) as cnt FROM user_mutes WHERE is_muted = 1")
    total = c.fetchone()["cnt"]
    conn.close()
    
    mutes = []
    for row in rows:
        mute = dict(row)
        # 获取用户信息
        user_info = _get_user_info(mute["user_id"])
        mute["user_avatar"] = user_info["avatar"]
        mute["user_remark"] = user_info["remark"]
        mutes.append(mute)
    
    return {
        "status": "success",
        "data": mutes,
        "total": total,
        "page": page,
        "limit": limit
    }


@router.post("/api/messages/mute")
def mute_user(data: MuteUserModel, request: Request):
    """禁言用户"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    _ensure_mute_table()
    
    admin_id = user.get("Id", "")
    admin_name = user.get("Name", "管理员")
    
    # 计算禁言到期时间
    muted_until = None
    if data.duration and data.duration > 0:
        from datetime import datetime, timedelta
        until = datetime.now() + timedelta(hours=data.duration)
        muted_until = until.strftime("%Y-%m-%d %H:%M:%S")
    
    # 获取用户名
    username = data.username
    if not username:
        try:
            if media_api:
                user_info = media_api.get(f"/Users/{data.user_id}")
                if user_info and user_info.status_code == 200:
                    username = user_info.json().get("Name", data.user_id)
        except:
            pass
        if not username:
            username = data.user_id
    
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    
    # 检查是否已存在
    c.execute("SELECT id FROM user_mutes WHERE user_id = ?", (data.user_id,))
    if c.fetchone():
        # 更新
        c.execute("""
            UPDATE user_mutes SET 
                is_muted = 1,
                username = ?,
                muted_until = ?,
                muted_reason = ?,
                muted_by = ?,
                muted_by_name = ?,
                muted_at = datetime('now','localtime')
            WHERE user_id = ?
        """, (username, muted_until, sanitize_html(data.reason) if data.reason else "", admin_id, admin_name, data.user_id))
    else:
        # 新增
        c.execute("""
            INSERT INTO user_mutes (user_id, username, is_muted, muted_until, muted_reason, muted_by, muted_by_name, muted_at)
            VALUES (?, ?, 1, ?, ?, ?, ?, datetime('now','localtime'))
        """, (data.user_id, username, muted_until, sanitize_html(data.reason) if data.reason else "", admin_id, admin_name))
    
    conn.commit()
    conn.close()
    
    return {"status": "success", "message": "禁言成功"}


@router.post("/api/messages/mute/batch")
def batch_mute_users(data: BatchMuteModel, request: Request):
    """批量禁言用户"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    if not data.user_ids:
        return {"status": "error", "message": "未选择用户"}
    
    _ensure_mute_table()
    
    admin_id = user.get("Id", "")
    admin_name = user.get("Name", "管理员")
    
    # 计算禁言到期时间
    muted_until = None
    if data.duration and data.duration > 0:
        from datetime import datetime, timedelta
        until = datetime.now() + timedelta(hours=data.duration)
        muted_until = until.strftime("%Y-%m-%d %H:%M:%S")
    
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    
    success_count = 0
    for user_id in data.user_ids:
        # 获取用户名
        username = user_id
        try:
            if media_api:
                user_info = media_api.get(f"/Users/{user_id}")
                if user_info and user_info.status_code == 200:
                    username = user_info.json().get("Name", user_id)
        except:
            pass
        
        # 检查是否已存在
        c.execute("SELECT id FROM user_mutes WHERE user_id = ?", (user_id,))
        if c.fetchone():
            c.execute("""
                UPDATE user_mutes SET 
                    is_muted = 1,
                    username = ?,
                    muted_until = ?,
                    muted_reason = ?,
                    muted_by = ?,
                    muted_by_name = ?,
                    muted_at = datetime('now','localtime')
                WHERE user_id = ?
            """, (username, muted_until, sanitize_html(data.reason) if data.reason else "", admin_id, admin_name, user_id))
        else:
            c.execute("""
                INSERT INTO user_mutes (user_id, username, is_muted, muted_until, muted_reason, muted_by, muted_by_name, muted_at)
                VALUES (?, ?, 1, ?, ?, ?, ?, datetime('now','localtime'))
            """, (user_id, username, muted_until, sanitize_html(data.reason) if data.reason else "", admin_id, admin_name))
        success_count += 1
    
    conn.commit()
    conn.close()
    
    return {"status": "success", "message": f"成功禁言 {success_count} 个用户"}


@router.post("/api/messages/unmute")
def unmute_users(data: UnmuteModel, request: Request):
    """批量解除禁言"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    if not data.user_ids:
        return {"status": "error", "message": "未选择用户"}
    
    _ensure_mute_table()
    
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    
    placeholders = ",".join(["?" for _ in data.user_ids])
    c.execute(f"UPDATE user_mutes SET is_muted = 0 WHERE user_id IN ({placeholders})", data.user_ids)
    
    conn.commit()
    conn.close()
    
    return {"status": "success", "message": f"成功解除 {len(data.user_ids)} 个用户的禁言"}


@router.delete("/api/messages/mute/{user_id}")
def unmute_single_user(user_id: str, request: Request):
    """解除单个用户的禁言"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    _ensure_mute_table()
    
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE user_mutes SET is_muted = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    
    return {"status": "success", "message": "已解除禁言"}


@router.get("/api/messages/mute/check/{user_id}")
def check_mute_status(user_id: str, request: Request):
    """检查用户禁言状态（管理端）"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    is_muted, mute_info = _is_user_muted(user_id)
    
    return {
        "status": "success",
        "is_muted": is_muted,
        "mute_info": mute_info
    }


# ==================== 公告管理 API ====================

class AnnouncementModel(BaseModel):
    title: str
    content: str
    is_active: bool = True
    priority: int = 0  # 优先级，数字越大越靠前

class AnnouncementUpdateModel(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    is_active: Optional[bool] = None
    priority: Optional[int] = None


def _ensure_announcement_table():
    """确保公告表存在"""
    # 🔥 确保数据库目录存在
    db_dir = os.path.dirname(SYSTEM_DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS announcements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        is_active INTEGER DEFAULT 1,
        priority INTEGER DEFAULT 0,
        view_count INTEGER DEFAULT 0,
        created_by TEXT,
        created_by_name TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    # 🔥 用户公告已读记录表
    c.execute('''CREATE TABLE IF NOT EXISTS announcement_reads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        announcement_id INTEGER NOT NULL,
        user_id TEXT NOT NULL,
        read_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(announcement_id, user_id)
    )''')
    conn.commit()
    conn.close()


@router.get("/api/announcements")
def get_announcements(request: Request, active_only: bool = False):
    """获取公告列表（管理端）"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    _ensure_announcement_table()
    
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    if active_only:
        c.execute("""
            SELECT * FROM announcements 
            WHERE is_active = 1 
            ORDER BY priority DESC, created_at DESC
        """)
    else:
        c.execute("""
            SELECT * FROM announcements 
            ORDER BY is_active DESC, priority DESC, created_at DESC
        """)
    rows = c.fetchall()
    conn.close()
    
    announcements = [dict(row) for row in rows] if rows else []
    return {"status": "success", "data": announcements}


@router.post("/api/announcements")
def create_announcement(data: AnnouncementModel, request: Request):
    """创建公告"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    _ensure_announcement_table()
    
    admin_id = user.get("Id", "")
    admin_name = user.get("Name", "管理员")
    
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO announcements (title, content, is_active, priority, created_by, created_by_name, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now','localtime'), datetime('now','localtime'))
    """, (sanitize_html(data.title), sanitize_rich_html(data.content, max_length=50000), 1 if data.is_active else 0, data.priority, admin_id, admin_name))
    conn.commit()
    ann_id = c.lastrowid
    conn.close()
    
    return {"status": "success", "message": "公告创建成功", "id": ann_id}


@router.put("/api/announcements/{ann_id}")
def update_announcement(ann_id: int, data: AnnouncementUpdateModel, request: Request):
    """更新公告"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    _ensure_announcement_table()
    
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    
    # 构建更新语句
    updates = []
    params = []
    if data.title is not None:
        updates.append("title = ?")
        params.append(sanitize_html(data.title))
    if data.content is not None:
        updates.append("content = ?")
        params.append(sanitize_rich_html(data.content, max_length=50000))
    if data.is_active is not None:
        updates.append("is_active = ?")
        params.append(1 if data.is_active else 0)
    if data.priority is not None:
        updates.append("priority = ?")
        params.append(data.priority)
    
    if not updates:
        conn.close()
        return {"status": "error", "message": "无更新内容"}
    
    updates.append("updated_at = datetime('now','localtime')")
    params.append(ann_id)
    
    c.execute(f"UPDATE announcements SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()
    
    return {"status": "success", "message": "公告更新成功"}


@router.delete("/api/announcements/{ann_id}")
def delete_announcement(ann_id: int, request: Request):
    """删除公告"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    _ensure_announcement_table()
    
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM announcements WHERE id = ?", (ann_id,))
    conn.commit()
    conn.close()
    
    return {"status": "success", "message": "公告删除成功"}


@router.post("/api/announcements/{ann_id}/view")
def increment_announcement_view(ann_id: int, request: Request):
    """增加公告浏览次数"""
    user = request.session.get("user") or request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "请先登录"}

    _ensure_announcement_table()
    
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE announcements SET view_count = view_count + 1 WHERE id = ?", (ann_id,))
    conn.commit()
    conn.close()
    
    return {"status": "success"}


# ==================== 用户端公告 API ====================

@router.get("/api/user/announcements")
def user_get_announcements(request: Request):
    """用户获取启用的公告列表"""
    # 🔒 安全检查（支持管理端和用户端）
    user = request.session.get("user") or request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "请先登录"}
    
    user_id = user.get('Id', '')
    _ensure_announcement_table()
    
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # 获取所有启用的公告
    c.execute("""
        SELECT id, title, content, view_count, created_at 
        FROM announcements 
        WHERE is_active = 1 
        ORDER BY priority DESC, created_at DESC
    """)
    rows = c.fetchall()
    
    # 获取用户已读的公告ID
    c.execute("SELECT announcement_id FROM announcement_reads WHERE user_id = ?", (user_id,))
    read_ids = set(row[0] for row in c.fetchall())
    conn.close()
    
    announcements = []
    for row in rows:
        ann = dict(row)
        ann['is_new'] = ann['id'] not in read_ids  # 标记是否未读
        announcements.append(ann)
    
    return {"status": "success", "data": announcements}


@router.post("/api/user/announcements/{ann_id}/read")
def mark_announcement_read(ann_id: int, request: Request):
    """标记公告为已读"""
    user = request.session.get("user") or request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "请先登录"}
    
    user_id = user.get('Id', '')
    _ensure_announcement_table()
    
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    # 使用 INSERT OR IGNORE 避免重复插入
    c.execute("""
        INSERT OR IGNORE INTO announcement_reads (announcement_id, user_id, read_at)
        VALUES (?, ?, datetime('now','localtime'))
    """, (ann_id, user_id))
    conn.commit()
    conn.close()
    
    return {"status": "success", "message": "已标记为已读"}


# ==================== 机器人消息通知 ====================

def _send_bot_notify_for_user_message(user_id: str, username: str, content: str, conv_id: int):
    """用户发消息时，发送机器人通知给管理员"""
    try:
        from app.core.config import cfg
        from app.services.bot_service import bot
        
        # 检查是否启用机器人消息通知
        if not cfg.get("msg_bot_notify_enabled", True):
            return
        
        # 检查该用户是否被屏蔽通知
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id FROM msg_notify_block WHERE user_id = ?", (user_id,))
        if c.fetchone():
            conn.close()
            return
        conn.close()
        
        # 获取用户备注
        user_display = username
        try:
            conn = sqlite3.connect(SYSTEM_DB_PATH)
            c = conn.cursor()
            c.execute("SELECT remark FROM local_users WHERE emby_user_id = ?", (user_id,))
            row = c.fetchone()
            if row and row[0]:
                user_display = f"{row[0]} ({username})"
            conn.close()
        except:
            pass
        
        # 构建通知消息
        text = f"💬 <b>新消息</b>\n\n"
        text += f"👤 用户：{user_display}\n"
        text += f"📝 内容：{content[:200]}{'...' if len(content) > 200 else ''}\n"
        text += f"🆔 用户ID：<code>{user_id}</code>"
        
        # 添加快捷回复按钮
        reply_markup = {
            "inline_keyboard": [
                [
                    {
                        "text": "💬 回复消息",
                        "callback_data": f"msg_reply:{user_id}"
                    }
                ],
                [
                    {
                        "text": "🚫 屏蔽通知",
                        "callback_data": f"msg_block:{user_id}"
                    }
                ]
            ]
        }
        
        # 如果配置了 base_url，添加查看详情按钮
        base_url = cfg.get("base_url", "").strip()
        if base_url:
            reply_markup["inline_keyboard"][0].append({
                "text": "🔗 查看详情",
                "url": f"{base_url}/messages?user={user_id}"
            })
        
        # 发送通知
        bot.send_message("sys_notify", text, reply_markup=reply_markup, platform="all")
        log_msg(f"[消息中心] 已发送机器人通知: 用户 {username} 的消息")
        
    except Exception as e:
        log_msg(f"[消息中心] 发送机器人通知失败: {e}")


def _send_bot_reply_to_user(user_id: str, content: str, admin_name: str = "管理员"):
    """管理员通过机器人回复用户"""
    try:
        from app.core.config import cfg
        from app.services.user_bot_service import user_bot
        
        # 检查用户机器人是否启用
        if not cfg.get("tg_user_bot_token"):
            return False
        
        # 查找用户的 TG ID
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        c.execute("SELECT tg_id FROM tg_bot_users WHERE emby_user_id = ?", (user_id,))
        row = c.fetchone()
        conn.close()
        
        if not row or not row[0]:
            log_msg(f"[消息中心] 用户 {user_id} 未绑定 TG 机器人")
            return False
        
        tg_id = row[0]
        
        # 发送消息给用户
        text = f"💌 <b>管理员回复</b>\n\n{content}"
        user_bot.send_message(tg_id, text)
        log_msg(f"[消息中心] 已通过 TG 机器人回复用户 {user_id}")
        return True
        
    except Exception as e:
        log_msg(f"[消息中心] 机器人回复失败: {e}")
        return False


# ==================== 机器人消息配置 API ====================

class MsgBotConfigModel(BaseModel):
    enabled: bool = True
    reply_via_bot: bool = False  # 是否通过用户机器人回复用户


@router.get("/api/messages/bot_config")
def get_msg_bot_config(request: Request):
    """获取消息机器人配置"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    from app.core.config import cfg
    return {
        "status": "success",
        "data": {
            "enabled": cfg.get("msg_bot_notify_enabled", True),
            "reply_via_bot": cfg.get("msg_bot_reply_enabled", False),
            "user_bot_configured": bool(cfg.get("tg_user_bot_token"))
        }
    }


@router.post("/api/messages/bot_config")
def set_msg_bot_config(data: MsgBotConfigModel, request: Request):
    """设置消息机器人配置"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    from app.core.config import cfg
    cfg.set("msg_bot_notify_enabled", data.enabled)
    cfg.set("msg_bot_reply_enabled", data.reply_via_bot)
    
    return {"status": "success", "message": "配置已保存"}


# ==================== 删除对话 API ====================

@router.delete("/api/messages/conversation/{user_id}")
def delete_conversation(user_id: str, request: Request):
    """删除与某用户的对话"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    _ensure_msg_tables()
    
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    
    try:
        # 获取会话 ID
        c.execute("SELECT id FROM msg_conversations WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        
        if row:
            conv_id = row[0]
            # 删除消息
            c.execute("DELETE FROM msg_items WHERE conversation_id = ?", (conv_id,))
            # 删除会话
            c.execute("DELETE FROM msg_conversations WHERE id = ?", (conv_id,))
            conn.commit()
            conn.close()
            return {"status": "success", "message": "对话已删除"}
        else:
            conn.close()
            return {"status": "error", "message": "对话不存在"}
    except Exception as e:
        conn.close()
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": safe_error_message(e, "删除失败")}


@router.delete("/api/messages/conversations/all")
def delete_all_conversations(request: Request):
    """清空所有对话"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    _ensure_msg_tables()
    
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    
    try:
        # 删除所有消息
        c.execute("DELETE FROM msg_items")
        # 删除所有会话
        c.execute("DELETE FROM msg_conversations")
        conn.commit()
        conn.close()
        return {"status": "success", "message": "所有对话已清空"}
    except Exception as e:
        conn.close()
        return {"status": "error", "message": f"清空失败: {e}"}


# ==================== 群发消息 ====================

class BroadcastModel(BaseModel):
    user_ids: list
    content: str


@router.post("/api/messages/broadcast")
def broadcast_message(data: BroadcastModel, request: Request):
    """群发消息给多个用户"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    
    if not data.user_ids:
        return {"status": "error", "message": "请选择至少一个用户"}
    
    if not data.content or not data.content.strip():
        return {"status": "error", "message": "消息内容不能为空"}
    
    _ensure_msg_tables()
    
    admin_name = user.get("Name", "管理员")
    admin_id = user.get("Id", "")
    content = sanitize_html(data.content.strip(), max_length=5000)
    
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    
    success_count = 0
    failed_count = 0
    
    for user_id in data.user_ids:
        try:
            # 获取用户名
            username = user_id
            try:
                if media_api and media_api.host and media_api.api_key:
                    user_res = media_api.get(f"/Users/{user_id}", timeout=5)
                    if user_res.status_code == 200:
                        username = user_res.json().get("Name", user_id)
            except:
                pass
            
            # 查找或创建会话
            c.execute("SELECT id FROM msg_conversations WHERE user_id = ?", (user_id,))
            conv = c.fetchone()
            
            if not conv:
                # 创建新会话
                c.execute("""
                    INSERT INTO msg_conversations (user_id, username, user_avatar, created_at, last_time)
                    VALUES (?, ?, '', datetime('now','localtime'), datetime('now','localtime'))
                """, (user_id, username))
                conv_id = c.lastrowid
            else:
                conv_id = conv[0]
            
            # 插入消息
            c.execute("""
                INSERT INTO msg_items (conversation_id, sender_type, sender_id, sender_name, content, created_at)
                VALUES (?, 'admin', ?, ?, ?, datetime('now','localtime'))
            """, (conv_id, admin_id, admin_name, content))
            
            # 更新会话
            c.execute("""
                UPDATE msg_conversations 
                SET last_message = ?, last_time = datetime('now','localtime'), unread_user = unread_user + 1
                WHERE id = ?
            """, (content[:100], conv_id))
            
            success_count += 1
        except Exception as e:
            log_msg(f"[群发消息] 发送给 {user_id} 失败: {e}")
            failed_count += 1
    
    conn.commit()
    conn.close()
    
    # 发送机器人通知
    if success_count > 0:
        log_msg(f"[群发消息] 成功发送给 {success_count} 个用户")
    
    return {
        "status": "success",
        "message": f"成功发送给 {success_count} 个用户" + (f"，{failed_count} 个失败" if failed_count > 0 else ""),
        "success_count": success_count,
        "failed_count": failed_count
    }
