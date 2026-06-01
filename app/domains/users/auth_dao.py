import sqlite3
from typing import Optional

from app.infra.db.schema_registry import TABLE_ALTERS, TABLE_SCHEMAS
from app.infra.db.system_store import system_store


_LOCAL_USER_UPDATE_FIELDS = {"remark", "is_enabled", "role", "permissions"}


def get_login_failure(lock_key: str):
    return system_store.fetch_one(
        """
        SELECT locked_until, failure_count
        FROM login_failures
        WHERE lock_key = ?
        """,
        (lock_key,),
    )


def get_login_failure_count(lock_key: str) -> Optional[int]:
    row = system_store.fetch_one("SELECT failure_count FROM login_failures WHERE lock_key = ?", (lock_key,))
    return row["failure_count"] if row else None


def upsert_login_failure(lock_key: str, lock_type: str, failure_count: int, locked_until) -> None:
    system_store.execute(
        """
        INSERT INTO login_failures (lock_key, lock_type, failure_count, locked_until, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(lock_key) DO UPDATE SET
            failure_count = excluded.failure_count,
            locked_until = excluded.locked_until,
            updated_at = CURRENT_TIMESTAMP
        """,
        (lock_key, lock_type, failure_count, locked_until),
    )


def clear_login_failure(lock_key: str) -> None:
    system_store.execute("DELETE FROM login_failures WHERE lock_key = ?", (lock_key,))


def cleanup_expired_login_locks() -> int:
    return system_store.execute("DELETE FROM login_failures WHERE locked_until IS NOT NULL AND locked_until < CURRENT_TIMESTAMP")


def _apply_table_alters(cursor, table_name: str) -> None:
    for alter_sql in TABLE_ALTERS.get(table_name, []):
        try:
            cursor.execute(alter_sql)
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise


def ensure_local_users_table() -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute(TABLE_SCHEMAS["local_users"])
        _apply_table_alters(cursor, "local_users")
        conn.commit()


def get_local_user_id_by_username(username: str):
    return system_store.fetch_one("SELECT id FROM local_users WHERE username = ?", (username,))


def upsert_env_local_admin(username: str, password_hash: str, updated_at: str) -> bool:
    existing = get_local_user_id_by_username(username)
    if existing:
        system_store.execute(
            "UPDATE local_users SET password_hash = ?, role = 'admin', is_enabled = 1, updated_at = ? WHERE username = ?",
            (password_hash, updated_at, username),
        )
        return False
    system_store.execute(
        "INSERT INTO local_users (username, password_hash, role, is_enabled, remark, permissions) VALUES (?, ?, 'admin', 1, '环境变量创建的管理员', '[]')",
        (username, password_hash),
    )
    return True


def count_enabled_local_users(role: Optional[str] = None) -> int:
    if role:
        row = system_store.fetch_one("SELECT COUNT(*) as cnt FROM local_users WHERE is_enabled = 1 AND role = ?", (role,))
    else:
        row = system_store.fetch_one("SELECT COUNT(*) as cnt FROM local_users WHERE is_enabled = 1")
    return row["cnt"] if row else 0


def list_local_users():
    return system_store.fetch_all(
        "SELECT id, username, role, remark, avatar, is_enabled, permissions, created_at, updated_at, last_login_at, last_login_ip FROM local_users ORDER BY created_at DESC"
    )


def create_local_user(username: str, password_hash: str, role: str, remark: str, permissions_json: str) -> None:
    system_store.execute(
        "INSERT INTO local_users (username, password_hash, role, remark, permissions) VALUES (?, ?, ?, ?, ?)",
        (username, password_hash, role, remark, permissions_json),
    )


def get_local_user_by_id(user_id: int, fields: str = "*"):
    return system_store.fetch_one(f"SELECT {fields} FROM local_users WHERE id = ?", (user_id,))


def update_local_user_fields(user_id: int, updates: dict, updated_at: str) -> None:
    invalid_fields = set(updates) - _LOCAL_USER_UPDATE_FIELDS
    if invalid_fields:
        raise ValueError(f"Unsupported local_users update fields: {', '.join(sorted(invalid_fields))}")

    values = dict(updates)
    values["updated_at"] = updated_at
    assignments = ", ".join([f"{field} = ?" for field in values.keys()])
    params = list(values.values()) + [user_id]
    system_store.execute(f"UPDATE local_users SET {assignments} WHERE id = ?", params)


def update_local_user_password(user_id: int, password_hash: str, updated_at: str) -> None:
    system_store.execute(
        "UPDATE local_users SET password_hash = ?, updated_at = ? WHERE id = ?",
        (password_hash, updated_at, user_id),
    )


def count_enabled_admin_users() -> int:
    return count_enabled_local_users("admin")


def delete_local_user(user_id: int) -> None:
    system_store.execute("DELETE FROM local_users WHERE id = ?", (user_id,))


def update_local_user_avatar(user_id: int, avatar: str, updated_at: str) -> None:
    system_store.execute(
        "UPDATE local_users SET avatar = ?, updated_at = ? WHERE id = ?",
        (avatar, updated_at, user_id),
    )


def update_local_user_permissions(user_id: int, permissions_json: str, updated_at: str) -> None:
    system_store.execute(
        "UPDATE local_users SET permissions = ?, updated_at = ? WHERE id = ?",
        (permissions_json, updated_at, user_id),
    )


def get_local_user_for_login(username: str):
    return system_store.fetch_one(
        "SELECT id, username, password_hash, role, remark, avatar, is_enabled, permissions, totp_secret, totp_enabled FROM local_users WHERE username = ?",
        (username,),
    )


def update_local_user_login(user_id: int, last_login_at: str, last_login_ip: str) -> None:
    system_store.execute(
        "UPDATE local_users SET last_login_at = ?, last_login_ip = ? WHERE id = ?",
        (last_login_at, last_login_ip, user_id),
    )


def get_local_user_totp_enabled(user_id: int):
    return system_store.fetch_one("SELECT totp_enabled FROM local_users WHERE id = ?", (user_id,))


def set_local_user_totp_pending_secret(user_id: int, secret: str) -> None:
    system_store.execute("UPDATE local_users SET totp_pending_secret = ? WHERE id = ?", (secret, user_id))


def get_local_user_totp_setup_secret(user_id: int):
    return system_store.fetch_one("SELECT totp_pending_secret, totp_secret FROM local_users WHERE id = ?", (user_id,))


def get_local_user_totp_pending_secret(user_id: int):
    return system_store.fetch_one("SELECT totp_pending_secret FROM local_users WHERE id = ?", (user_id,))


def enable_local_user_totp(user_id: int, secret: str) -> None:
    system_store.execute(
        "UPDATE local_users SET totp_secret = ?, totp_enabled = 1, totp_pending_secret = '' WHERE id = ?",
        (secret, user_id),
    )


def get_local_user_totp_secret(user_id: int):
    return system_store.fetch_one("SELECT totp_secret FROM local_users WHERE id = ?", (user_id,))


def disable_local_user_totp(user_id: int) -> None:
    system_store.execute(
        "UPDATE local_users SET totp_secret = '', totp_pending_secret = '', totp_enabled = 0 WHERE id = ?",
        (user_id,),
    )
