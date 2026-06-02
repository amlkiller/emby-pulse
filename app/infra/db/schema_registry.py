# -*- coding: utf-8 -*-
"""
统一数据库表结构定义
所有系统表的 CREATE 和 ALTER 语句都在这里维护
新增表只需在 TABLE_SCHEMAS 和 SYSTEM_TABLES 中添加即可
"""

# 🔥 系统数据表清单（与 SYSTEM_TABLES 保持同步）
SYSTEM_TABLES = [
    "users_meta", "user_tags", "invitations", "sys_license", "tg_user_bindings",
    "tg_user_blacklist", "tg_bot_users", "tg_channel_bindings",
    "media_requests", "request_users", "media_feedback",
    "request_admin_messages", "risk_logs", "sys_notifications", "point_logs", "point_config",
    "plugin_state", "plugin_logs", "sys_dashboard", "insight_ignores", "notify_mutes",
    "UserList", "client_blacklist", "client_whitelist", "gap_records", "gap_config",
    "gap_perfect_series", "gap_scan_cache", "dedupe_results", "dedupe_whitelist",
    "dedupe_config", "keep_alive_violations",
    "temp_accounts", "temp_account_password_history",
    "season_poster_logs", "season_poster_cache", "emby_restart_history",
    "smart_collections", "smart_collection_items", "smart_collection_sync_logs",
    "task_config", "task_translations", "tv_calendar_cache", "tv_series_status", "tg_reg_logs",
    "local_users", "login_failures", "api_tokens",
    "msg_conversations", "msg_items", "msg_notify_block", "user_mutes",
    "announcements", "announcement_reads",
    "bot_notify_mutes", "user_audit_logs", "notify_rules", "calendar_notify_config",
    "pwa_config", "user_pwa_icons",
    "lottery_tickets", "lottery_results", "lottery_winners",
    "scratch_cards", "scratch_card_slots", "point_checkin_streak",
    "point_red_packets", "point_red_packet_logs", "point_transfer_logs",
    "point_rob_logs", "pk_invitations", "pk_logs"
]

# 🔥 播放数据表（不迁移，保持原库读取）
PLAYBACK_TABLES = ["PlaybackActivity"]

