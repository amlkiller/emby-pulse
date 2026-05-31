from app.infra.db.system_store import system_store


def list_risk_logs(limit: int = 200):
    return system_store.fetch_all(
        "SELECT * FROM risk_logs ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )


def count_recent_risk_actions():
    return system_store.fetch_all(
        """
        SELECT action, COUNT(*) as cnt
        FROM risk_logs
        WHERE datetime(created_at) >= datetime('now', '-1 day')
        GROUP BY action
        """
    )


def list_top_risk_offenders(limit: int = 5):
    return system_store.fetch_all(
        """
        SELECT username, COUNT(*) as total_violations
        FROM risk_logs
        GROUP BY username
        ORDER BY total_violations DESC
        LIMIT ?
        """,
        (limit,),
    )


def count_vip_users() -> int:
    row = system_store.fetch_one("SELECT COUNT(*) as vip_count FROM users_meta WHERE is_vip = 1")
    return row["vip_count"] if row else 0


def set_user_admin_disabled(user_id: str, disabled: bool, created_at: str = "") -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        if disabled:
            cursor.execute(
                "INSERT OR IGNORE INTO users_meta (user_id, created_at) VALUES (?, ?)",
                (user_id, created_at),
            )
        cursor.execute(
            "UPDATE users_meta SET admin_disabled = ? WHERE user_id = ?",
            (1 if disabled else 0, user_id),
        )
        conn.commit()


def create_risk_log(user_id: str, username: str, action: str, reason: str) -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO risk_logs (user_id, username, action, reason) VALUES (?, ?, ?, ?)",
            (user_id, username, action, reason),
        )
        if action == "ban":
            cursor.execute("UPDATE users_meta SET risk_level = 'banned' WHERE user_id = ?", (user_id,))
        conn.commit()


def get_user_concurrent_policy(user_id: str):
    return system_store.fetch_one(
        "SELECT max_concurrent, is_vip FROM users_meta WHERE user_id = ?",
        (user_id,),
    )


def get_tg_user_id_for_emby_user(user_id: str):
    row = system_store.fetch_one(
        "SELECT tg_user_id FROM tg_user_bindings WHERE emby_user_id = ?",
        (user_id,),
    )
    return row["tg_user_id"] if row else None
