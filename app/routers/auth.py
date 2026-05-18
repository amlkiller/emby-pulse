# -*- coding: utf-8 -*-
"""
本地用户认证路由
支持混合登录模式：Emby 账号 + 本地账号
支持子账号权限控制
"""

import bcrypt
import datetime
import json
import secrets
import base64
import time
import logging
import re
import os
from io import BytesIO
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from app.core.database import query_db, SYSTEM_DB_PATH
from app.core.config import cfg

from app.core.security_utils import sanitize_html, safe_error_message
from app.core.security import validate_password_strength
import sqlite3


logger = logging.getLogger("uvicorn")

# TOTP 两步验证
try:
    import pyotp
    import qrcode
    TOTP_AVAILABLE = True
except ImportError:
    TOTP_AVAILABLE = False
    print("[警告] pyotp 或 qrcode 未安装，两步验证功能不可用")

router = APIRouter()

# ==================== 登录失败锁定机制（数据库持久化） ====================

_LOGIN_MAX_FAILURES = 5  # 最大失败次数
_LOGIN_LOCK_DURATION = 300  # 锁定时长（秒）= 5分钟

def _check_login_locked(lock_key: str) -> tuple:
    """检查是否被锁定，返回 (is_locked, remaining_seconds)
    
    Args:
        lock_key: 锁定键（ip:xxx 或 user:xxx）
    """
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        c.execute("""
            SELECT locked_until, failure_count 
            FROM login_failures 
            WHERE lock_key = ?
        """, (lock_key,))
        
        row = c.fetchone()
        conn.close()
        
        if not row:
            return False, 0
        
        locked_until = row['locked_until']
        if locked_until:
            locked_timestamp = datetime.datetime.fromisoformat(locked_until).timestamp()
            if locked_timestamp > time.time():
                remaining = int(locked_timestamp - time.time())
                return True, remaining
        
        return False, 0
    except Exception as e:
        logger.error(f"[登录锁定] 检查失败: {e}")
        return False, 0

def _record_login_failure(lock_key: str, lock_type: str):
    """记录登录失败
    
    Args:
        lock_key: 锁定键（ip:xxx 或 user:xxx）
        lock_type: 锁定类型（ip 或 user）
    """
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        
        # 获取当前失败次数
        c.execute("SELECT failure_count FROM login_failures WHERE lock_key = ?", (lock_key,))
        row = c.fetchone()
        
        if row:
            failure_count = row[0] + 1
        else:
            failure_count = 1
        
        # 计算锁定时间
        locked_until = None
        if failure_count >= _LOGIN_MAX_FAILURES:
            locked_until = datetime.datetime.fromtimestamp(time.time() + _LOGIN_LOCK_DURATION).isoformat()
        
        # 更新或插入
        c.execute("""
            INSERT INTO login_failures (lock_key, lock_type, failure_count, locked_until, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(lock_key) DO UPDATE SET
                failure_count = excluded.failure_count,
                locked_until = excluded.locked_until,
                updated_at = CURRENT_TIMESTAMP
        """, (lock_key, lock_type, failure_count, locked_until))
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"[登录锁定] 记录失败: {e}")

def _clear_login_failure(lock_key: str):
    """登录成功，清除失败记录"""
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM login_failures WHERE lock_key = ?", (lock_key,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"[登录锁定] 清除失败: {e}")

def _get_remaining_attempts(lock_key: str) -> int:
    """获取剩余尝试次数"""
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        c.execute("SELECT failure_count FROM login_failures WHERE lock_key = ?", (lock_key,))
        row = c.fetchone()
        conn.close()
        
        if row:
            return max(0, _LOGIN_MAX_FAILURES - row[0])
        return _LOGIN_MAX_FAILURES
    except Exception as e:
        logger.error(f"[登录锁定] 获取剩余次数失败: {e}")
        return _LOGIN_MAX_FAILURES

def _cleanup_expired_locks():
    """清理过期的锁定记录（可定期调用）"""
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM login_failures WHERE locked_until IS NOT NULL AND locked_until < CURRENT_TIMESTAMP")
        deleted = c.rowcount
        conn.commit()
        conn.close()
        return deleted
    except Exception as e:
        logger.error(f"[登录锁定] 清理失败: {e}")
        return 0

# 定期清理过期锁定记录（每 10 分钟）
def _start_lock_cleanup():
    import threading
    def cleanup():
        _cleanup_expired_locks()
        timer = threading.Timer(600, cleanup)
        timer.daemon = True
        timer.start()
    cleanup()

_start_lock_cleanup()

# ==================== 权限常量 ====================

ALL_PERMISSIONS = [
    'dashboard', 'content', 'details', 'insight', 'gaps', 'dedupe', 'history',
    'requests_admin', 'users', 'points', 'risk', 'clients', 'calendar',
    'bot', 'tasks', 'report', 'settings', 'about', 'plugins', 'messages', 'mutes'
]

# 页面路由到权限 ID 的映射
PAGE_PERMISSION_MAP = {
    '/': 'dashboard',
    '/content': 'content',
    '/details': 'details',
    '/insight': 'insight',
    '/gaps': 'gaps',
    '/dedupe': 'dedupe',
    '/history': 'history',
    '/requests_admin': 'requests_admin',
    '/users_manage': 'users',
    '/users': 'users',
    '/points': 'points',
    '/risk': 'risk',
    '/clients': 'clients',
    '/calendar': 'calendar',
    '/bot': 'bot',
    '/tasks': 'tasks',
    '/report': 'report',
    '/settings': 'settings',
    '/system': 'settings',
    '/about': 'about',
    '/plugins': 'plugins',
    '/messages': 'messages',
    '/mutes': 'mutes',
}


