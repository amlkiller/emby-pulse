# -*- coding: utf-8 -*-
"""
Login attempt limiter to prevent brute force attacks
"""

import time
import sqlite3
from app.core.config import SYSTEM_DB_PATH


def init_login_attempts_table():
    """Initialize login attempts tracking table"""
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS login_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ip_address TEXT NOT NULL,
        username TEXT,
        attempt_time REAL NOT NULL,
        success INTEGER DEFAULT 0
    )
    """)
    try:
        c.execute("CREATE INDEX IF NOT EXISTS idx_login_attempts_ip ON login_attempts(ip_address)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_login_attempts_time ON login_attempts(attempt_time)")
    except:
        pass
    conn.commit()
    conn.close()


def record_login_attempt(ip_address: str, username: str, success: bool):
    """Record a login attempt"""
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO login_attempts (ip_address, username, attempt_time, success) VALUES (?, ?, ?, ?)",
        (ip_address, username, time.time(), 1 if success else 0)
    )
    conn.commit()
    conn.close()


def get_failed_attempts(ip_address: str, window_seconds: int = 300) -> int:
    """
    Get number of failed attempts from an IP in the given time window
    
    Args:
        ip_address: Client IP address
        window_seconds: Time window in seconds (default 5 minutes)
    
    Returns:
        Number of failed attempts
    """
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    cutoff_time = time.time() - window_seconds
    c.execute(
        "SELECT COUNT(*) FROM login_attempts WHERE ip_address = ? AND attempt_time > ? AND success = 0",
        (ip_address, cutoff_time)
    )
    count = c.fetchone()[0]
    conn.close()
    return count


def is_login_blocked(ip_address: str, max_attempts: int = 5, window_seconds: int = 300) -> tuple:
    """
    Check if login is blocked for an IP
    
    Args:
        ip_address: Client IP address
        max_attempts: Maximum allowed failed attempts (default 5)
        window_seconds: Time window in seconds (default 5 minutes)
    
    Returns:
        (is_blocked: bool, remaining_attempts: int, wait_seconds: int)
    """
    init_login_attempts_table()
    
    failed_count = get_failed_attempts(ip_address, window_seconds)
    
    if failed_count >= max_attempts:
        # Calculate wait time
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        cutoff_time = time.time() - window_seconds
        c.execute(
            "SELECT MIN(attempt_time) FROM login_attempts WHERE ip_address = ? AND attempt_time > ? AND success = 0",
            (ip_address, cutoff_time)
        )
        oldest_attempt = c.fetchone()[0]
        conn.close()
        
        wait_seconds = int(oldest_attempt + window_seconds - time.time()) if oldest_attempt else 0
        return True, 0, max(0, wait_seconds)
    
    return False, max_attempts - failed_count, 0


def clear_login_attempts(ip_address: str):
    """Clear login attempts for an IP (after successful login)"""
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM login_attempts WHERE ip_address = ?", (ip_address,))
    conn.commit()
    conn.close()


def cleanup_old_attempts():
    """Clean up old login attempts (older than 1 hour)"""
    conn = sqlite3.connect(SYSTEM_DB_PATH)
    c = conn.cursor()
    cutoff_time = time.time() - 3600
    c.execute("DELETE FROM login_attempts WHERE attempt_time < ?", (cutoff_time,))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return deleted