# 🔥 统一表结构定义 - 新增表只需在这里添加
TABLE_SCHEMAS = {
    # ==================== 用户与权限 ====================
    "users_meta": """CREATE TABLE IF NOT EXISTS users_meta (
        user_id TEXT PRIMARY KEY,
        expire_date TEXT,
        note TEXT,
        created_at TEXT,
        max_concurrent INTEGER,
        risk_level TEXT DEFAULT 'safe',
        is_vip INTEGER DEFAULT 0,
        points INTEGER DEFAULT 0,
        block_routes TEXT DEFAULT '',
        allow_routes TEXT DEFAULT '',
        remark TEXT DEFAULT '',
        admin_disabled INTEGER DEFAULT 0,
        req_free INTEGER DEFAULT 0,
        req_free_count INTEGER DEFAULT -1,
        tags TEXT DEFAULT '',
        emby_pw_hash TEXT DEFAULT '',
        admin_enabled_folders TEXT,
        hidden_libraries TEXT DEFAULT ''
    )""",

    "user_tags": """CREATE TABLE IF NOT EXISTS user_tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        color TEXT DEFAULT 'blue',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    "invitations": """CREATE TABLE IF NOT EXISTS invitations (
        code TEXT PRIMARY KEY,
        days INTEGER,
        used_count INTEGER DEFAULT 0,
        max_uses INTEGER DEFAULT 1,
        created_at TEXT,
        used_at DATETIME,
        used_by TEXT,
        status INTEGER DEFAULT 0,
        template_user_id TEXT,
        type TEXT DEFAULT 'register',
        routes TEXT,
        route_mode TEXT DEFAULT 'block',
        req_free INTEGER DEFAULT 0,
        req_free_count INTEGER DEFAULT -1
    )""",

    "sys_license": """CREATE TABLE IF NOT EXISTS sys_license (
        license_key TEXT,
        machine_id TEXT,
        pro_token TEXT,
        status TEXT DEFAULT 'pro',
        expire_date DATETIME,
        last_checked DATETIME DEFAULT CURRENT_TIMESTAMP,
        max_devices INTEGER,
        current_devices INTEGER
    )""",

    # ==================== TG 机器人 ====================
    "tg_user_bindings": """CREATE TABLE IF NOT EXISTS tg_user_bindings (
        tg_user_id TEXT PRIMARY KEY,
        tg_username TEXT DEFAULT '',
        tg_display_name TEXT DEFAULT '',
        emby_user_id TEXT,
        emby_username TEXT,
        init_password TEXT DEFAULT '',
        bound_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    "tg_user_blacklist": """CREATE TABLE IF NOT EXISTS tg_user_blacklist (
        tg_user_id TEXT PRIMARY KEY,
        reason TEXT DEFAULT '',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    "tg_bot_users": """CREATE TABLE IF NOT EXISTS tg_bot_users (
        tg_user_id TEXT PRIMARY KEY,
        tg_name TEXT DEFAULT '',
        first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
        last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    "tg_channel_bindings": """CREATE TABLE IF NOT EXISTS tg_channel_bindings (
        channel_id TEXT PRIMARY KEY,
        tg_user_id TEXT,
        channel_title TEXT DEFAULT '',
        bound_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    "tg_reg_logs": """CREATE TABLE IF NOT EXISTS tg_reg_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tg_user_id TEXT,
        emby_username TEXT,
        emby_user_id TEXT,
        reg_type TEXT DEFAULT 'open',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    # ==================== 求片系统 ====================
    "media_requests": """CREATE TABLE IF NOT EXISTS media_requests (
        tmdb_id INTEGER,
        media_type TEXT,
        title TEXT,
        year TEXT,
        poster_path TEXT,
        status INTEGER DEFAULT 0,
        season INTEGER DEFAULT 0,
        episodes TEXT DEFAULT '',
        request_type TEXT DEFAULT 'new',
        series_id TEXT DEFAULT '',
        reject_reason TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (tmdb_id, season)
    )""",

    "request_users": """CREATE TABLE IF NOT EXISTS request_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tmdb_id INTEGER,
        user_id TEXT,
        username TEXT,
        season INTEGER DEFAULT 0,
        requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(tmdb_id, user_id, season)
    )""",

    "request_admin_messages": """CREATE TABLE IF NOT EXISTS request_admin_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tmdb_id INTEGER NOT NULL,
        chat_id TEXT NOT NULL,
        message_id INTEGER NOT NULL,
        is_caption INTEGER DEFAULT 1,
        original_text TEXT DEFAULT '',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(tmdb_id, chat_id, message_id)
    )""",

    "media_feedback": """CREATE TABLE IF NOT EXISTS media_feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_name TEXT,
        user_id TEXT,
        username TEXT,
        issue_type TEXT,
        description TEXT,
        status INTEGER DEFAULT 0,
        poster_path TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    # ==================== 风控系统 ====================
    "risk_logs": """CREATE TABLE IF NOT EXISTS risk_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        username TEXT,
        action TEXT,
        reason TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    # ==================== 客户端管控 ====================
    "client_blacklist": """CREATE TABLE IF NOT EXISTS client_blacklist (
        app_name TEXT PRIMARY KEY,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    "client_whitelist": """CREATE TABLE IF NOT EXISTS client_whitelist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        user_name TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id)
    )""",

    # ==================== 通知系统 ====================
    "sys_notifications": """CREATE TABLE IF NOT EXISTS sys_notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT,
        title TEXT,
        message TEXT,
        is_read INTEGER DEFAULT 0,
        action_url TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    "notify_mutes": """CREATE TABLE IF NOT EXISTS notify_mutes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        mute_type TEXT,
        mute_target TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, mute_type, mute_target)
    )""",

    # ==================== 通知规则配置 ====================
    "notify_rules": """CREATE TABLE IF NOT EXISTS notify_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        notify_type TEXT UNIQUE NOT NULL,
        notify_name TEXT NOT NULL,
        channels TEXT DEFAULT '[]',
        enabled INTEGER DEFAULT 1,
        config TEXT DEFAULT '{}',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    "calendar_notify_config": """CREATE TABLE IF NOT EXISTS calendar_notify_config (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        enabled INTEGER DEFAULT 0,
        notify_time TEXT DEFAULT '09:00',
        channels TEXT DEFAULT '["tg_bot"]',
        tg_chat_id TEXT,
        wecom_touser TEXT DEFAULT '@all',
        last_sent TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    # ==================== 积分系统 ====================
    "point_logs": """CREATE TABLE IF NOT EXISTS point_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        username TEXT,
        action TEXT,
        amount INTEGER,
        balance INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    "point_config": """CREATE TABLE IF NOT EXISTS point_config (
        key TEXT PRIMARY KEY,
        value TEXT
    )""",

    "lottery_tickets": """CREATE TABLE IF NOT EXISTS lottery_tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        username TEXT,
        numbers TEXT NOT NULL,
        cost INTEGER,
        draw_date TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    "lottery_results": """CREATE TABLE IF NOT EXISTS lottery_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        draw_date TEXT NOT NULL UNIQUE,
        winning_numbers TEXT NOT NULL,
        total_pool INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    "lottery_winners": """CREATE TABLE IF NOT EXISTS lottery_winners (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        username TEXT,
        ticket_id INTEGER,
        prize_level INTEGER,
        prize_amount INTEGER,
        draw_date TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    "scratch_cards": """CREATE TABLE IF NOT EXISTS scratch_cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        total_slots INTEGER DEFAULT 9,
        filled_slots INTEGER DEFAULT 0,
        price INTEGER DEFAULT 100,
        status TEXT DEFAULT 'active',
        created_by TEXT,
        chat_id TEXT DEFAULT '',
        message_id INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    "scratch_card_slots": """CREATE TABLE IF NOT EXISTS scratch_card_slots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        card_id INTEGER NOT NULL,
        slot_number INTEGER NOT NULL,
        prize_amount INTEGER NOT NULL,
        is_scratched INTEGER DEFAULT 0,
        user_id TEXT,
        username TEXT,
        scratched_at DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    "point_checkin_streak": """CREATE TABLE IF NOT EXISTS point_checkin_streak (
        user_id TEXT PRIMARY KEY,
        streak_count INTEGER DEFAULT 0,
        last_checkin DATE
    )""",

    "point_red_packets": """CREATE TABLE IF NOT EXISTS point_red_packets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        total_amount INTEGER,
        remain_amount INTEGER,
        total_count INTEGER,
        remain_count INTEGER,
        creator_id TEXT,
        creator_name TEXT,
        chat_id TEXT,
        message_id TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        expires_at DATETIME
    )""",

    "point_red_packet_logs": """CREATE TABLE IF NOT EXISTS point_red_packet_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        packet_id INTEGER,
        user_id TEXT,
        user_name TEXT,
        amount INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    "point_transfer_logs": """CREATE TABLE IF NOT EXISTS point_transfer_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_user_id TEXT,
        from_user_name TEXT,
        to_user_id TEXT,
        to_user_name TEXT,
        amount INTEGER,
        fee INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    "point_rob_logs": """CREATE TABLE IF NOT EXISTS point_rob_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_user_id TEXT,
        from_user_name TEXT,
        to_user_id TEXT,
        to_user_name TEXT,
        amount INTEGER,
        success INTEGER DEFAULT 0,
        counter_amount INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    "pk_invitations": """CREATE TABLE IF NOT EXISTS pk_invitations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        challenger_id TEXT,
        challenger_name TEXT,
        challenger_tg_name TEXT,
        target_id TEXT,
        target_name TEXT,
        target_tg_name TEXT,
        points INTEGER,
        chat_id TEXT,
        message_id TEXT,
        command_message_id TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        expires_at DATETIME,
        status TEXT DEFAULT 'pending'
    )""",

    "pk_logs": """CREATE TABLE IF NOT EXISTS pk_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        challenger_id TEXT,
        challenger_name TEXT,
        target_id TEXT,
        target_name TEXT,
        points INTEGER,
        challenger_roll INTEGER,
        target_roll INTEGER,
        winner_id TEXT,
        winner_name TEXT,
        tax INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    # ==================== PWA 配置 ====================
    "pwa_config": """CREATE TABLE IF NOT EXISTS pwa_config (
        key TEXT PRIMARY KEY,
        value TEXT
    )""",

    "user_pwa_icons": """CREATE TABLE IF NOT EXISTS user_pwa_icons (
        user_id TEXT PRIMARY KEY,
        icon_id TEXT
    )""",

    # ==================== 插件系统 ====================
    "plugin_state": """CREATE TABLE IF NOT EXISTS plugin_state (
        plugin_id TEXT PRIMARY KEY,
        enabled INTEGER DEFAULT 0,
        config TEXT DEFAULT '{}'
    )""",

    # ==================== 仪表盘 ====================
    "sys_dashboard": """CREATE TABLE IF NOT EXISTS sys_dashboard (
        id INTEGER PRIMARY KEY DEFAULT 1,
        layout_json TEXT
    )""",

    # ==================== 洞察与忽略 ====================
    "insight_ignores": """CREATE TABLE IF NOT EXISTS insight_ignores (
        item_id TEXT PRIMARY KEY,
        item_name TEXT,
        ignored_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    # ==================== 用户列表 ====================
    "UserList": """CREATE TABLE IF NOT EXISTS UserList (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        list_name TEXT,
        list_type TEXT,
        user_ids TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    # ==================== 缺集管理 ====================
    "gap_records": """CREATE TABLE IF NOT EXISTS gap_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        series_id TEXT,
        series_name TEXT,
        season_number INTEGER,
        episode_number INTEGER,
        status INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(series_id, season_number, episode_number)
    )""",

    "gap_config": """CREATE TABLE IF NOT EXISTS gap_config (
        key TEXT PRIMARY KEY,
        value TEXT,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    "gap_perfect_series": """CREATE TABLE IF NOT EXISTS gap_perfect_series (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        series_id TEXT,
        tmdb_id TEXT,
        series_name TEXT,
        total_seasons INTEGER,
        total_episodes INTEGER,
        marked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(series_id)
    )""",

    "gap_scan_cache": """CREATE TABLE IF NOT EXISTS gap_scan_cache (
        id INTEGER PRIMARY KEY,
        result_json TEXT,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    # ==================== 去重系统 ====================
    "dedupe_results": """CREATE TABLE IF NOT EXISTS dedupe_results (
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
    )""",

    "dedupe_whitelist": """CREATE TABLE IF NOT EXISTS dedupe_whitelist (
        group_key TEXT PRIMARY KEY,
        title TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    # ==================== 任务系统 ====================
    "task_config": """CREATE TABLE IF NOT EXISTS task_config (
        key TEXT PRIMARY KEY,
        value TEXT
    )""",

    "task_translations": """CREATE TABLE IF NOT EXISTS task_translations (
        original_name TEXT PRIMARY KEY,
        translated_name TEXT
    )""",

    # ==================== 追剧日历 ====================
    "tv_calendar_cache": """CREATE TABLE IF NOT EXISTS tv_calendar_cache (
        id TEXT PRIMARY KEY,
        series_id TEXT,
        season INTEGER,
        episode INTEGER,
        air_date TEXT,
        status TEXT,
        data_json TEXT
    )""",

    "tv_series_status": """CREATE TABLE IF NOT EXISTS tv_series_status (
        tmdb_id TEXT PRIMARY KEY,
        series_name TEXT,
        status TEXT DEFAULT 'continuing',
        last_checked TEXT,
        updated_at TEXT
    )""",

    # ==================== 本地用户认证 ====================
    "local_users": """CREATE TABLE IF NOT EXISTS local_users (
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
        last_login_ip TEXT,
        totp_secret TEXT DEFAULT '',
        totp_enabled INTEGER DEFAULT 0,
        totp_pending_secret TEXT DEFAULT ''
    )""",

    "login_failures": """CREATE TABLE IF NOT EXISTS login_failures (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lock_key TEXT NOT NULL UNIQUE,
        lock_type TEXT NOT NULL,
        failure_count INTEGER DEFAULT 0,
        locked_until DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    "api_tokens": """CREATE TABLE IF NOT EXISTS api_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        token TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        expires_at DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        last_used_at DATETIME,
        FOREIGN KEY (user_id) REFERENCES users_meta(user_id)
    )""",

    # ==================== 消息中心 ====================
    "msg_conversations": """CREATE TABLE IF NOT EXISTS msg_conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        username TEXT,
        user_avatar TEXT,
        last_message TEXT,
        last_time DATETIME DEFAULT CURRENT_TIMESTAMP,
        unread_admin INTEGER DEFAULT 0,
        unread_user INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    "msg_items": """CREATE TABLE IF NOT EXISTS msg_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id INTEGER,
        sender_type TEXT DEFAULT 'admin',
        sender_id TEXT,
        sender_name TEXT,
        content TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    "msg_notify_block": """CREATE TABLE IF NOT EXISTS msg_notify_block (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    # ==================== 用户禁言 ====================
    "user_mutes": """CREATE TABLE IF NOT EXISTS user_mutes (
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
    )""",

    "announcements": """CREATE TABLE IF NOT EXISTS announcements (
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
    )""",

    "announcement_reads": """CREATE TABLE IF NOT EXISTS announcement_reads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        announcement_id INTEGER NOT NULL,
        user_id TEXT NOT NULL,
        read_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(announcement_id, user_id)
    )""",

    # ==================== 插件日志 ====================
    "plugin_logs": """CREATE TABLE IF NOT EXISTS plugin_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plugin_id TEXT NOT NULL,
        level TEXT DEFAULT 'info',
        message TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    # ==================== 去重配置 ====================
    "dedupe_config": """CREATE TABLE IF NOT EXISTS dedupe_config (
        key TEXT PRIMARY KEY,
        value TEXT,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",

    # ==================== 保活违规记录 ====================
    "keep_alive_violations": """CREATE TABLE IF NOT EXISTS keep_alive_violations (
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
    )""",

    "temp_accounts": """CREATE TABLE IF NOT EXISTS temp_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        emby_user_id TEXT,
        current_password TEXT NOT NULL,
        template_user_id TEXT,
        allow_routes TEXT DEFAULT '',
        block_routes TEXT DEFAULT '',
        req_free INTEGER DEFAULT 0,
        req_free_count INTEGER DEFAULT -1,
        auto_update_enabled INTEGER DEFAULT 1,
        update_interval_hours INTEGER DEFAULT 24,
        update_interval_minutes INTEGER DEFAULT 0,
        last_password_update TEXT,
        next_password_update TEXT,
        notify_tg INTEGER DEFAULT 1,
        notify_wecom INTEGER DEFAULT 0,
        enabled INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        remark TEXT DEFAULT '临时账号',
        tags TEXT DEFAULT ''
    )""",

    "temp_account_password_history": """CREATE TABLE IF NOT EXISTS temp_account_password_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL,
        old_password TEXT,
        new_password TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        notify_sent INTEGER DEFAULT 0,
        FOREIGN KEY (account_id) REFERENCES temp_accounts(id)
    )""",

    "season_poster_logs": """CREATE TABLE IF NOT EXISTS season_poster_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        time TEXT NOT NULL,
        series_id TEXT,
        series_name TEXT,
        season_number INTEGER,
        old_poster TEXT,
        new_poster TEXT,
        success INTEGER,
        message TEXT
    )""",

    "season_poster_cache": """CREATE TABLE IF NOT EXISTS season_poster_cache (
        series_id TEXT PRIMARY KEY,
        series_name TEXT,
        season_count INTEGER,
        last_season_number INTEGER,
        last_updated TEXT
    )""",

    "emby_restart_history": """CREATE TABLE IF NOT EXISTS emby_restart_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        time TEXT NOT NULL,
        mode TEXT,
        success INTEGER,
        detail TEXT
    )""",

    "smart_collections": """CREATE TABLE IF NOT EXISTS smart_collections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        icon TEXT DEFAULT 'fa-layer-group',
        icon_color TEXT DEFAULT 'from-purple-500 to-pink-500',
        source_type TEXT DEFAULT 'tmdb_trending',
        source_config TEXT DEFAULT '{}',
        min_rating REAL DEFAULT 7.0,
        update_mode TEXT DEFAULT 'incremental',
        is_enabled INTEGER DEFAULT 1,
        last_sync TEXT,
        last_count INTEGER DEFAULT 0,
        created_at TEXT,
        updated_at TEXT
    )""",

    "smart_collection_items": """CREATE TABLE IF NOT EXISTS smart_collection_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collection_id INTEGER NOT NULL,
        item_id TEXT NOT NULL,
        tmdb_id TEXT,
        title TEXT,
        sort_order INTEGER DEFAULT 0,
        added_at TEXT,
        FOREIGN KEY (collection_id) REFERENCES smart_collections(id) ON DELETE CASCADE,
        UNIQUE(collection_id, item_id)
    )""",

    "smart_collection_sync_logs": """CREATE TABLE IF NOT EXISTS smart_collection_sync_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collection_id INTEGER,
        action TEXT,
        status TEXT,
        message TEXT,
        count INTEGER DEFAULT 0,
        created_at TEXT
    )""",

    # ==================== 机器人通知屏蔽 ====================
    "bot_notify_mutes": """CREATE TABLE IF NOT EXISTS bot_notify_mutes (
        user_id TEXT,
        event_type TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, event_type)
    )""",

    # ==================== 用户操作审计日志 ====================
    "user_audit_logs": """CREATE TABLE IF NOT EXISTS user_audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id TEXT NOT NULL,
        admin_name TEXT NOT NULL,
        action TEXT NOT NULL,
        target_user_id TEXT,
        target_user_name TEXT,
        target_count INTEGER DEFAULT 0,
        details TEXT DEFAULT '',
        ip_address TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )"""
}

# 🔥 表字段增量更新 - 用于 ALTER TABLE
TABLE_ALTERS = {
    "users_meta": [
        "ALTER TABLE users_meta ADD COLUMN max_concurrent INTEGER",
        "ALTER TABLE users_meta ADD COLUMN risk_level TEXT DEFAULT 'safe'",
        "ALTER TABLE users_meta ADD COLUMN is_vip INTEGER DEFAULT 0",
        "ALTER TABLE users_meta ADD COLUMN points INTEGER DEFAULT 0",
        "ALTER TABLE users_meta ADD COLUMN block_routes TEXT DEFAULT ''",
        "ALTER TABLE users_meta ADD COLUMN allow_routes TEXT DEFAULT ''",
        "ALTER TABLE users_meta ADD COLUMN remark TEXT DEFAULT ''",
        "ALTER TABLE users_meta ADD COLUMN admin_disabled INTEGER DEFAULT 0",
        "ALTER TABLE users_meta ADD COLUMN req_free INTEGER DEFAULT 0",
        "ALTER TABLE users_meta ADD COLUMN req_free_count INTEGER DEFAULT -1",
        "ALTER TABLE users_meta ADD COLUMN tags TEXT DEFAULT ''",
        "ALTER TABLE users_meta ADD COLUMN emby_pw_hash TEXT DEFAULT ''",
        "ALTER TABLE users_meta ADD COLUMN admin_enabled_folders TEXT",
        "ALTER TABLE users_meta ADD COLUMN hidden_libraries TEXT DEFAULT ''"
    ],
    "invitations": [
        "ALTER TABLE invitations ADD COLUMN template_user_id TEXT",
        "ALTER TABLE invitations ADD COLUMN type TEXT DEFAULT 'register'",
        "ALTER TABLE invitations ADD COLUMN routes TEXT",
        "ALTER TABLE invitations ADD COLUMN route_mode TEXT DEFAULT 'block'",
        "ALTER TABLE invitations ADD COLUMN req_free INTEGER DEFAULT 0",
        "ALTER TABLE invitations ADD COLUMN req_free_count INTEGER DEFAULT -1"
    ],
    "sys_notifications": [
        "ALTER TABLE sys_notifications ADD COLUMN is_cleared INTEGER DEFAULT 0"
    ],
    "sys_license": [
        "ALTER TABLE sys_license ADD COLUMN pro_token TEXT",
        "ALTER TABLE sys_license ADD COLUMN expire_date DATETIME",
        "ALTER TABLE sys_license ADD COLUMN last_checked DATETIME",
        "ALTER TABLE sys_license ADD COLUMN max_devices INTEGER",
        "ALTER TABLE sys_license ADD COLUMN current_devices INTEGER"
    ],
    "tg_user_bindings": [
        "ALTER TABLE tg_user_bindings ADD COLUMN init_password TEXT DEFAULT ''",
        "ALTER TABLE tg_user_bindings ADD COLUMN tg_username TEXT DEFAULT ''",
        "ALTER TABLE tg_user_bindings ADD COLUMN tg_display_name TEXT DEFAULT ''"
    ],
    "local_users": [
        "ALTER TABLE local_users ADD COLUMN role TEXT DEFAULT 'admin'",
        "ALTER TABLE local_users ADD COLUMN remark TEXT DEFAULT ''",
        "ALTER TABLE local_users ADD COLUMN avatar TEXT DEFAULT ''",
        "ALTER TABLE local_users ADD COLUMN is_enabled INTEGER DEFAULT 1",
        "ALTER TABLE local_users ADD COLUMN permissions TEXT DEFAULT '[]'",
        "ALTER TABLE local_users ADD COLUMN last_login_at DATETIME",
        "ALTER TABLE local_users ADD COLUMN last_login_ip TEXT",
        "ALTER TABLE local_users ADD COLUMN totp_secret TEXT DEFAULT ''",
        "ALTER TABLE local_users ADD COLUMN totp_enabled INTEGER DEFAULT 0",
        "ALTER TABLE local_users ADD COLUMN totp_pending_secret TEXT DEFAULT ''"
    ],
    "media_requests": [
        "ALTER TABLE media_requests ADD COLUMN episodes TEXT DEFAULT ''",
        "ALTER TABLE media_requests ADD COLUMN request_type TEXT DEFAULT 'new'",
        "ALTER TABLE media_requests ADD COLUMN series_id TEXT DEFAULT ''"
    ],
    "media_feedback": [
        "ALTER TABLE media_feedback ADD COLUMN poster_path TEXT"
    ],
    "temp_accounts": [
        "ALTER TABLE temp_accounts ADD COLUMN allow_routes TEXT DEFAULT ''",
        "ALTER TABLE temp_accounts ADD COLUMN block_routes TEXT DEFAULT ''",
        "ALTER TABLE temp_accounts ADD COLUMN tags TEXT DEFAULT ''",
        "ALTER TABLE temp_accounts ADD COLUMN req_free INTEGER DEFAULT 0",
        "ALTER TABLE temp_accounts ADD COLUMN req_free_count INTEGER DEFAULT -1"
    ],
    "scratch_cards": [
        "ALTER TABLE scratch_cards ADD COLUMN chat_id TEXT DEFAULT ''",
        "ALTER TABLE scratch_cards ADD COLUMN message_id INTEGER DEFAULT 0"
    ],
    "point_red_packets": [
        "ALTER TABLE point_red_packets ADD COLUMN message_id TEXT"
    ],
    "pk_invitations": [
        "ALTER TABLE pk_invitations ADD COLUMN challenger_tg_name TEXT",
        "ALTER TABLE pk_invitations ADD COLUMN target_tg_name TEXT",
        "ALTER TABLE pk_invitations ADD COLUMN command_message_id TEXT"
    ],
    "PlaybackActivity": [
        "ALTER TABLE PlaybackActivity ADD COLUMN RemoteEndPoint TEXT",
        "ALTER TABLE PlaybackActivity ADD COLUMN Location TEXT",
        "ALTER TABLE PlaybackActivity ADD COLUMN ISP TEXT",
        "ALTER TABLE PlaybackActivity ADD COLUMN ClientName TEXT"
    ],
    "gap_perfect_series": [
        "ALTER TABLE gap_perfect_series ADD COLUMN tmdb_id TEXT"
    ],
    # 🔥 去重表增量更新（旧结构升级到新结构）
    "dedupe_results": [
        "ALTER TABLE dedupe_results ADD COLUMN group_key TEXT",
        "ALTER TABLE dedupe_results ADD COLUMN tmdb_id TEXT",
        "ALTER TABLE dedupe_results ADD COLUMN season_num INTEGER",
        "ALTER TABLE dedupe_results ADD COLUMN episode_num INTEGER",
        "ALTER TABLE dedupe_results ADD COLUMN file_name TEXT",
        "ALTER TABLE dedupe_results ADD COLUMN file_path TEXT",
        "ALTER TABLE dedupe_results ADD COLUMN resolution TEXT",
        "ALTER TABLE dedupe_results ADD COLUMN bitrate INTEGER",
        "ALTER TABLE dedupe_results ADD COLUMN size_bytes REAL",
        "ALTER TABLE dedupe_results ADD COLUMN video_codec TEXT",
        "ALTER TABLE dedupe_results ADD COLUMN audio_codec TEXT",
        "ALTER TABLE dedupe_results ADD COLUMN has_hdr INTEGER",
        "ALTER TABLE dedupe_results ADD COLUMN has_dovi INTEGER",
        "ALTER TABLE dedupe_results ADD COLUMN has_chi_sub INTEGER",
        "ALTER TABLE dedupe_results ADD COLUMN has_ass_sub INTEGER",
        "ALTER TABLE dedupe_results ADD COLUMN score INTEGER",
        "ALTER TABLE dedupe_results ADD COLUMN is_recommended_del INTEGER DEFAULT 0",
        "ALTER TABLE dedupe_results ADD COLUMN is_exempt INTEGER DEFAULT 0"
    ],
    "dedupe_whitelist": [
        "ALTER TABLE dedupe_whitelist ADD COLUMN title TEXT"
    ],
    # 🔥 保活违规表增量更新
    "keep_alive_violations": [
        "ALTER TABLE keep_alive_violations ADD COLUMN action TEXT DEFAULT 'warn'",
        "ALTER TABLE keep_alive_violations ADD COLUMN disabled INTEGER DEFAULT 0"
    ]
}

# 🔥 核心表定义 - 用于检测是否有数据
CORE_TABLES = ["users_meta"]  # 只要 users_meta 有数据就认为系统库已初始化

# 🔥 播放表的 CREATE 语句（用于初始化旧库路径）
PLAYBACK_SCHEMA = """CREATE TABLE IF NOT EXISTS PlaybackActivity (
    Id INTEGER PRIMARY KEY AUTOINCREMENT,
    UserId TEXT,
    UserName TEXT,
    ItemId TEXT,
    ItemName TEXT,
    PlayDuration INTEGER,
    DateCreated DATETIME DEFAULT CURRENT_TIMESTAMP,
    Client TEXT,
    DeviceName TEXT,
    RemoteEndPoint TEXT,
    Location TEXT,
    ISP TEXT
)"""
