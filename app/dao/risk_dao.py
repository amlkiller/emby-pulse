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
