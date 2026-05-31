from app.infra.db.system_store import system_store


def create_user_audit_log(
    admin_id: str,
    admin_name: str,
    action: str,
    target_user_id: str = None,
    target_user_name: str = None,
    target_count: int = 0,
    details: str = "",
    ip_address: str = "",
    created_at: str = "",
) -> None:
    system_store.execute(
        """
        INSERT INTO user_audit_logs
        (admin_id, admin_name, action, target_user_id, target_user_name,
         target_count, details, ip_address, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            admin_id,
            admin_name,
            action,
            target_user_id,
            target_user_name,
            target_count,
            details,
            ip_address,
            created_at,
        ),
    )


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
