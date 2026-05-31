import sqlite3
import os
import requests
import json
import logging
import datetime  # 🔥 新增导入 datetime 模块
import shutil
import time
from collections import deque
from app.core.config import cfg, DB_PATH, SYSTEM_DB_PATH
from app.dao.notification_dao import add_system_notification

# 🔥 导出 SYSTEM_DB_PATH 供其他模块使用
__all__ = ['init_db', 'query_db', 'get_base_filter', 'add_sys_notification',
           'DB_PATH', 'SYSTEM_DB_PATH', 'auto_migrate_system_db', 'get_db_connection',
           'get_query_perf_stats']

_slow_queries = deque(maxlen=50)
_query_stats = {
    "total": 0,
    "select": 0,
    "slow": 0,
    "large_result": 0,
}

def _get_slow_query_ms() -> int:
    try:
        return int(cfg.get("slow_query_ms") or 800)
    except Exception:
        return 800

def _record_query_perf(query: str, elapsed_ms: float, row_count: int = 0):
    _query_stats["total"] += 1
    if query.strip().upper().startswith("SELECT"):
        _query_stats["select"] += 1
    if row_count >= 1000:
        _query_stats["large_result"] += 1

    slow_ms = _get_slow_query_ms()
    if elapsed_ms >= slow_ms:
        _query_stats["slow"] += 1
        normalized = " ".join(query.strip().split())
        _slow_queries.append({
            "elapsed_ms": round(elapsed_ms, 1),
            "rows": row_count,
            "sql": normalized[:300],
            "ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        logger.warning(f"[慢查询] {elapsed_ms:.1f}ms rows={row_count} sql={normalized[:180]}")

def get_query_perf_stats():
    return {
        **_query_stats,
        "slow_query_ms": _get_slow_query_ms(),
        "recent_slow_queries": list(_slow_queries),
    }

# 🔥 统一数据库连接函数 - 解决 "database is locked" 问题
def get_db_connection(db_path, timeout=30.0, enable_wal=True):
    """
    创建 SQLite 连接，配置 WAL 模式和超时
    
    Args:
        db_path: 数据库路径
        timeout: 锁等待超时（秒），默认 30
        enable_wal: 启用 WAL 模式提高并发，默认 True
    
    Returns:
        sqlite3.Connection
    """
    conn = sqlite3.connect(db_path, timeout=timeout)
    if enable_wal:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")  # 30秒
        conn.execute("PRAGMA synchronous=NORMAL")  # 平衡性能和安全
    conn.row_factory = sqlite3.Row
    return conn

logger = logging.getLogger("uvicorn")

# 🔥 系统数据表清单 - 这些表会迁移到独立系统数据库
SYSTEM_TABLES = [
    "users_meta", "invitations", "sys_license", "tg_user_bindings",
    "tg_user_blacklist", "media_requests", "request_users", "media_feedback",
    "risk_logs", "sys_notifications", "point_logs", "point_config",
    "plugin_state", "plugin_logs", "sys_dashboard", "insight_ignores", "notify_mutes",
    "UserList", "client_blacklist", "gap_records", "gap_config",
    "gap_perfect_series", "gap_scan_cache", "dedupe_results", "dedupe_whitelist",
    "dedupe_config", "keep_alive_violations",
    "task_config", "task_translations", "tv_calendar_cache", "tg_reg_logs",
    "local_users", "msg_conversations", "msg_items", "msg_notify_block", "user_mutes",
    "bot_notify_mutes", "notify_rules"
]

# 🔥 播放数据表（不迁移，保持原库读取）
PLAYBACK_TABLES = ["PlaybackActivity"]

def check_db_has_data(db_path):
    """检查数据库是否有系统表数据
    🔥 关键：检查多个核心表，包括 users_meta 和 sys_license（Pro 授权）
    """
    try:
        conn = get_db_connection(db_path)
        cursor = conn.cursor()

        # 先检查有哪些表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = [row[0] for row in cursor.fetchall()]

        # 🔥 核心表列表：users_meta（用户数据）和 sys_license（Pro 授权）
        # 任一表存在且有数据，都视为"有数据"，不应触发迁移
        core_tables = ['users_meta', 'sys_license']
        has_core_data = False
        table_counts = {}

        for table in core_tables:
            if table in existing_tables:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    if count > 0:
                        has_core_data = True
                        table_counts[table] = count
                        print(f"[🔄 迁移检测] 核心表 {table} 有 {count} 条数据")
                except:
                    pass

        # 🔥 如果任一核心表有数据，跳过迁移
        if has_core_data:
            # 统计其他表数据
            for table in SYSTEM_TABLES:
                if table not in core_tables and table in existing_tables:
                    try:
                        cursor.execute(f"SELECT COUNT(*) FROM {table}")
                        count = cursor.fetchone()[0]
                        if count > 0:
                            table_counts[table] = count
                    except:
                        pass
            conn.close()
            print(f"[🔄 迁移检测] ✅ 系统库已有核心数据，跳过迁移: {table_counts}")
            return True

        # 🔥 核心表都为空或不存在，才触发迁移
        print(f"[🔄 迁移检测] 核心表无数据（users_meta/sys_license），需要迁移或初始化")
        conn.close()
        return False

    except Exception as e:
        print(f"[🔄 迁移检测] 检查数据失败: {e}")
        return False


def auto_migrate_system_db():
    """
    自动迁移系统数据到独立数据库
    启动时检测：如果系统库不存在或无数据，且旧库有数据，自动迁移
    
    环境变量：
    - AUTO_MIGRATE_DB=1 启用自动迁移（默认关闭）
    - FORCE_MIGRATE=1 强制重新迁移（需要先启用 AUTO_MIGRATE_DB）
    """
    # 🔥 默认关闭自动迁移，需要显式设置 AUTO_MIGRATE_DB=1 才执行
    auto_migrate_enabled = os.getenv("AUTO_MIGRATE_DB", "") == "1"
    if not auto_migrate_enabled:
        print("[🔄 迁移检测] 自动迁移已关闭（设置 AUTO_MIGRATE_DB=1 启用）")
        return False

    old_db = DB_PATH  # 原数据库路径
    new_db = SYSTEM_DB_PATH  # 新系统数据库路径
    backup_db = "/workspace/data/playback_reporting.db.backup"

    # 强制迁移模式
    force_migrate = os.getenv("FORCE_MIGRATE", "") == "1"
    if force_migrate and os.path.exists(new_db):
        print(f"[🔄 迁移检测] 强制迁移模式，删除现有系统库")
        try:
            os.remove(new_db)
            print(f"[🔄 迁移检测] 已删除现有系统库")
        except Exception as e:
            print(f"[🔄 迁移检测] 删除失败: {e}")

    # 检查旧库是否存在
    if not os.path.exists(old_db):
        print(f"[🔄 迁移检测] 未检测到旧数据库，将在新库创建全新系统表")
        return False

    # 检查新库是否有数据
    if os.path.exists(new_db):
        if check_db_has_data(new_db):
            print(f"[🔄 迁移检测] 系统数据库已有数据，跳过迁移")
            return True
        else:
            # 🔥 即使检测为空，也要额外检查 sys_license 表（保护 Pro 授权）
            try:
                conn = sqlite3.connect(new_db)
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sys_license'")
                if cursor.fetchone():
                    cursor.execute("SELECT COUNT(*) FROM sys_license")
                    license_count = cursor.fetchone()[0]
                    if license_count > 0:
                        conn.close()
                        print(f"[🔄 迁移检测] ⚠️ sys_license 有 {license_count} 条授权数据，保护不删除")
                        return True
                conn.close()
            except Exception as e:
                print(f"[🔄 迁移检测] Pro授权检查异常: {e}")

            print(f"[🔄 迁移检测] 系统数据库确实为空，删除后重新迁移")
            try:
                os.remove(new_db)
            except Exception as e:
                print(f"[🔄 迁移检测] 删除空库失败: {e}")
                return False

    print(f"[🔄 迁移检测] 发现旧数据库: {old_db}")
    print(f"[🔄 迁移检测] 开始自动迁移系统数据...")

    try:
        # 1. 备份原库（安全第一）
        try:
            shutil.copy2(old_db, backup_db)
            print(f"[🔄 迁移] ✅ 已备份原库: {backup_db}")
        except Exception as e:
            print(f"[🔄 迁移] ⚠️ 备份警告: {e}")

        # 2. 连接数据库
        old_conn = sqlite3.connect(old_db)
        old_conn.row_factory = sqlite3.Row

        # 确保新库目录存在
        new_db_dir = os.path.dirname(new_db)
        if not os.path.exists(new_db_dir):
            os.makedirs(new_db_dir, exist_ok=True)

        new_conn = sqlite3.connect(new_db)
        new_cursor = new_conn.cursor()

        # 3. 迁移系统表
        migrated = []
        failed = []

        for table in SYSTEM_TABLES:
            try:
                # 检查旧库中是否存在该表
                old_cursor = old_conn.cursor()
                old_cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table,)
                )
                if not old_cursor.fetchone():
                    continue  # 表不存在，跳过

                # 获取表结构
                old_cursor.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                    (table,)
                )
                schema_row = old_cursor.fetchone()
                if not schema_row or not schema_row[0]:
                    continue

                # 在新库创建表
                new_cursor.execute(schema_row[0])

                # 复制数据
                old_cursor.execute(f"SELECT * FROM {table}")
                rows = old_cursor.fetchall()

                if rows:
                    # 获取列名
                    columns = [desc[0] for desc in old_cursor.description]
                    placeholders = ",".join(["?" for _ in columns])

                    # 批量插入
                    new_cursor.executemany(
                        f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})",
                        [tuple(row) for row in rows]
                    )
                    migrated.append(f"{table}({len(rows)})")
                else:
                    migrated.append(f"{table}(0)")

            except Exception as e:
                failed.append(f"{table}: {str(e)}")
                print(f"[🔄 迁移] ⚠️ 表 {table} 迁移失败: {e}")

        # 4. 提交并关闭
        new_conn.commit()
        old_conn.close()
        new_conn.close()

        # 5. 创建迁移标记
        marker_file = f"{new_db}.migrated"
        with open(marker_file, "w", encoding="utf-8") as f:
            f.write(f"迁移时间: {datetime.datetime.now()}\n")
            f.write(f"迁移表: {', '.join(migrated)}\n")
            if failed:
                f.write(f"失败: {', '.join(failed)}\n")

        print(f"[🔄 迁移] ✅ 迁移完成！共 {len(migrated)} 张表")
        if migrated:
            print(f"[🔄 迁移] 📊 详情: {', '.join(migrated[:10])}{'...' if len(migrated) > 10 else ''}")
        if failed:
            print(f"[🔄 迁移] ⚠️ 失败: {', '.join(failed)}")

        return True

    except Exception as e:
        print(f"[🔄 迁移] ❌ 迁移过程出错: {e}")
        # 清理可能损坏的新库
        if os.path.exists(new_db):
            try:
                os.remove(new_db)
                print(f"[🔄 迁移] 🧹 已清理损坏的新库")
            except:
                pass
        return False

