import json
import time
from datetime import datetime

from app.infra.db.schema_bootstrap import ensure_registered_table
from app.infra.db.system_store import system_store

AUDIT_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_audit_user_id ON audit_logs(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action)",
)


def ensure_audit_table() -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        ensure_registered_table(cursor, "audit_logs")
        for index_sql in AUDIT_INDEX_SQL:
            cursor.execute(index_sql)
        conn.commit()


def insert_audit_log(
    action: str,
    user_id=None,
    user_name=None,
    resource_type=None,
    resource_id=None,
    ip_address=None,
    user_agent=None,
    details=None,
    status: str = "success",
) -> None:
    now = time.time()
    datetime_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    details_json = json.dumps(details, ensure_ascii=False) if details else None
    system_store.execute(
        """
        INSERT INTO audit_logs
        (timestamp, datetime, user_id, user_name, action, resource_type, resource_id, ip_address, user_agent, details, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (now, datetime_str, user_id, user_name, action, resource_type, resource_id, ip_address, user_agent, details_json, status),
    )


def list_audit_logs(user_id=None, action=None, start_time=None, end_time=None, limit: int = 100, offset: int = 0):
    where_clauses = []
    params = []
    if user_id:
        where_clauses.append("user_id = ?")
        params.append(user_id)
    if action:
        where_clauses.append("action = ?")
        params.append(action)
    if start_time:
        where_clauses.append("timestamp >= ?")
        params.append(start_time)
    if end_time:
        where_clauses.append("timestamp <= ?")
        params.append(end_time)

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    rows = system_store.fetch_all(
        f"""
        SELECT * FROM audit_logs
        WHERE {where_sql}
        ORDER BY timestamp DESC
        LIMIT ? OFFSET ?
        """,
        tuple(params + [limit, offset]),
    )
    return [dict(row) for row in rows]


def get_audit_stats_since(start_time: float):
    with system_store.connect() as conn:
        action_stats = conn.execute(
            "SELECT action, COUNT(*) as count FROM audit_logs WHERE timestamp >= ? GROUP BY action ORDER BY count DESC",
            (start_time,),
        ).fetchall()
        user_stats = conn.execute(
            "SELECT user_name, COUNT(*) as count FROM audit_logs WHERE timestamp >= ? AND user_name IS NOT NULL GROUP BY user_name ORDER BY count DESC LIMIT 10",
            (start_time,),
        ).fetchall()
        failed_stats = conn.execute(
            "SELECT action, COUNT(*) as count FROM audit_logs WHERE timestamp >= ? AND status = 'failed' GROUP BY action ORDER BY count DESC",
            (start_time,),
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) as count FROM audit_logs WHERE timestamp >= ?",
            (start_time,),
        ).fetchone()

    return {
        "total": total["count"] if total else 0,
        "by_action": [{"action": row["action"], "count": row["count"]} for row in action_stats],
        "by_user": [{"user": row["user_name"], "count": row["count"]} for row in user_stats],
        "failed": [{"action": row["action"], "count": row["count"]} for row in failed_stats],
    }


def cleanup_audit_logs_before(cutoff_time: float) -> int:
    return system_store.execute("DELETE FROM audit_logs WHERE timestamp < ?", (cutoff_time,))
