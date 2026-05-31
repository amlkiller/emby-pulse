from app.infra.db.system_store import system_store


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


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


def list_user_audit_logs(
    page: int = 1,
    limit: int = 20,
    action: str = None,
    start_date: str = None,
    end_date: str = None,
    target_user_id: str = None,
) -> dict:
    conditions = []
    params = []

    if action:
        conditions.append("action LIKE ? ESCAPE '\\'")
        params.append(f"%{_escape_like(action)}%")
    if start_date:
        conditions.append("created_at >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("created_at <= ?")
        params.append(end_date + "T23:59:59")
    if target_user_id:
        conditions.append("target_user_id LIKE ? ESCAPE '\\'")
        params.append(f"%{_escape_like(target_user_id)}%")

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    with system_store.connect() as conn:
        count_sql = f"SELECT COUNT(*) as count FROM user_audit_logs {where_clause}"
        count_res = conn.execute(count_sql, params).fetchone()
        total_count = count_res["count"] if count_res else 0

        offset = (page - 1) * limit
        data_sql = f"SELECT * FROM user_audit_logs {where_clause} ORDER BY id DESC LIMIT ? OFFSET ?"
        logs = conn.execute(data_sql, params + [limit, offset]).fetchall()

    result = []
    for log in logs:
        result.append(
            {
                "id": log["id"],
                "admin_id": log["admin_id"],
                "admin_name": log["admin_name"],
                "action": log["action"],
                "target_user_id": log["target_user_id"] or "",
                "target_user_name": log["target_user_name"] or "",
                "target_count": log["target_count"] or 0,
                "details": log["details"] or "",
                "ip_address": log["ip_address"] or "",
                "created_at": log["created_at"],
            }
        )

    return {
        "logs": result,
        "total_count": total_count,
        "total_pages": max(1, (total_count + limit - 1) // limit),
        "page": page,
    }


def get_user_audit_stats(start_date: str) -> dict:
    with system_store.connect() as conn:
        action_stats = conn.execute(
            "SELECT action, COUNT(*) as count FROM user_audit_logs WHERE created_at >= ? GROUP BY action ORDER BY count DESC",
            [start_date],
        ).fetchall()
        admin_stats = conn.execute(
            "SELECT admin_name, COUNT(*) as count FROM user_audit_logs WHERE created_at >= ? GROUP BY admin_id ORDER BY count DESC LIMIT 10",
            [start_date],
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) as count FROM user_audit_logs WHERE created_at >= ?",
            [start_date],
        ).fetchone()

    return {
        "action_stats": [{"action": row["action"], "count": row["count"]} for row in action_stats],
        "admin_stats": [{"admin_name": row["admin_name"], "count": row["count"]} for row in admin_stats],
        "total_count": total["count"] if total else 0,
    }


def delete_user_audit_log(log_id: int) -> None:
    system_store.execute("DELETE FROM user_audit_logs WHERE id = ?", [log_id])


def clear_user_audit_logs_before(cutoff_date: str) -> int:
    return system_store.execute("DELETE FROM user_audit_logs WHERE created_at < ?", [cutoff_date])