def init_system_db():
    """初始化系统数据库（固定路径，与播放数据分离）"""
    db_dir = os.path.dirname(SYSTEM_DB_PATH)
    if not os.path.exists(db_dir):
        try:
            os.makedirs(db_dir, exist_ok=True)
            print(f"[📁 系统库] 创建目录: {db_dir}")
        except Exception as e:
            print(f"[📁 系统库] 目录创建警告: {e}")

    # 🔥 每次都执行表创建和字段迁移（CREATE TABLE IF NOT EXISTS 和 ALTER TABLE 会自动处理已存在的情况）
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()

        # 系统表创建和字段迁移
        _create_system_tables(c)

        conn.commit()
        
        # 🔥 修复 point_logs 表中的时间问题（本地时间被当作 UTC 导致多了8小时）
        try:
            c.execute("""
                UPDATE point_logs 
                SET created_at = datetime(created_at, '-8 hours')
                WHERE created_at > datetime('now', 'localtime')
            """)
            fixed_count = c.rowcount
            if fixed_count > 0:
                print(f"[🔧 时间修复] 已修复 {fixed_count} 条积分流水记录的时间")
                conn.commit()
        except Exception as e:
            print(f"[🔧 时间修复] 检查跳过: {e}")
        
        conn.close()
        print(f"✅ 系统数据库初始化完成: {SYSTEM_DB_PATH}")
    except Exception as e:
        print(f"❌ 系统数据库初始化错误: {e}")