def check_permission(request: Request, page: str) -> bool:
    """检查用户是否有访问某个页面的权限"""
    user = request.session.get("user", {})

    # Emby 账号或 admin 角色拥有全部权限
    if user.get("auth_type") == "emby" or user.get("role") == "admin":
        return True

    # 子账号检查权限
    permissions = user.get("permissions", [])
    if isinstance(permissions, str):
        try:
            permissions = json.loads(permissions)
        except:
            permissions = []

    if "all" in permissions:
        return True
    return page in permissions


def is_admin_user(request: Request) -> bool:
    """检查是否为 admin 或 Emby 账号（拥有完整管理权限）"""
    user = request.session.get("user", {})
    return user.get("auth_type") == "emby" or user.get("role") == "admin"


def get_current_user_id(request: Request) -> int:
    """获取当前登录的本地用户 ID"""
    user = request.session.get("user", {})
    if user.get("auth_type") == "local" and user.get("id"):
        return user.get("id")
    return None

# ==================== Pydantic Models ====================

class LocalUserCreate(BaseModel):
    username: str
    password: str
    role: str = "sub_admin"
    remark: str = ""
    permissions: list = []  # 权限列表

class LocalUserUpdate(BaseModel):
    remark: str = ""
    is_enabled: int = 1
    role: str = ""
    permissions: list = None  # 权限列表

class PasswordChange(BaseModel):
    new_password: str
    old_password: str = ""  # 用户修改自己密码时必填；管理员重置他人密码时可空

class PermissionsUpdate(BaseModel):
    permissions: list = []

class AuthSettingsUpdate(BaseModel):
    enable_local_auth: bool
    disable_emby_auth: bool = False  # 禁用 Emby 管理员登录


# ==================== 工具函数 ====================

