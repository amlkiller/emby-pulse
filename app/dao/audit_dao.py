from app.infra.db.system_store import system_store


def list_user_audit_logs_since(start_datetime: str, limit: int):
    return system_store.fetch_all(
        """
        SELECT * FROM user_audit_logs
        WHERE datetime(created_at) >= datetime(?, 'localtime')
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (start_datetime, limit),
    )
