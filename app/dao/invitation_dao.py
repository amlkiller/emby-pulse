from app.infra.db.row import to_data_row
from app.infra.db.system_store import system_store


def get_invitation_by_code(code: str):
    return system_store.fetch_one("SELECT * FROM invitations WHERE code = ?", (code,))


def restore_invitation_code_usage(code: str) -> None:
    system_store.execute(
        """
        UPDATE invitations
        SET used_count = MAX(used_count - 1, 0),
            used_by = NULL,
            used_at = NULL
        WHERE code = ?
        """,
        (code,),
    )


def claim_registration_invitation(code: str, used_by: str):
    with system_store.connect() as conn:
        cursor = conn.cursor()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor.execute(
                """
                UPDATE invitations
                SET used_count = used_count + 1,
                    used_at = datetime('now','localtime'),
                    used_by = ?
                WHERE code = ? AND status != 1 AND used_count < max_uses
                AND (type IS NULL OR type = 'register')
                """,
                (used_by, code),
            )
            if cursor.rowcount == 0:
                conn.rollback()
                cursor.execute("SELECT 1 FROM invitations WHERE code = ?", (code,))
                exists = cursor.fetchone()
                if not exists:
                    return None, "邀请码无效"
                return None, "邀请码已失效或已达到使用上限"

            cursor.execute("SELECT * FROM invitations WHERE code = ?", (code,))
            invite = to_data_row(cursor.fetchone())

            used_count = invite["used_count"] if invite["used_count"] else 0
            max_uses = invite["max_uses"] if invite["max_uses"] else 1
            if used_count >= max_uses:
                cursor.execute("UPDATE invitations SET status = 1 WHERE code = ?", (code,))
            conn.commit()
            return invite, None
        except Exception:
            conn.rollback()
            raise


def save_registered_user_meta(
    user_id: str,
    expire_date,
    allow_routes: str,
    block_routes: str,
    req_free,
    req_free_count,
) -> None:
    system_store.execute(
        """
        INSERT OR REPLACE INTO users_meta
        (user_id, expire_date, allow_routes, block_routes, req_free, req_free_count, created_at)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now','localtime'))
        """,
        (user_id, expire_date, allow_routes, block_routes, req_free, req_free_count),
    )