def hash_password(password: str) -> str:
    """使用 bcrypt 哈希密码"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12)).decode('utf-8')

def verify_password(password: str, password_hash: str) -> bool:
    """验证密码"""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
    except:
        return False

def ensure_local_users_table():
    """确保 local_users 表存在且结构正确"""
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS local_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'admin',
            remark TEXT DEFAULT '',
            avatar TEXT DEFAULT '',
            is_enabled INTEGER DEFAULT 1,
            permissions TEXT DEFAULT '[]',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_login_at DATETIME,
            last_login_ip TEXT
        )''')
        # 检查列是否存在
        c.execute("PRAGMA table_info(local_users)")
        columns = [row[1] for row in c.fetchall()]
        if 'username' not in columns:
            c.execute("ALTER TABLE local_users ADD COLUMN username TEXT UNIQUE NOT NULL")
        if 'password_hash' not in columns:
            c.execute("ALTER TABLE local_users ADD COLUMN password_hash TEXT NOT NULL")
        if 'role' not in columns:
            c.execute("ALTER TABLE local_users ADD COLUMN role TEXT DEFAULT 'admin'")
        if 'remark' not in columns:
            c.execute("ALTER TABLE local_users ADD COLUMN remark TEXT DEFAULT ''")
        if 'avatar' not in columns:
            c.execute("ALTER TABLE local_users ADD COLUMN avatar TEXT DEFAULT ''")
        if 'is_enabled' not in columns:
            c.execute("ALTER TABLE local_users ADD COLUMN is_enabled INTEGER DEFAULT 1")
        if 'permissions' not in columns:
            c.execute("ALTER TABLE local_users ADD COLUMN permissions TEXT DEFAULT '[]'")
        if 'created_at' not in columns:
            c.execute("ALTER TABLE local_users ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP")
        if 'updated_at' not in columns:
            c.execute("ALTER TABLE local_users ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP")
        if 'last_login_at' not in columns:
            c.execute("ALTER TABLE local_users ADD COLUMN last_login_at DATETIME")
        if 'last_login_ip' not in columns:
            c.execute("ALTER TABLE local_users ADD COLUMN last_login_ip TEXT")
        if 'totp_secret' not in columns:
            c.execute("ALTER TABLE local_users ADD COLUMN totp_secret TEXT DEFAULT ''")  # TOTP 密钥
        if 'totp_enabled' not in columns:
            c.execute("ALTER TABLE local_users ADD COLUMN totp_enabled INTEGER DEFAULT 0")  # 是否启用 TOTP
        if 'totp_pending_secret' not in columns:
            c.execute("ALTER TABLE local_users ADD COLUMN totp_pending_secret TEXT DEFAULT ''")  # TOTP 待验证密钥
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[本地认证] 表结构检查失败: {e}")

# 启动时确保表存在
ensure_local_users_table()


# ==================== 环境变量初始化本地管理员 ====================

def ensure_env_local_admin():
    """
    从环境变量创建本地管理员账号
    支持在没有 Emby API 的情况下初始化系统

    环境变量：
    - LOCAL_AUTH_ENABLED: 启用本地认证
    - LOCAL_ADMIN_USERNAME: 管理员用户名
    - LOCAL_ADMIN_PASSWORD: 管理员密码
    """
    import os

    # 检查是否启用本地认证
    local_auth_enabled = os.getenv("LOCAL_AUTH_ENABLED", "").lower() in ("true", "1", "yes")
    admin_username = os.getenv("LOCAL_ADMIN_USERNAME", "").strip()
    admin_password = os.getenv("LOCAL_ADMIN_PASSWORD", "").strip()

    if not local_auth_enabled or not admin_username or not admin_password:
        return

    try:
        # 检查用户是否已存在
        existing = query_db("SELECT id FROM local_users WHERE username = ?", (admin_username,), one=True)

        if existing:
            # 用户已存在，更新密码（如果环境变量有设置）
            new_hash = hash_password(admin_password)
            query_db(
                "UPDATE local_users SET password_hash = ?, role = 'admin', is_enabled = 1, updated_at = ? WHERE username = ?",
                (new_hash, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), admin_username)
            )
            print(f"[本地认证] 环境变量管理员 '{admin_username}' 密码已更新")
        else:
            # 创建新管理员
            password_hash = hash_password(admin_password)
            query_db(
                "INSERT INTO local_users (username, password_hash, role, is_enabled, remark, permissions) VALUES (?, ?, 'admin', 1, '环境变量创建的管理员', '[]')",
                (admin_username, password_hash)
            )
            print(f"[本地认证] 环境变量管理员 '{admin_username}' 已创建")

        # 同时确保本地认证开关开启
        if not cfg.get("enable_local_auth", False):
            cfg.set("enable_local_auth", True)
            print("[本地认证] 已自动开启本地认证")

    except Exception as e:
        print(f"[本地认证] 环境变量创建管理员失败: {e}")


# 启动时检查环境变量并创建管理员
ensure_env_local_admin()


# ==================== 认证设置 API ====================

@router.get("/api/auth/settings")
async def get_auth_settings():
    """获取认证设置（公开 API，用于登录页面）"""
    enable_local = cfg.get("enable_local_auth", False)
    local_users_count = 0
    try:
        rows = query_db("SELECT COUNT(*) as cnt FROM local_users WHERE is_enabled = 1")
        local_users_count = rows[0]['cnt'] if rows else 0
    except:
        pass

    # 检查 Emby 是否配置（用于前端判断默认登录方式）
    emby_host = cfg.get("emby_host", "")
    emby_api_key = cfg.get("emby_api_key", "")
    emby_configured = bool(emby_host and emby_api_key)

    return {
        "status": "success",
        "data": {
            "enable_local_auth": enable_local,
            "disable_emby_auth": cfg.get("disable_emby_auth", False),  # 新增：是否禁用 Emby 认证
            "has_local_admin": local_users_count > 0,
            "emby_configured": emby_configured  # Emby 是否已配置
        }
    }


@router.post("/api/auth/settings")
async def save_auth_settings(request: Request, data: AuthSettingsUpdate):
    """保存认证设置（需要管理员权限）"""
    # 验证权限
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    # 获取当前配置
    current_disable_emby = cfg.get("disable_emby_auth", False)

    # 安全检查1：如果要禁用 Emby 认证，必须先有本地管理员账号
    if data.disable_emby_auth:
        # 检查本地认证是否开启
        if not data.enable_local_auth:
            return {"status": "error", "message": "禁用 Emby 认证前必须先开启本地认证"}
        # 检查是否有本地管理员
        local_users_count = 0
        try:
            rows = query_db("SELECT COUNT(*) as cnt FROM local_users WHERE is_enabled = 1 AND role = 'admin'")
            local_users_count = rows[0]['cnt'] if rows else 0
        except:
            pass
        if local_users_count == 0:
            return {"status": "error", "message": "禁用 Emby 认证前必须先创建本地管理员账号"}

    # 安全检查2：如果已禁用 Emby 认证，不允许关闭本地认证
    if current_disable_emby and not data.enable_local_auth:
        return {"status": "error", "message": "已禁用 Emby 登录，本地认证必须保持开启！两种登录模式至少保留一种。"}

    cfg.set("enable_local_auth", data.enable_local_auth)
    cfg.set("disable_emby_auth", data.disable_emby_auth)
    return {"status": "success", "message": "设置已保存"}


# ==================== 本地用户管理 API ====================

@router.get("/api/auth/local-users")
async def get_local_users(request: Request):
    """获取本地用户列表"""
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    rows = query_db("SELECT id, username, role, remark, avatar, is_enabled, permissions, created_at, updated_at, last_login_at, last_login_ip FROM local_users ORDER BY created_at DESC")

    # 解析 permissions JSON
    users = []
    for r in rows:
        user = dict(r)
        try:
            user['permissions'] = json.loads(user.get('permissions', '[]'))
        except:
            user['permissions'] = []
        users.append(user)

    return {
        "status": "success",
        "data": users
    }


@router.post("/api/auth/local-users")
async def create_local_user(request: Request, data: LocalUserCreate):
    """创建本地用户"""
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    # 验证用户名
    username = data.username.strip()
    if not username or len(username) < 3:
        return {"status": "error", "message": "用户名至少需要 3 个字符"}

    # 验证密码强度
    pw_valid, pw_error = validate_password_strength(data.password)
    if not pw_valid:
        return {"status": "error", "message": pw_error}

    # 验证角色
    if data.role not in ["admin", "sub_admin"]:
        return {"status": "error", "message": "角色必须是 admin 或 sub_admin"}

    # 检查用户名是否已存在
    existing = query_db("SELECT id FROM local_users WHERE username = ?", (username,), one=True)
    if existing:
        return {"status": "error", "message": "用户名已存在"}

    # 处理权限
    permissions_json = json.dumps(data.permissions) if data.permissions else "[]"

    # 创建用户
    password_hash = hash_password(data.password)
    try:
        query_db(
            "INSERT INTO local_users (username, password_hash, role, remark, permissions) VALUES (?, ?, ?, ?, ?)",
            (username, password_hash, data.role, sanitize_html(data.remark), permissions_json)
        )
        # 🔒 审计日志：创建用户
        from app.core.audit_logger import log_audit
        current_user = request.session.get("user", {})
        log_audit(
            action="user_create",
            user_id=str(current_user.get("id", "")),
            user_name=current_user.get("name", ""),
            ip_address=request.client.host if request.client else "",
            resource_type="user",
            details={"new_username": username, "role": data.role}
        )
        return {"status": "success", "message": "用户创建成功"}
    except Exception as e:
        logger.error(f"[创建用户失败] {str(e)}")
        return {"status": "error", "message": safe_error_message(e, "创建用户失败")}


@router.put("/api/auth/local-users/{user_id}")
async def update_local_user(request: Request, user_id: int, data: LocalUserUpdate):
    """更新本地用户信息"""
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    # 检查用户是否存在
    user = query_db("SELECT id FROM local_users WHERE id = ?", (user_id,), one=True)
    if not user:
        return {"status": "error", "message": "用户不存在"}

    # 构建更新语句
    updates = []
    params = []

    if data.remark is not None:
        updates.append("remark = ?")
        params.append(sanitize_html(data.remark))
    if data.is_enabled is not None:
        updates.append("is_enabled = ?")
        params.append(data.is_enabled)
    if data.role:
        if data.role not in ["admin", "sub_admin"]:
            return {"status": "error", "message": "无效的角色"}
        updates.append("role = ?")
        params.append(data.role)
    if data.permissions is not None:
        updates.append("permissions = ?")
        params.append(json.dumps(data.permissions))

    if not updates:
        return {"status": "error", "message": "没有要更新的内容"}

    updates.append("updated_at = ?")
    params.append(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    params.append(user_id)

    try:
        query_db(f"UPDATE local_users SET {', '.join(updates)} WHERE id = ?", params)
        # 🔒 审计日志：更新用户
        from app.core.audit_logger import log_audit
        current_user = request.session.get("user", {})
        log_audit(
            action="user_update",
            user_id=str(current_user.get("id", "")),
            user_name=current_user.get("name", ""),
            ip_address=request.client.host if request.client else "",
            resource_type="user",
            resource_id=str(user_id),
            details={"updated_fields": updates}
        )
        return {"status": "success", "message": "更新成功"}
    except Exception as e:
        logger.error(f"[更新用户失败] {str(e)}")
        return {"status": "error", "message": "更新失败"}


@router.put("/api/auth/local-users/{user_id}/password")
async def change_local_user_password(request: Request, user_id: int, data: PasswordChange):
    """修改本地用户密码 - 子账号只能修改自己的密码"""
    current_user = request.session.get("user", {})
    current_user_id = get_current_user_id(request)

    # 子账号只能修改自己的密码
    if not is_admin_user(request):
        if current_user_id != user_id:
            return {"status": "error", "message": "子账号只能修改自己的密码"}

    # 🔒 旧密码验证：当用户修改自己的密码时强制校验
    # 管理员为他人重置密码时跳过（合理的平台能力），但仍写入审计日志
    is_self_change = (current_user_id == user_id)
    if is_self_change:
        if not data.old_password:
            return {"status": "error", "message": "请提供原密码"}
        existing = query_db(
            "SELECT password_hash FROM local_users WHERE id = ?",
            (user_id,), one=True
        )
        if not existing:
            return {"status": "error", "message": "用户不存在"}
        if not verify_password(data.old_password, existing['password_hash']):
            return {"status": "error", "message": "原密码不正确"}

    # 验证密码强度
    pw_valid, pw_error = validate_password_strength(data.new_password)
    if not pw_valid:
        return {"status": "error", "message": pw_error}

    # 检查用户是否存在
    user = query_db("SELECT id FROM local_users WHERE id = ?", (user_id,), one=True)
    if not user:
        return {"status": "error", "message": "用户不存在"}

    # 更新密码
    password_hash = hash_password(data.new_password)
    try:
        query_db(
            "UPDATE local_users SET password_hash = ?, updated_at = ? WHERE id = ?",
            (password_hash, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id)
        )
        # 🔒 审计日志：密码修改
        from app.core.audit_logger import log_audit
        current_user = request.session.get("user", {})
        log_audit(
            action="password_change",
            user_id=str(user_id),
            user_name=current_user.get("name", ""),
            ip_address=request.client.host if request.client else "",
            resource_type="user",
            resource_id=str(user_id)
        )
        return {"status": "success", "message": "密码修改成功"}
    except Exception as e:
        logger.error(f"[修改密码失败] {str(e)}")
        return {"status": "error", "message": "密码修改失败"}


@router.delete("/api/auth/local-users/{user_id}")
async def delete_local_user(request: Request, user_id: int):
    """删除本地用户 - 子账号不能删除账号"""
    if not is_admin_user(request):
        return {"status": "error", "message": "子账号无法删除用户"}

    # 检查用户是否存在
    user = query_db("SELECT id, username FROM local_users WHERE id = ?", (user_id,), one=True)
    if not user:
        return {"status": "error", "message": "用户不存在"}

    # 检查是否是最后一个管理员
    admin_count = query_db("SELECT COUNT(*) as cnt FROM local_users WHERE role = 'admin' AND is_enabled = 1")
    if admin_count and admin_count[0]['cnt'] <= 1:
        # 检查要删除的是否是这个管理员
        user_role = query_db("SELECT role FROM local_users WHERE id = ?", (user_id,), one=True)
        if user_role and user_role['role'] == 'admin':
            return {"status": "error", "message": "不能删除最后一个管理员账号"}

    try:
        query_db("DELETE FROM local_users WHERE id = ?", (user_id,))
        # 🔒 审计日志：删除用户
        from app.core.audit_logger import log_audit
        current_user = request.session.get("user", {})
        log_audit(
            action="user_delete",
            user_id=str(current_user.get("id", "")),
            user_name=current_user.get("name", ""),
            ip_address=request.client.host if request.client else "",
            resource_type="user",
            resource_id=str(user_id),
            details={"deleted_username": user['username']}
        )
        return {"status": "success", "message": "用户已删除"}
    except Exception as e:
        logger.error(f"[删除用户失败] {str(e)}")
        return {"status": "error", "message": "删除用户失败"}


class AvatarUpdate(BaseModel):
    avatar: str  # 头像 URL 或 base64


@router.get("/api/auth/avatar/{user_id}")
async def get_avatar(request: Request, user_id: int):
    """获取本地用户头像"""
    # 🔒 安全：需要登录才能访问
    session_user = request.session.get("user")
    if not session_user:
        return RedirectResponse("/static/img/logo-app.png")

    # 🔒 IDOR 防护：非管理员仅可访问自己的头像
    if not is_admin_user(request):
        own_id = get_current_user_id(request)
        try:
            own_id_int = int(own_id) if own_id is not None else None
        except (TypeError, ValueError):
            own_id_int = None
        if own_id_int != user_id:
            return RedirectResponse("/static/img/logo-app.png")

    try:
        user = query_db("SELECT avatar FROM local_users WHERE id = ?", (user_id,), one=True)
        if user and user['avatar']:
            # 返回头像数据（可能是 base64 或 URL）
            avatar = user['avatar']
            if avatar.startswith('data:image'):
                # base64 数据，返回原始数据
                from fastapi.responses import Response
                # 解析 base64
                import base64
                header, data = avatar.split(',', 1)
                # 获取 mime 类型
                mime = 'image/jpeg'
                if 'image/png' in header:
                    mime = 'image/png'
                elif 'image/gif' in header:
                    mime = 'image/gif'
                return Response(content=base64.b64decode(data), media_type=mime)
            else:
                # 仅允许相对路径重定向，防止 Open Redirect
                if avatar.startswith('/') and not avatar.startswith('//'):
                    return RedirectResponse(avatar)
                else:
                    return RedirectResponse("/static/img/logo-app.png")
        # 返回默认头像
        return RedirectResponse("/static/img/logo-app.png")
    except Exception as e:
        return RedirectResponse("/static/img/logo-app.png")


@router.post("/api/auth/avatar")
async def update_avatar(request: Request, data: AvatarUpdate):
    """更新当前用户头像 - 仅本地账号支持"""
    user = request.session.get("user", {})
    user_id = get_current_user_id(request)

    # 只有本地账号可以修改头像
    if user.get("auth_type") != "local" or not user_id:
        return {"status": "error", "message": "Emby 账号暂不支持设置头像，请在 Emby 服务端修改"}

    # 严格校验：magic bytes + PIL 二次解析 + 剥离 EXIF 并重新编码
    from app.utils.image_validator import validate_base64_image
    try:
        safe_avatar = validate_base64_image(data.avatar, max_bytes=2 * 1024 * 1024)
    except ValueError as ve:
        return {"status": "error", "message": str(ve)}

    try:
        query_db(
            "UPDATE local_users SET avatar = ?, updated_at = ? WHERE id = ?",
            (safe_avatar, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id)
        )

        # 注意：头像数据存储在数据库中，不存储在 session 中（session 有大小限制）
        # 前端通过 /api/auth/avatar/{user_id} 获取头像

        return {"status": "success", "message": "头像更新成功"}
    except Exception as e:
        logging.error(f"[头像更新失败] {str(e)}")
        return {"status": "error", "message": safe_error_message(e, "更新失败")}


# ==================== 权限管理 API ====================

@router.get("/api/auth/permissions")
async def get_permissions_list(request: Request):
    """获取所有可用权限列表"""
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}
    return {
        "status": "success",
        "data": {
            "permissions": ALL_PERMISSIONS,
            "page_map": PAGE_PERMISSION_MAP
        }
    }


@router.put("/api/auth/local-users/{user_id}/permissions")
async def update_user_permissions(request: Request, user_id: int, data: PermissionsUpdate):
    """更新用户权限 - 仅 admin/Emby 可操作"""
    if not is_admin_user(request):
        return {"status": "error", "message": "需要管理员权限"}

    # 检查用户是否存在
    user = query_db("SELECT id, role FROM local_users WHERE id = ?", (user_id,), one=True)
    if not user:
        return {"status": "error", "message": "用户不存在"}

    # admin 角色自动拥有全部权限
    if user['role'] == 'admin':
        return {"status": "error", "message": "管理员账号自动拥有全部权限，无需设置"}

    # 验证权限列表
    invalid_perms = [p for p in data.permissions if p not in ALL_PERMISSIONS and p != "all"]
    if invalid_perms:
        return {"status": "error", "message": f"无效的权限: {', '.join(invalid_perms)}"}

    try:
        query_db(
            "UPDATE local_users SET permissions = ?, updated_at = ? WHERE id = ?",
            (json.dumps(data.permissions), datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id)
        )
        return {"status": "success", "message": "权限更新成功"}
    except Exception as e:
        logger.error(f"[更新权限失败] {str(e)}")
        return {"status": "error", "message": "权限更新失败"}


# ==================== 本地登录验证 ====================

def verify_local_user(username: str, password: str, client_ip: str = None, totp_code: str = ""):
    """
    验证本地用户登录
    返回: (success: bool, user_info: dict or error_message: str)
    """
    # 检查是否启用本地认证
    if not cfg.get("enable_local_auth", False):
        return False, "本地认证未启用"

    # 查询用户
    user = query_db(
        "SELECT id, username, password_hash, role, remark, avatar, is_enabled, permissions, totp_secret, totp_enabled FROM local_users WHERE username = ?",
        (username,),
        one=True
    )
    
    if not user:
        return False, "用户名或密码错误"

    # 🔒 用户枚举防护：禁用状态不能在密码校验前泄露，统一报"用户名或密码错误"
    if not user['is_enabled']:
        return False, "用户名或密码错误"

    # 验证密码
    if not verify_password(password, user['password_hash']):
        return False, "用户名或密码错误"
    
    # 验证 TOTP（如果启用）
    if user['totp_enabled'] and user['totp_secret']:
        if not TOTP_AVAILABLE:
            return False, "系统未安装 TOTP 支持，请联系管理员"
        if not totp_code:
            return False, "需要验证器验证码"
        # 验证 TOTP 验证码
        totp = pyotp.TOTP(user['totp_secret'])
        if not totp.verify(totp_code, valid_window=1):  # 允许前后 1 个时间窗口
            return False, "验证码错误或已过期"
    
    # 更新最后登录信息
    try:
        query_db(
            "UPDATE local_users SET last_login_at = ?, last_login_ip = ? WHERE id = ?",
            (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), client_ip, user['id'])
        )
    except:
        pass

    # 解析权限
    try:
        permissions = json.loads(user['permissions']) if user['permissions'] else []
    except:
        permissions = []

    # admin 角色才是真正的管理员
    is_admin = user['role'] == 'admin'

    # 头像使用代理 API（避免 session 大小限制）
    avatar_url = f"/api/auth/avatar/{user['id']}" if user['avatar'] else ""

    return True, {
        "id": user['id'],
        "name": user['username'],
        "is_admin": is_admin,
        "role": user['role'],
        "remark": user['remark'],
        "avatar": avatar_url,
        "auth_type": "local",
        "permissions": permissions
    }


# ==================== 登录 API（支持 Emby + 本地双模式） ====================

from pydantic import BaseModel as _BaseModel
import requests

class LoginModel(_BaseModel):
    username: str
    password: str
    auth_type: str = "emby"  # emby 或 local
    totp_code: str = ""  # TOTP 验证码（两步验证）

@router.post("/api/login")
async def api_login(data: LoginModel, request: Request):
    """
    统一登录 API - 支持 Emby 和本地账号双模式
    """
    from app.core.audit_logger import log_audit
    
    username = data.username.strip()
    password = data.password
    auth_type = data.auth_type
    
    # 🔒 端口隔离检查：使用服务器实际端口判断，防止 Host 头伪造
    _SERVER_PORT = int(os.getenv("PORT", "10307"))
    _USER_PORT = int(os.getenv("REQUEST_PORT", "10308"))
    server_port = request.url.port or _SERVER_PORT
    is_user_port = server_port == _USER_PORT

    # 如果从用户社区端口访问，拒绝后台登录
    if is_user_port and auth_type != "local":
        return {"status": "error", "message": "请从管理端口(10307)登录后台"}
    
    # 获取客户端 IP（复用可信代理逻辑，防止 XFF 伪造绕过锁定）
    from app.core.rate_limiter import get_client_ip
    client_ip = get_client_ip(request)
    
    user_agent = request.headers.get("user-agent", "")
    
    # 🔒 检查 IP 和用户名是否被锁定
    ip_key = f"ip:{client_ip}"
    user_key = f"user:{username}"
    
    # 检查 IP 锁定
    is_ip_locked, ip_remaining = _check_login_locked(ip_key)
    if is_ip_locked:
        log_audit("login_failed", user_name=username, ip_address=client_ip, user_agent=user_agent, details={"reason": "IP_locked"}, status="failed")
        return {
            "status": "error", 
            "message": f"登录失败次数过多，IP 已被锁定，请 {ip_remaining} 秒后重试",
            "locked": True,
            "remaining_seconds": ip_remaining
        }
    
    # 检查用户名锁定
    is_user_locked, user_remaining = _check_login_locked(user_key)
    if is_user_locked:
        log_audit("login_failed", user_name=username, ip_address=client_ip, user_agent=user_agent, details={"reason": "user_locked"}, status="failed")
        return {
            "status": "error", 
            "message": f"账号 {username} 已被锁定，请 {user_remaining} 秒后重试",
            "locked": True,
            "remaining_seconds": user_remaining
        }

    # 本地账号登录
    if auth_type == "local":
        success, result = verify_local_user(username, password, client_ip, data.totp_code)
        if success:
            # 🔒 登录成功，清除 IP 和用户名的失败记录
            _clear_login_failure(ip_key)
            _clear_login_failure(user_key)
            # 🔒 安全：清除旧 Session，防止 Session 固定攻击
            request.session.clear()
            # 重新生成 session_id
            from app.core.session import create_session
            new_session_id = create_session({})
            request.session._session_id = new_session_id
            request.session["user"] = result
            request.session["login_time"] = time.time()
            log_audit("login", user_id=str(result.get("id")), user_name=username, ip_address=client_ip, user_agent=user_agent, details={"auth_type": "local"})
            return {"status": "success", "message": "登录成功"}
        else:
            # 🔒 记录 IP 和用户名的失败
            _record_login_failure(ip_key, "ip")
            _record_login_failure(user_key, "user")
            remaining = min(_get_remaining_attempts(ip_key), _get_remaining_attempts(user_key))
            log_audit("login_failed", user_name=username, ip_address=client_ip, user_agent=user_agent, details={"reason": str(result), "remaining": remaining}, status="failed")
            return {
                "status": "error", 
                "message": result if isinstance(result, str) else "登录失败",
                "remaining_attempts": remaining
            }

    # Emby 账号登录（默认）
    # 检查是否禁用了 Emby 认证
    if cfg.get("disable_emby_auth", False):
        return {"status": "error", "message": "Emby 管理员登录已禁用，请使用本地账号登录"}

    emby_host = cfg.get("emby_host", "")
    emby_key = cfg.get("emby_api_key", "")

    if not emby_host or not emby_key:
        return {"status": "error", "message": "Emby 服务器未配置"}

    try:
        # 获取所有用户
        users_res = requests.get(
            f"{emby_host}/Users?api_key={emby_key}",
            timeout=10
        )

        if users_res.status_code != 200:
            return {"status": "error", "message": "Emby 服务器连接失败"}

        users = users_res.json()
        matched_user = None

        # 匹配用户名
        for u in users:
            if u.get("Name", "").lower() == username.lower():
                matched_user = u
                break

        if not matched_user:
            # 🔒 记录 IP 和用户名的失败
            _record_login_failure(ip_key, "ip")
            _record_login_failure(user_key, "user")
            remaining = min(_get_remaining_attempts(ip_key), _get_remaining_attempts(user_key))
            return {"status": "error", "message": "账号或密码错误", "remaining_attempts": remaining}

        # 检查是否是管理员
        if not matched_user.get("Policy", {}).get("IsAdministrator", False):
            # 🔒 用户枚举防护：统一返回"账号或密码错误"，不暴露用户存在
            _record_login_failure(ip_key, "ip")
            _record_login_failure(user_key, "user")
            remaining = min(_get_remaining_attempts(ip_key), _get_remaining_attempts(user_key))
            return {"status": "error", "message": "账号或密码错误", "remaining_attempts": remaining}

        # 验证密码（如果有设置）
        has_password = matched_user.get("HasPassword", False)
        if not has_password:
            _record_login_failure(ip_key, "ip")
            _record_login_failure(user_key, "user")
            remaining = min(_get_remaining_attempts(ip_key), _get_remaining_attempts(user_key))
            return {
                "status": "error",
                "message": "安全要求：请先在 Emby 中为管理员账号设置密码",
                "remaining_attempts": remaining
            }
        if has_password:
            # 使用 Emby 认证接口验证密码
            auth_url = f"{emby_host}/Users/AuthenticateByName"
            auth_res = requests.post(
                auth_url,
                data={"Username": username, "Pw": password},
                headers={"X-Emby-Authorization": f'MediaBrowser Client="EmbyPulse", Device="EmbyPulse", DeviceId="EmbyPulse", Version="1.0"'},
                timeout=10
            )
            if auth_res.status_code != 200:
                _record_login_failure(ip_key, "ip")
                _record_login_failure(user_key, "user")
                remaining = min(_get_remaining_attempts(ip_key), _get_remaining_attempts(user_key))
                return {"status": "error", "message": "账号或密码错误", "remaining_attempts": remaining}

        # 🔒 登录成功，清除 IP 和用户名的失败记录
        _clear_login_failure(ip_key)
        _clear_login_failure(user_key)
        
        # 🔒 审计日志：Emby 登录成功
        from app.core.audit_logger import log_audit
        log_audit(
            action="login",
            user_id=matched_user["Id"],
            user_name=username,
            ip_address=client_ip,
            user_agent=request.headers.get("user-agent", ""),
            details={"auth_type": "emby"}
        )

        # 登录成功，设置 session
        # 使用代理 API 获取 Emby 用户头像（前端通过 /api/user/image/{user_id} 访问）

        user_info = {
            "id": matched_user["Id"],
            "name": matched_user["Name"],
            "is_admin": True,
            "role": "admin",  # Emby 管理员角色
            "server_id": matched_user.get("ServerId", ""),
            "auth_type": "emby",
            "permissions": [],  # Emby 账号拥有全部权限
            "avatar": f"/api/user/image/{matched_user['Id']}" if matched_user.get("PrimaryImageTag") else ""
        }

        # 🔒 安全：清除旧 Session，防止 Session 固定攻击
        request.session.clear()
        # 重新生成 session_id
        from app.core.session import create_session
        new_session_id = create_session({})
        request.session._session_id = new_session_id
        request.session["user"] = user_info
        request.session["login_time"] = time.time()
        return {"status": "success", "message": "登录成功"}

    except requests.exceptions.Timeout:
        return {"status": "error", "message": "Emby 连接超时"}
    except requests.exceptions.ConnectionError:
        return {"status": "error", "message": "Emby 连接失败"}
    except Exception as e:
        logger.error(f"[登录异常] {str(e)}")
        return {"status": "error", "message": "登录失败"}


@router.post("/api/logout")
async def api_logout(request: Request):
    """登出"""
    # 🔒 审计日志：登出
    from app.core.audit_logger import log_audit
    user = request.session.get("user", {})
    if user:
        log_audit(
            action="logout",
            user_id=str(user.get("id", "")),
            user_name=user.get("name", ""),
            ip_address=request.client.host if request.client else ""
        )
    request.session.clear()
    return {"status": "success", "message": "已登出"}


@router.get("/api/me")
async def get_current_user(request: Request):
    """获取当前登录用户信息"""
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    return {"status": "success", "data": user}


# ==================== TOTP 两步验证 API ====================

class TOTPVerifyModel(BaseModel):
    code: str

class TOTPEnableModel(BaseModel):
    secret: str
    code: str  # 验证码，确保用户已绑定验证器

@router.get("/api/auth/totp/setup")
async def totp_setup(request: Request):
    """
    生成 TOTP 密钥和二维码
    用户需要用验证器扫码绑定
    """
    if not TOTP_AVAILABLE:
        return {"status": "error", "message": "系统未安装 TOTP 支持"}
    
    user = request.session.get("user")
    if not user or user.get("auth_type") != "local":
        return {"status": "error", "message": "仅本地账号支持两步验证"}
    
    user_id = user.get("id")
    
    # 检查是否已启用 TOTP
    existing = query_db("SELECT totp_enabled FROM local_users WHERE id = ?", (user_id,), one=True)
    if existing and existing['totp_enabled']:
        return {"status": "error", "message": "已启用两步验证，如需更换请先禁用"}
    
    # 生成新的 TOTP 密钥
    secret = pyotp.random_base32()
    
    # 生成 provisioning URL（验证器扫码用）
    app_name = "EmbyPulse"
    username = user.get("name", "user")
    provisioning_url = pyotp.totp.TOTP(secret).provisioning_uri(
        name=username,
        issuer_name=app_name
    )
    
    # 生成二维码图片
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(provisioning_url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # 将图片转为 base64
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    img_base64 = base64.b64encode(buffer.getvalue()).decode()
    
    # 保存到待验证字段（不覆盖已启用的密钥）
    query_db("UPDATE local_users SET totp_pending_secret = ? WHERE id = ?", (secret, user_id))
    
    return {
        "status": "success",
        "data": {
            "secret": secret,  # 手动输入用（备用）
            "qr_code": f"data:image/png;base64,{img_base64}",
            "provisioning_url": provisioning_url,
            "username": username,
            "issuer": app_name
        }
    }


@router.post("/api/auth/totp/verify")
async def totp_verify(request: Request, data: TOTPVerifyModel):
    """
    验证 TOTP 验证码
    用于绑定验证器时的验证
    """
    if not TOTP_AVAILABLE:
        return {"status": "error", "message": "系统未安装 TOTP 支持"}
    
    user = request.session.get("user")
    if not user or user.get("auth_type") != "local":
        return {"status": "error", "message": "仅本地账号支持两步验证"}
    
    user_id = user.get("id")
    
    # 获取用户当前的 TOTP secret（优先使用待验证密钥）
    row = query_db("SELECT totp_pending_secret, totp_secret FROM local_users WHERE id = ?", (user_id,), one=True)
    secret = (row['totp_pending_secret'] or row['totp_secret']) if row else ''
    if not secret:
        return {"status": "error", "message": "请先生成验证器密钥"}

    # 验证验证码
    totp = pyotp.TOTP(secret)
    if totp.verify(data.code, valid_window=1):
        return {"status": "success", "message": "验证成功"}
    else:
        return {"status": "error", "message": "验证码错误或已过期"}


@router.post("/api/auth/totp/enable")
async def totp_enable(request: Request, data: TOTPEnableModel):
    """
    启用 TOTP 两步验证
    需要验证验证码确保用户已绑定
    """
    if not TOTP_AVAILABLE:
        return {"status": "error", "message": "系统未安装 TOTP 支持"}
    
    user = request.session.get("user")
    if not user or user.get("auth_type") != "local":
        return {"status": "error", "message": "仅本地账号支持两步验证"}
    
    user_id = user.get("id")
    
    # 验证验证码
    totp = pyotp.TOTP(data.secret)
    if not totp.verify(data.code, valid_window=1):
        return {"status": "error", "message": "验证码错误或已过期"}
    
    # 启用 TOTP
    pending = query_db("SELECT totp_pending_secret FROM local_users WHERE id = ?", (user_id,), one=True)
    if not pending or not pending['totp_pending_secret']:
        return {"status": "error", "message": "请先调用 TOTP setup 生成密钥"}
    query_db("UPDATE local_users SET totp_secret = ?, totp_enabled = 1, totp_pending_secret = '' WHERE id = ?",
             (pending['totp_pending_secret'], user_id))
    
    return {"status": "success", "message": "两步验证已启用"}


@router.post("/api/auth/totp/disable")
async def totp_disable(request: Request, data: TOTPVerifyModel):
    """
    禁用 TOTP 两步验证
    需要验证验证码确保是本人操作
    """
    if not TOTP_AVAILABLE:
        return {"status": "error", "message": "系统未安装 TOTP 支持"}
    
    user = request.session.get("user")
    if not user or user.get("auth_type") != "local":
        return {"status": "error", "message": "仅本地账号支持两步验证"}
    
    user_id = user.get("id")
    
    # 获取当前 secret
    row = query_db("SELECT totp_secret FROM local_users WHERE id = ?", (user_id,), one=True)
    if not row or not row['totp_secret']:
        return {"status": "error", "message": "未启用两步验证"}
    
    # 验证验证码（确保是本人）
    totp = pyotp.TOTP(row['totp_secret'])
    if not totp.verify(data.code, valid_window=1):
        return {"status": "error", "message": "验证码错误或已过期"}
    
    # 禁用 TOTP
    query_db("UPDATE local_users SET totp_secret = '', totp_pending_secret = '', totp_enabled = 0 WHERE id = ?", (user_id,))
    
    return {"status": "success", "message": "两步验证已禁用"}


@router.get("/api/auth/totp/status")
async def totp_status(request: Request):
    """
    获取当前用户的 TOTP 状态
    """
    user = request.session.get("user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    if user.get("auth_type") != "local":
        return {"status": "success", "data": {"enabled": False, "available": False}}
    
    user_id = user.get("id")
    row = query_db("SELECT totp_enabled FROM local_users WHERE id = ?", (user_id,), one=True)
    
    return {
        "status": "success",
        "data": {
            "enabled": row['totp_enabled'] if row else False,
            "available": TOTP_AVAILABLE
        }
    }
