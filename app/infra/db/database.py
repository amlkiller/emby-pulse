import sqlite3
import os
import logging
import datetime  # 🔥 新增导入 datetime 模块
import shutil
from app.core.config import DB_PATH, SYSTEM_DB_PATH
from app.infra.db.notification_dao import add_system_notification
from app.infra.db.playback_filters import get_base_filter as _get_base_filter
from app.infra.db.query_perf import get_query_perf_stats
from app.infra.db.schema_bootstrap import ensure_registered_table
from app.infra.db.schema_registry import PLAYBACK_TABLES, SYSTEM_TABLES

_REGISTRY_SYSTEM_INIT_TABLES = (
    "invitations",
    "sys_license",
    "tv_calendar_cache",
    "request_users",
    "request_admin_messages",
    "insight_ignores",
    "gap_records",
    "risk_logs",
    "sys_notifications",
    "tg_user_bindings",
    "tg_user_blacklist",
    "plugin_state",
    "sys_dashboard",
    "point_logs",
    "point_config",
    "msg_conversations",
    "msg_items",
    "msg_notify_block",
    "tg_reg_logs",
    "task_translations",
    "task_config",
    "media_feedback",
    "client_blacklist",
    "notify_mutes",
    "notify_rules",
    "UserList",
    "gap_config",
    "gap_perfect_series",
    "gap_scan_cache",
    "dedupe_results",
    "dedupe_whitelist",
    "dedupe_config",
    "plugin_logs",
    "user_mutes",
    "keep_alive_violations",
    "local_users",
    "bot_notify_mutes",
)

# 🔥 导出 SYSTEM_DB_PATH 供其他模块使用
__all__ = ['init_db', 'get_base_filter', 'add_sys_notification',
           'DB_PATH', 'SYSTEM_DB_PATH', 'auto_migrate_system_db', 'get_db_connection',
           'get_query_perf_stats', 'PLAYBACK_TABLES', 'SYSTEM_TABLES']

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
    ensure_registered_table(c, "users_meta")

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

    # 🔥 用户标签配置表
    c.execute('''CREATE TABLE IF NOT EXISTS user_tags (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, color TEXT DEFAULT 'blue', created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    c.execute('''CREATE TABLE IF NOT EXISTS tv_series_status (tmdb_id TEXT PRIMARY KEY, series_name TEXT, status TEXT DEFAULT 'continuing', last_checked TEXT, updated_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS media_requests (tmdb_id INTEGER, media_type TEXT, title TEXT, year TEXT, poster_path TEXT, status INTEGER DEFAULT 0, season INTEGER DEFAULT 0, reject_reason TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (tmdb_id, season))''')

    for table_name in _REGISTRY_SYSTEM_INIT_TABLES:
        ensure_registered_table(c, table_name)
    
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
        ensure_registered_table(c, "users_meta")

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


def get_base_filter(user_id_filter):
    return _get_base_filter(user_id_filter)

# 👇 核心修复：强制获取北京时间并显式写入，拒绝使用 SQLite 默认的 UTC 零时区！
def add_sys_notification(notify_type: str, title: str, message: str, action_url: str = ""):
    try:
        add_system_notification(notify_type, title, message, action_url)
    except Exception as e:
        logger.error(f"[系统通知] 写入数据库失败: {e}")