def _create_system_tables(c):
    """创建系统表（内部函数）"""
    c.execute('''CREATE TABLE IF NOT EXISTS users_meta (user_id TEXT PRIMARY KEY, expire_date TEXT, note TEXT, created_at TEXT)''')

    # 风控字段
    try: c.execute("ALTER TABLE users_meta ADD COLUMN max_concurrent INTEGER")
    except Exception: pass
    try: c.execute("ALTER TABLE users_meta ADD COLUMN risk_level TEXT DEFAULT 'safe'")
    except Exception: pass
    try: c.execute("ALTER TABLE users_meta ADD COLUMN is_vip INTEGER DEFAULT 0")
    except Exception: pass
    try: c.execute("ALTER TABLE users_meta ADD COLUMN points INTEGER DEFAULT 0")
    except Exception: pass
    try: c.execute("ALTER TABLE users_meta ADD COLUMN block_routes TEXT DEFAULT ''")
    except Exception: pass
    try: c.execute("ALTER TABLE users_meta ADD COLUMN allow_routes TEXT DEFAULT ''")
    except Exception: pass
    try: c.execute("ALTER TABLE users_meta ADD COLUMN remark TEXT DEFAULT ''")
    except Exception: pass
    try: c.execute("ALTER TABLE users_meta ADD COLUMN admin_disabled INTEGER DEFAULT 0")
    except Exception: pass
    # 🔥 求片权限字段
    try: c.execute("ALTER TABLE users_meta ADD COLUMN req_free INTEGER DEFAULT 0")  # 0=跟随全局, 1=免费, 2=付费
    except Exception: pass
    try: c.execute("ALTER TABLE users_meta ADD COLUMN req_free_count INTEGER DEFAULT -1")  # -1=无限次, >=0=剩余次数
    except Exception: pass
    # 🔥 用户标签字段
    try: c.execute("ALTER TABLE users_meta ADD COLUMN tags TEXT DEFAULT ''")  # 用户标签，逗号分隔
    except Exception: pass

    # 🔒 安全：登录失败锁定表（持久化，防止重启后丢失）
    c.execute('''CREATE TABLE IF NOT EXISTS login_failures (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lock_key TEXT NOT NULL UNIQUE,
        lock_type TEXT NOT NULL,
        failure_count INTEGER DEFAULT 0,
        locked_until DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    try: c.execute("CREATE INDEX IF NOT EXISTS idx_login_failures_key ON login_failures(lock_key)")
    except Exception: pass
    try: c.execute("CREATE INDEX IF NOT EXISTS idx_login_failures_type ON login_failures(lock_type)")
    except Exception: pass
    try: c.execute("CREATE INDEX IF NOT EXISTS idx_login_failures_locked ON login_failures(locked_until)")
    except Exception: pass

    # 🔑 API Token 表（用于第三方应用调用）
    c.execute('''CREATE TABLE IF NOT EXISTS api_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        token TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        expires_at DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        last_used_at DATETIME,
        FOREIGN KEY (user_id) REFERENCES users_meta(user_id)
    )''')
    try: c.execute("CREATE INDEX IF NOT EXISTS idx_api_tokens_user ON api_tokens(user_id)")
    except Exception: pass
    try: c.execute("CREATE INDEX IF NOT EXISTS idx_api_tokens_token ON api_tokens(token)")
    except Exception: pass

    c.execute('''CREATE TABLE IF NOT EXISTS invitations (code TEXT PRIMARY KEY, days INTEGER, used_count INTEGER DEFAULT 0, max_uses INTEGER DEFAULT 1, created_at TEXT, used_at DATETIME, used_by TEXT, status INTEGER DEFAULT 0, template_user_id TEXT, type TEXT DEFAULT 'register', routes TEXT)''')
    try: c.execute("ALTER TABLE invitations ADD COLUMN template_user_id TEXT")
    except Exception: pass
    try: c.execute("ALTER TABLE invitations ADD COLUMN type TEXT DEFAULT 'register'")
    except Exception: pass
    try: c.execute("ALTER TABLE invitations ADD COLUMN routes TEXT")
    except Exception: pass
    try: c.execute("ALTER TABLE invitations ADD COLUMN route_mode TEXT DEFAULT 'block'")
    except Exception: pass

    c.execute('''CREATE TABLE IF NOT EXISTS sys_license (license_key TEXT, machine_id TEXT, pro_token TEXT, status TEXT DEFAULT 'pro', expire_date DATETIME, last_checked DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    # 🔥 用户标签配置表
    c.execute('''CREATE TABLE IF NOT EXISTS user_tags (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, color TEXT DEFAULT 'blue', created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    c.execute('''CREATE TABLE IF NOT EXISTS tv_calendar_cache (id TEXT PRIMARY KEY, series_id TEXT, season INTEGER, episode INTEGER, air_date TEXT, status TEXT, data_json TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tv_series_status (tmdb_id TEXT PRIMARY KEY, series_name TEXT, status TEXT DEFAULT 'continuing', last_checked TEXT, updated_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS media_requests (tmdb_id INTEGER, media_type TEXT, title TEXT, year TEXT, poster_path TEXT, status INTEGER DEFAULT 0, season INTEGER DEFAULT 0, reject_reason TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (tmdb_id, season))''')
    c.execute('''CREATE TABLE IF NOT EXISTS request_users (id INTEGER PRIMARY KEY AUTOINCREMENT, tmdb_id INTEGER, user_id TEXT, username TEXT, season INTEGER DEFAULT 0, requested_at DATETIME DEFAULT CURRENT_TIMESTAMP, UNIQUE(tmdb_id, user_id, season))''')
    c.execute('''CREATE TABLE IF NOT EXISTS request_admin_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tmdb_id INTEGER NOT NULL,
        chat_id TEXT NOT NULL,
        message_id INTEGER NOT NULL,
        is_caption INTEGER DEFAULT 1,
        original_text TEXT DEFAULT '',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(tmdb_id, chat_id, message_id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS insight_ignores (item_id TEXT PRIMARY KEY, item_name TEXT, ignored_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS gap_records (id INTEGER PRIMARY KEY AUTOINCREMENT, series_id TEXT, series_name TEXT, season_number INTEGER, episode_number INTEGER, status INTEGER DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, UNIQUE(series_id, season_number, episode_number))''')
    c.execute('''CREATE TABLE IF NOT EXISTS risk_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, username TEXT, action TEXT, reason TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS sys_notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT, title TEXT, message TEXT, is_read INTEGER DEFAULT 0, action_url TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    try: c.execute("ALTER TABLE sys_notifications ADD COLUMN is_cleared INTEGER DEFAULT 0")
    except Exception: pass
    c.execute('''CREATE TABLE IF NOT EXISTS tg_user_bindings (tg_user_id TEXT PRIMARY KEY, tg_username TEXT DEFAULT '', emby_user_id TEXT, emby_username TEXT, init_password TEXT DEFAULT '', bound_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tg_user_blacklist (tg_user_id TEXT PRIMARY KEY, reason TEXT DEFAULT '', created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    # 🔥 迁移：添加 tg_username 字段
    try: c.execute("ALTER TABLE tg_user_bindings ADD COLUMN tg_username TEXT DEFAULT ''")
    except Exception: pass
    # 🔥 迁移：添加 tg_display_name 字段（TG显示名称/中文名）
    try: c.execute("ALTER TABLE tg_user_bindings ADD COLUMN tg_display_name TEXT DEFAULT ''")
    except Exception: pass
    c.execute('''CREATE TABLE IF NOT EXISTS plugin_state (plugin_id TEXT PRIMARY KEY, enabled INTEGER DEFAULT 0, config TEXT DEFAULT '{}')''')
    c.execute('''CREATE TABLE IF NOT EXISTS sys_dashboard (id INTEGER PRIMARY KEY DEFAULT 1, layout_json TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS point_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, username TEXT, action TEXT, amount INTEGER, balance INTEGER, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS point_config (key TEXT PRIMARY KEY, value TEXT)''')
    
    # 🔥 彩票系统表
    c.execute('''CREATE TABLE IF NOT EXISTS lottery_tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        username TEXT,
        numbers TEXT NOT NULL,
        cost INTEGER,
        draw_date TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS lottery_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        draw_date TEXT NOT NULL UNIQUE,
        winning_numbers TEXT NOT NULL,
        total_pool INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS lottery_winners (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        username TEXT,
        ticket_id INTEGER,
        prize_level INTEGER,
        prize_amount INTEGER,
        draw_date TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # 🔥 刮刮乐表
    c.execute('''CREATE TABLE IF NOT EXISTS scratch_cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        total_slots INTEGER DEFAULT 9,
        filled_slots INTEGER DEFAULT 0,
        price INTEGER DEFAULT 100,
        status TEXT DEFAULT 'active',
        created_by TEXT,
        chat_id TEXT DEFAULT '',
        message_id INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    try: c.execute("ALTER TABLE scratch_cards ADD COLUMN chat_id TEXT DEFAULT ''")
    except Exception: pass
    try: c.execute("ALTER TABLE scratch_cards ADD COLUMN message_id INTEGER DEFAULT 0")
    except Exception: pass
    c.execute('''CREATE TABLE IF NOT EXISTS scratch_card_slots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        card_id INTEGER NOT NULL,
        slot_number INTEGER NOT NULL,
        prize_amount INTEGER NOT NULL,
        is_scratched INTEGER DEFAULT 0,
        user_id TEXT,
        username TEXT,
        scratched_at DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    # 消息中心表
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
    c.execute('''CREATE TABLE IF NOT EXISTS msg_notify_block (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    # 🤖 开放注册日志表
    c.execute('''CREATE TABLE IF NOT EXISTS tg_reg_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, tg_user_id TEXT, emby_username TEXT, emby_user_id TEXT, reg_type TEXT DEFAULT 'open', created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    # 任务翻译表
    c.execute('''CREATE TABLE IF NOT EXISTS task_translations (original_name TEXT PRIMARY KEY, translated_name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS task_config (key TEXT PRIMARY KEY, value TEXT)''')

    # 媒体反馈表
    c.execute('''CREATE TABLE IF NOT EXISTS media_feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, item_name TEXT, user_id TEXT, username TEXT, issue_type TEXT, description TEXT, status INTEGER DEFAULT 0, poster_path TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

    # 客户端黑名单
    c.execute('''CREATE TABLE IF NOT EXISTS client_blacklist (app_name TEXT PRIMARY KEY, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    # 通知静音
    c.execute('''CREATE TABLE IF NOT EXISTS notify_mutes (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, mute_type TEXT, mute_target TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, mute_type, mute_target))''')

    # 通知规则配置
    c.execute('''CREATE TABLE IF NOT EXISTS notify_rules (id INTEGER PRIMARY KEY AUTOINCREMENT, notify_type TEXT UNIQUE NOT NULL, notify_name TEXT NOT NULL, channels TEXT DEFAULT '[]', enabled INTEGER DEFAULT 1, config TEXT DEFAULT '{}', created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    # 用户列表
    c.execute('''CREATE TABLE IF NOT EXISTS UserList (id INTEGER PRIMARY KEY AUTOINCREMENT, list_name TEXT, list_type TEXT, user_ids TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    # 缺集配置
    c.execute('''CREATE TABLE IF NOT EXISTS gap_config (key TEXT PRIMARY KEY, value TEXT, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS gap_perfect_series (id INTEGER PRIMARY KEY AUTOINCREMENT, series_id TEXT, tmdb_id TEXT, series_name TEXT, total_seasons INTEGER, total_episodes INTEGER, marked_at DATETIME DEFAULT CURRENT_TIMESTAMP, UNIQUE(series_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS gap_scan_cache (id INTEGER PRIMARY KEY, result_json TEXT, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    # 去重系统（完整字段版本，与 dedupe.py 保持一致）
    c.execute('''CREATE TABLE IF NOT EXISTS dedupe_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_key TEXT,
        tmdb_id TEXT,
        media_type TEXT,
        title TEXT,
        season_num INTEGER,
        episode_num INTEGER,
        item_id TEXT,
        file_name TEXT,
        file_path TEXT,
        resolution TEXT,
        bitrate INTEGER,
        size_bytes REAL,
        video_codec TEXT,
        audio_codec TEXT,
        has_hdr INTEGER,
        has_dovi INTEGER,
        has_chi_sub INTEGER,
        has_ass_sub INTEGER,
        score INTEGER,
        is_recommended_del INTEGER DEFAULT 0,
        is_exempt INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS dedupe_whitelist (
        group_key TEXT PRIMARY KEY,
        title TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS dedupe_config (key TEXT PRIMARY KEY, value TEXT, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    # 插件日志
    c.execute('''CREATE TABLE IF NOT EXISTS plugin_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plugin_id TEXT NOT NULL,
        level TEXT DEFAULT 'info',
        message TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    # 用户禁言表
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

    # 保活违规记录
    c.execute('''CREATE TABLE IF NOT EXISTS keep_alive_violations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        user_name TEXT NOT NULL,
        year_month TEXT NOT NULL,
        hours REAL DEFAULT 0,
        days INTEGER DEFAULT 0,
        min_hours REAL DEFAULT 0,
        min_days INTEGER DEFAULT 0,
        action TEXT DEFAULT 'warn',
        disabled INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, year_month)
    )''')

    # 本地用户认证
    c.execute('''CREATE TABLE IF NOT EXISTS local_users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT DEFAULT 'admin', remark TEXT DEFAULT '', avatar TEXT DEFAULT '', is_enabled INTEGER DEFAULT 1, permissions TEXT DEFAULT '[]', created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, last_login_at DATETIME, last_login_ip TEXT)''')

    # 机器人通知屏蔽（与消息中心的 notify_mutes 不同）
    c.execute('''CREATE TABLE IF NOT EXISTS bot_notify_mutes (
        user_id TEXT,
        event_type TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, event_type)
    )''')

    # 🔥 性能优化：创建索引（大幅提升查询速度）
    # 用户元数据索引
    try: c.execute("CREATE INDEX IF NOT EXISTS idx_users_meta_expire ON users_meta(expire_date)")
    except Exception: pass
    # 风控日志索引
    try: c.execute("CREATE INDEX IF NOT EXISTS idx_risk_logs_user ON risk_logs(user_id)")
    except Exception: pass
    try: c.execute("CREATE INDEX IF NOT EXISTS idx_risk_logs_time ON risk_logs(created_at)")
    except Exception: pass
    # 积分日志索引
    try: c.execute("CREATE INDEX IF NOT EXISTS idx_point_logs_user ON point_logs(user_id)")
    except Exception: pass
    # 媒体请求索引
    try: c.execute("CREATE INDEX IF NOT EXISTS idx_media_requests_status ON media_requests(status)")
    except Exception: pass
    try: c.execute("CREATE INDEX IF NOT EXISTS idx_request_admin_messages_tmdb ON request_admin_messages(tmdb_id)")
    except Exception: pass
    # 消息索引
    try: c.execute("CREATE INDEX IF NOT EXISTS idx_msg_conversations_user ON msg_conversations(user_id)")
    except Exception: pass
    try: c.execute("CREATE INDEX IF NOT EXISTS idx_msg_items_conv ON msg_items(conversation_id)")
    except Exception: pass


def init_db(skip_migration=False):
    """初始化所有数据库
    Args:
        skip_migration: 如果为True，跳过迁移检测（main.py已调用过）
    """
    # 1. 尝试自动迁移（如果系统库不存在且旧库存在）
    if not skip_migration:
        auto_migrate_system_db()

    # 2. 初始化系统数据库（固定路径）
    init_system_db()

    # 3. 兼容：如果配置了旧路径，也初始化（用于播放数据）
    db_dir = os.path.dirname(DB_PATH)
    if not os.path.exists(db_dir):
        try:
            os.makedirs(db_dir, exist_ok=True)
        except:
            pass

    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        c.execute('''CREATE TABLE IF NOT EXISTS PlaybackActivity (Id INTEGER PRIMARY KEY AUTOINCREMENT, UserId TEXT, UserName TEXT, ItemId TEXT, ItemName TEXT, PlayDuration INTEGER, DateCreated DATETIME DEFAULT CURRENT_TIMESTAMP, Client TEXT, DeviceName TEXT, RemoteEndPoint TEXT, Location TEXT, ISP TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS users_meta (user_id TEXT PRIMARY KEY, expire_date TEXT, note TEXT, created_at TEXT)''')

        # 🔥 风控模块：为老数据库无损新增"并发控制"和"风控等级"字段
        try: c.execute("ALTER TABLE users_meta ADD COLUMN max_concurrent INTEGER")
        except Exception: pass
        try: c.execute("ALTER TABLE users_meta ADD COLUMN risk_level TEXT DEFAULT 'safe'")
        except Exception: pass
        # 👇 添加这一行：新增 VIP 独立字段
        try: c.execute("ALTER TABLE users_meta ADD COLUMN is_vip INTEGER DEFAULT 0")
        except Exception: pass
        # 👇 新增：admin_disabled 字段，区分过期禁用和管理员禁用
        try: c.execute("ALTER TABLE users_meta ADD COLUMN admin_disabled INTEGER DEFAULT 0")
        except Exception: pass

        c.execute('''CREATE TABLE IF NOT EXISTS invitations (code TEXT PRIMARY KEY, days INTEGER, used_count INTEGER DEFAULT 0, max_uses INTEGER DEFAULT 1, created_at TEXT, used_at DATETIME, used_by TEXT, status INTEGER DEFAULT 0, template_user_id TEXT, type TEXT DEFAULT 'register', routes TEXT)''')
        try: c.execute("ALTER TABLE invitations ADD COLUMN template_user_id TEXT")
        except Exception: pass
        try: c.execute("ALTER TABLE invitations ADD COLUMN type TEXT DEFAULT 'register'")
        except Exception: pass
        try: c.execute("ALTER TABLE invitations ADD COLUMN routes TEXT")
        except Exception: pass
        try: c.execute("ALTER TABLE invitations ADD COLUMN route_mode TEXT DEFAULT 'block'")
        except Exception: pass

# 👇 商业化模块：新建本地凭证库，存储 Pro 激活码和状态
        c.execute('''CREATE TABLE IF NOT EXISTS sys_license (
            license_key TEXT,
            machine_id TEXT,
            pro_token TEXT,
            status TEXT DEFAULT 'pro',
            expire_date DATETIME,
            last_checked DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')

        c.execute('''CREATE TABLE IF NOT EXISTS tv_calendar_cache (id TEXT PRIMARY KEY, series_id TEXT, season INTEGER, episode INTEGER, air_date TEXT, status TEXT, data_json TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS media_requests (tmdb_id INTEGER, media_type TEXT, title TEXT, year TEXT, poster_path TEXT, status INTEGER DEFAULT 0, season INTEGER DEFAULT 0, reject_reason TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (tmdb_id, season))''')
        c.execute('''CREATE TABLE IF NOT EXISTS request_users (id INTEGER PRIMARY KEY AUTOINCREMENT, tmdb_id INTEGER, user_id TEXT, username TEXT, season INTEGER DEFAULT 0, requested_at DATETIME DEFAULT CURRENT_TIMESTAMP, UNIQUE(tmdb_id, user_id, season))''')
        c.execute('''CREATE TABLE IF NOT EXISTS request_admin_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tmdb_id INTEGER NOT NULL,
            chat_id TEXT NOT NULL,
            message_id INTEGER NOT NULL,
            is_caption INTEGER DEFAULT 1,
            original_text TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(tmdb_id, chat_id, message_id)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS insight_ignores (item_id TEXT PRIMARY KEY, item_name TEXT, ignored_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS gap_records (id INTEGER PRIMARY KEY AUTOINCREMENT, series_id TEXT, series_name TEXT, season_number INTEGER, episode_number INTEGER, status INTEGER DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, UNIQUE(series_id, season_number, episode_number))''')

        # 🔥 风控模块：新建独立的小黑屋与执法日志表
        c.execute('''CREATE TABLE IF NOT EXISTS risk_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, username TEXT, action TEXT, reason TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')

        # 👇 新增：系统全局通知表
        c.execute('''CREATE TABLE IF NOT EXISTS sys_notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT, title TEXT, message TEXT, is_read INTEGER DEFAULT 0, action_url TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')

        # 🤖 用户机器人相关表
        c.execute('''CREATE TABLE IF NOT EXISTS tg_user_bindings (tg_user_id TEXT PRIMARY KEY, tg_username TEXT DEFAULT '', emby_user_id TEXT, emby_username TEXT, init_password TEXT DEFAULT '', bound_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS tg_user_blacklist (tg_user_id TEXT PRIMARY KEY, reason TEXT DEFAULT '', created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        # 🔥 迁移：添加 tg_username 字段
        try: c.execute("ALTER TABLE tg_user_bindings ADD COLUMN tg_username TEXT DEFAULT ''")
        except Exception: pass

        # 🧩 插件系统
        c.execute('''CREATE TABLE IF NOT EXISTS plugin_state (plugin_id TEXT PRIMARY KEY, enabled INTEGER DEFAULT 0, config TEXT DEFAULT '{}')''')

        # 📊 仪表盘布局持久化
        c.execute('''CREATE TABLE IF NOT EXISTS sys_dashboard (id INTEGER PRIMARY KEY DEFAULT 1, layout_json TEXT)''')

        # 💰 积分系统（确保表存在）
        c.execute('''CREATE TABLE IF NOT EXISTS point_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, username TEXT, action TEXT, amount INTEGER, balance INTEGER, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS point_config (key TEXT PRIMARY KEY, value TEXT)''')
        # 🤖 开放注册日志表
        c.execute('''CREATE TABLE IF NOT EXISTS tg_reg_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, tg_user_id TEXT, emby_username TEXT, emby_user_id TEXT, reg_type TEXT DEFAULT 'open', created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        try: c.execute("ALTER TABLE users_meta ADD COLUMN points INTEGER DEFAULT 0")
        except Exception: pass
        # 🔥 屏蔽线路功能：新增用户专属屏蔽线路字段
        try: c.execute("ALTER TABLE users_meta ADD COLUMN block_routes TEXT DEFAULT ''")
        except Exception: pass
        # 🔥 允许线路功能：新增用户专属允许线路字段（可覆盖屏蔽设置）
        try: c.execute("ALTER TABLE users_meta ADD COLUMN allow_routes TEXT DEFAULT ''")
        except Exception: pass
        # 🔥 备注字段（忽略已存在的错误）
        try: c.execute("ALTER TABLE users_meta ADD COLUMN remark TEXT DEFAULT ''")
        except Exception: pass

        # 🔥 播放历史增强：新增 IP、归属地、运营商字段（兼容旧数据库）
        try: c.execute("ALTER TABLE PlaybackActivity ADD COLUMN RemoteEndPoint TEXT")
        except Exception: pass
        try: c.execute("ALTER TABLE PlaybackActivity ADD COLUMN Location TEXT")
        except Exception: pass
        try: c.execute("ALTER TABLE PlaybackActivity ADD COLUMN ISP TEXT")
        except Exception: pass

        # 🔥 性能优化：创建索引（大幅提升查询速度）
        # 播放历史表索引
        try: c.execute("CREATE INDEX IF NOT EXISTS idx_playback_user_date ON PlaybackActivity(UserId, DateCreated)")
        except Exception: pass
        try: c.execute("CREATE INDEX IF NOT EXISTS idx_playback_date ON PlaybackActivity(DateCreated)")
        except Exception: pass
        try: c.execute("CREATE INDEX IF NOT EXISTS idx_playback_item ON PlaybackActivity(ItemId)")
        except Exception: pass
        # 用户元数据索引
        try: c.execute("CREATE INDEX IF NOT EXISTS idx_users_meta_expire ON users_meta(expire_date)")
        except Exception: pass

        conn.commit()
        conn.close()
        print("✅ 数据库结构初始化完成.")
    except Exception as e:
        print(f"❌ DB Init Error: {e}")

    # 4. 确保消息中心表存在（系统库）
    try:
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
    except Exception as e:
        print(f"❌ 消息表初始化错误: {e}")


class APIRow(dict):
    """
    终极伪装者：让 API 返回的普通字典不仅能支持 FastAPI 的无损 JSON 序列化，
    还能像 sqlite3.Row 一样支持按索引(row[0])和忽略大小写的键名访问。
    """
    def __init__(self, original_dict):
        super().__init__(original_dict)
        self._vals = list(original_dict.values())
        self._lower_keys = {str(k).lower(): k for k in original_dict.keys()}

    def __getitem__(self, key):
        if isinstance(key, int):
            try: return self._vals[key]
            except IndexError: return None
        key_str = str(key)
        if super().__contains__(key_str):
            return super().__getitem__(key_str)
        key_lower = key_str.lower()
        if key_lower in self._lower_keys:
            return super().__getitem__(self._lower_keys[key_lower])
        return None

def _interpolate_sql(query: str, args) -> str:
    """将参数化查询转为拼接查询（仅用于 API 模式下提交给 Emby）"""
    if not args: return query
    parts = query.split('?')
    if len(parts) - 1 != len(args): return query
    res = parts[0]
    for i, arg in enumerate(args):
        if isinstance(arg, bool): val = "1" if arg else "0"
        elif isinstance(arg, (int, float)): val = str(arg)
        elif arg is None: val = "NULL"
        else:
            s = str(arg)
            # 转义反斜杠（必须最先处理）
            s = s.replace('\\', '\\\\')
            # 转义单引号
            s = s.replace("'", "''")
            # 移除 NULL 字节（所有变体）
            s = s.replace('\x00', '')
            s = s.replace('�', '')
            # 转义控制字符
            s = s.replace('\n', '\\n')
            s = s.replace('\r', '\\r')
            s = s.replace('\t', '\\t')
            s = s.replace('\x1a', '\\Z')
            # 移除 SQL 注释序列
            s = s.replace('/*', '')
            s = s.replace('*/', '')
            # 移除反引号（防止标识符注入）
            s = s.replace('`', '')
            val = f"'{s}'"
        res += val + parts[i+1]
    return res

def get_db_path_for_query(query: str) -> str:
    """
    根据查询类型返回对应的数据库路径
    - 系统表查询 -> SYSTEM_DB_PATH（固定）
    - 播放表查询 -> DB_PATH（可配置，支持挂载或API）
    """
    query_upper = query.upper()

    # 播放相关表（走原路径，支持挂载或API）
    playback_keywords = ["PLAYBACKACTIVITY", "PLAYBACKREPORTING", "TV_CALENDAR_CACHE"]
    for keyword in playback_keywords:
        if keyword in query_upper:
            return DB_PATH

    # 系统表（走固定系统库）
    return SYSTEM_DB_PATH


def get_playback_column_name() -> str:
    """
    自动检测 PlaybackActivity 表中客户端列的名称
    兼容不同版本的 Emby/Jellyfin 插件数据库
    支持 API 模式和 SQLite 模式
    返回: 'ClientName' 或 'Client' 或 'client'
    """
    try:
        # 🔥 用 SELECT 查询检测列名，兼容 API 模式
        test_res = query_db("SELECT * FROM PlaybackActivity LIMIT 1", [])
        
        if test_res and len(test_res) > 0:
            first_row = test_res[0]
            # 获取列名
            if hasattr(first_row, 'keys'):
                available_cols = list(first_row.keys())
            elif isinstance(first_row, dict):
                available_cols = list(first_row.keys())
            else:
                available_cols = []
            
            # 检查大小写不敏感
            col_map = {c.lower(): c for c in available_cols}
            
            # 优先使用 ClientName（Pulse 添加的标准列）
            if 'clientname' in col_map:
                return col_map['clientname']
            # 其次使用 Client
            if 'client' in col_map:
                return col_map['client']
        
        # 兜底返回 Client，兼容旧版 Emby 插件
        return 'Client'
    except Exception as e:
        logger.warning(f"[列检测] 检测 PlaybackActivity 列失败: {e}，默认使用 Client")
        return 'Client'


def query_db(query, args=(), one=False):
    started = time.perf_counter()
    mode = cfg.get("playback_data_mode", "sqlite")
    is_playback_query = "PlaybackActivity" in query or "PlaybackReporting" in query or "tv_calendar_cache" in query.lower()

    # ==========================================
    # 🔥 双擎路由拦截器 (API 穿透模式)
    # ==========================================
    if mode == "api" and is_playback_query:
        host = cfg.get("emby_host")
        token = cfg.get("emby_api_key")
        if host and token:
            full_sql = _interpolate_sql(query, args)
            url = f"{host.rstrip('/')}/emby/user_usage_stats/submit_custom_query"
            headers = {"X-Emby-Token": token, "Content-Type": "application/json"}
            payload = {"CustomQueryString": full_sql}

            try:
                res = requests.post(url, headers=headers, json=payload, timeout=20)

                if res.status_code == 200:
                    raw_data = None
                    try:
                        res_json = res.json()
                        if isinstance(res_json, str):
                            try: raw_data = json.loads(res_json)
                            except: raw_data = res_json
                        else:
                            raw_data = res_json
                    except:
                        try: raw_data = json.loads(res.text)
                        except: raw_data = {}

                    final_data = []

                    if isinstance(raw_data, dict):
                        # 💡 核心拉链缝合逻辑开始：专门对付 Emby 插件的奇葩结构
                        columns = raw_data.get("colums") or raw_data.get("columns") # 兼容作者拼写错误
                        results = raw_data.get("results")

                        if columns and isinstance(results, list):
                            # 是那种带表头和二维数组的变态格式
                            for row in results:
                                if isinstance(row, list):
                                    row_dict = {}
                                    for i, col_name in enumerate(columns):
                                        val = row[i] if i < len(row) else None
                                        # 🔥 智能类型推断：把 "2267" 这种字符串变回纯数字
                                        if isinstance(val, str) and val.isdigit():
                                            val = int(val)
                                        row_dict[col_name] = val
                                    final_data.append(row_dict)
                        else:
                            # 如果它抽风返回了正常的结构 (防患于未然)
                            extracted = raw_data.get("results", raw_data.get("Items", [raw_data]))
                            final_data = extracted if isinstance(extracted, list) else [extracted]

                    elif isinstance(raw_data, list):
                        final_data = raw_data
                    else:
                        final_data = [raw_data] if raw_data else []

                    # 使用神级 APIRow 类包裹，前端不再罢工
                    data = [APIRow(item) if isinstance(item, dict) else item for item in final_data]

                    if query.strip().upper().startswith("SELECT"):
                        _record_query_perf(query, (time.perf_counter() - started) * 1000, len(data))
                        return (data[0] if data else None) if one else data
                    _record_query_perf(query, (time.perf_counter() - started) * 1000, 0)
                    return True
                else:
                    print(f"[API 引擎] ❌ 接口拒绝请求! 响应: {res.text[:200]}")
            except Exception as e:
                print(f"[API 引擎] ❌ 网络崩溃异常: {e}")
        else:
            print("[API 引擎] ⚠️ 警告: Emby Host 或 Token 未配置，自动降级回 SQLite。")

    # ==========================================
    # 🚂 原版 SQLite 执行器 (处理非播放表及降级情况)
    # ==========================================

    # 🔥 根据查询类型选择数据库路径
    target_db = get_db_path_for_query(query)

    # 检查挂载目录是否存在（仅在需要访问挂载路径时）
    if target_db == DB_PATH and DB_PATH.startswith("/emby-data"):
        emby_data_dir = "/emby-data"
        if not os.path.exists(emby_data_dir):
            print(f"[📁 挂载检测] ⚠️ 未检测到 Emby 数据挂载: {emby_data_dir}")
            print(f"[📁 挂载检测] 播放统计功能将不可用，请配置 API 模式或挂载数据库")
            # 如果是播放查询且没挂载，返回 None
            if is_playback_query:
                return None

    if not os.path.exists(target_db):
        if target_db == SYSTEM_DB_PATH:
            print(f"[SQLite 引擎] ⚠️ 系统数据库不存在: {target_db}")
        else:
            print(f"[SQLite 引擎] ⚠️ 数据库文件不存在: {target_db}")
            print(f"[SQLite 引擎] 请确保已正确挂载 Emby 插件的 playback_reporting.db")
        return None

    try:
        conn = sqlite3.connect(target_db, timeout=20.0)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(query, args)
        if query.strip().upper().startswith("SELECT"):
            if one:
                row = cur.fetchone()
                conn.close()
                result = APIRow(dict(row)) if row else None
                _record_query_perf(query, (time.perf_counter() - started) * 1000, 1 if row else 0)
                return result
            rv = cur.fetchall()
            conn.close()
            # 🔥 包装成 APIRow，统一支持 .get() 方法
            rv = [APIRow(dict(row)) for row in rv]
            _record_query_perf(query, (time.perf_counter() - started) * 1000, len(rv))
            return rv
        else:
            conn.commit()
            conn.close()
            _record_query_perf(query, (time.perf_counter() - started) * 1000, 0)
            return True
    except sqlite3.OperationalError as e:
        err_msg = str(e).lower()
        if "no such table" in err_msg:
            print(f"[SQLite 引擎] ❌ 表不存在: {e}")
            print(f"[SQLite 引擎] 请确认 Emby 插件是否已正确运行并创建数据库表")
        elif "no such column" in err_msg:
            print(f"[SQLite 引擎] ❌ 列不存在: {e}")
            print(f"[SQLite 引擎] 可能是插件版本差异，请检查插件版本")
        elif "duplicate column" in err_msg:
            # 🔥 列已存在是正常的迁移情况，不打印错误
            pass
        elif "read-only" in err_msg:
            print(f"[SQLite 引擎] ❌ 数据库为只读: {e}")
            print(f"[SQLite 引擎] 请检查 Docker 卷挂载是否为读写模式")
        else:
            print(f"[SQLite 引擎] 💥 数据库操作失败: {e}")
        return None
    except Exception as e:
        print(f"[SQLite 引擎] 💥 未知错误: {e}")
        return None

def get_base_filter(user_id_filter):
    where = "WHERE 1=1"
    params = []

    if user_id_filter and user_id_filter != 'all':
        where += " AND UserId = ?"
        params.append(user_id_filter)

    hidden = cfg.get("hidden_users")
    if (not user_id_filter or user_id_filter == 'all') and hidden and len(hidden) > 0:
        placeholders = ','.join(['?'] * len(hidden))
        where += f" AND UserId NOT IN ({placeholders})"
        params.extend(hidden)

    return where, params

# 👇 核心修复：强制获取北京时间并显式写入，拒绝使用 SQLite 默认的 UTC 零时区！
def add_sys_notification(notify_type: str, title: str, message: str, action_url: str = ""):
    try:
        add_system_notification(notify_type, title, message, action_url)
    except Exception as e:
        logger.error(f"[系统通知] 写入数据库失败: {e}")
