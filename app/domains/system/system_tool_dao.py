import os
import random
import string
import time
import json
import sqlite3

from app.core.security_utils import safe_error_message
from app.infra.db.schema_registry import SYSTEM_TABLES
from app.infra.db.system_store import system_store


def check_system_table_integrity():
    if not os.path.exists(system_store.db_path):
        return {"ok": False, "msg": "系统数据库不存在"}

    try:
        with system_store.connect(timeout=3) as conn:
            cursor = conn.cursor()
            existing_tables = []
            missing_tables = []

            for table in SYSTEM_TABLES.copy():
                try:
                    cursor.execute(f"SELECT 1 FROM {table} LIMIT 1")
                    existing_tables.append(table)
                except Exception:
                    missing_tables.append(table)

        if len(missing_tables) == 0:
            return {"ok": True, "msg": f"完整 ({len(existing_tables)} 表)"}
        return {
            "ok": False,
            "msg": f"缺 {len(missing_tables)} 表: {', '.join(missing_tables[:3])}{'...' if len(missing_tables) > 3 else ''}",
        }
    except Exception as exc:
        return {"ok": False, "msg": safe_error_message(exc)[:50]}


def check_system_db_readwrite():
    try:
        test_key = f"_health_check_{''.join(random.choices(string.ascii_lowercase, k=8))}"
        test_value = f"test_{int(time.time())}"

        with system_store.connect(timeout=3) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO point_config (key, value) VALUES (?, ?)", (test_key, test_value))
            conn.commit()
            cursor.execute("SELECT value FROM point_config WHERE key = ?", (test_key,))
            result = cursor.fetchone()
            cursor.execute("DELETE FROM point_config WHERE key = ?", (test_key,))
            conn.commit()

        if result and result[0] == test_value:
            return {"ok": True, "msg": "读写正常"}
        return {"ok": False, "msg": "数据验证失败"}
    except Exception as exc:
        return {"ok": False, "msg": safe_error_message(exc)[:50]}


def system_database_exists() -> bool:
    return os.path.exists(system_store.db_path)


def repair_core_system_tables():
    results = []
    with system_store.connect() as conn:
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT 1 FROM PlaybackActivity LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS PlaybackActivity (
                    Id INTEGER PRIMARY KEY AUTOINCREMENT,
                    UserId TEXT,
                    UserName TEXT,
                    ItemId TEXT,
                    ItemName TEXT,
                    PlayDuration INTEGER,
                    DateCreated DATETIME DEFAULT CURRENT_TIMESTAMP,
                    Client TEXT,
                    DeviceName TEXT
                )"""
            )
            results.append("已修复: 播放活动主表")

        try:
            cursor.execute("SELECT 1 FROM users_meta LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS users_meta (
                    user_id TEXT PRIMARY KEY,
                    expire_date TEXT,
                    note TEXT,
                    created_at TEXT
                )"""
            )
            results.append("已修复: 用户元数据表")

        try:
            cursor.execute("SELECT 1 FROM invitations LIMIT 1")
            try:
                cursor.execute("SELECT template_user_id FROM invitations LIMIT 1")
            except sqlite3.OperationalError:
                cursor.execute("ALTER TABLE invitations ADD COLUMN template_user_id TEXT")
                results.append("已升级: 邀请码模板字段")
        except sqlite3.OperationalError:
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS invitations (
                    code TEXT PRIMARY KEY,
                    days INTEGER,
                    used_count INTEGER DEFAULT 0,
                    max_uses INTEGER DEFAULT 1,
                    created_at TEXT,
                    used_at DATETIME,
                    used_by TEXT,
                    status INTEGER DEFAULT 0,
                    template_user_id TEXT
                )"""
            )
            results.append("已修复: 邀请码表")

        try:
            cursor.execute("SELECT 1 FROM tv_calendar_cache LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS tv_calendar_cache (
                    id TEXT PRIMARY KEY,
                    series_id TEXT,
                    season INTEGER,
                    episode INTEGER,
                    air_date TEXT,
                    status TEXT,
                    data_json TEXT
                )"""
            )
            results.append("已修复: 追剧日历缓存表")

        try:
            cursor.execute("SELECT 1 FROM media_requests LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS media_requests (
                    tmdb_id INTEGER,
                    media_type TEXT,
                    title TEXT,
                    year TEXT,
                    poster_path TEXT,
                    status INTEGER DEFAULT 0,
                    season INTEGER DEFAULT 0,
                    reject_reason TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (tmdb_id, season)
                )"""
            )
            results.append("已修复: 求片主表")

        try:
            cursor.execute("SELECT 1 FROM request_users LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS request_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tmdb_id INTEGER,
                    user_id TEXT,
                    username TEXT,
                    season INTEGER DEFAULT 0,
                    requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(tmdb_id, user_id, season)
                )"""
            )
            results.append("已修复: 求片关联表")

        try:
            cursor.execute("SELECT 1 FROM insight_ignores LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS insight_ignores (
                    item_id TEXT PRIMARY KEY,
                    item_name TEXT,
                    ignored_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            results.append("已修复: 盘点忽略表")

        try:
            cursor.execute("SELECT 1 FROM gap_records LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS gap_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    series_id TEXT,
                    series_name TEXT,
                    season_number INTEGER,
                    episode_number INTEGER,
                    status INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(series_id, season_number, episode_number)
                )"""
            )
            results.append("已修复: 缺集记录表")

        conn.commit()
    return results


def get_dashboard_layout():
    with system_store.connect() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS sys_dashboard (id INTEGER PRIMARY KEY DEFAULT 1, layout_json TEXT)")
        row = conn.execute("SELECT layout_json FROM sys_dashboard WHERE id = 1").fetchone()
        if row and row[0]:
            return json.loads(row[0])
    return None


def save_dashboard_layout(data) -> None:
    with system_store.connect() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS sys_dashboard (id INTEGER PRIMARY KEY DEFAULT 1, layout_json TEXT)")
        conn.execute(
            "INSERT OR REPLACE INTO sys_dashboard (id, layout_json) VALUES (1, ?)",
            (json.dumps(data, ensure_ascii=False),),
        )
        conn.commit()
