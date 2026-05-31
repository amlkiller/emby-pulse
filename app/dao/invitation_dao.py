import datetime

from app.infra.db.row import to_data_row
from app.infra.db.system_store import system_store


def get_invitation_by_code(code: str):
    return system_store.fetch_one("SELECT * FROM invitations WHERE code = ?", (code,))


def get_available_registration_invitation(code: str):
    return system_store.fetch_one(
        """
        SELECT days, used_count, max_uses, template_user_id, routes, route_mode
        FROM invitations
        WHERE code = ? AND status = 0 AND (type = 'register' OR type IS NULL)
        """,
        (code,),
    )


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


def claim_invitation_usage(code: str, used_by: str) -> bool:
    with system_store.connect() as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                """
                UPDATE invitations
                SET used_count = used_count + 1,
                    used_at = datetime('now','localtime'),
                    used_by = ?
                WHERE code = ? AND status != 1 AND used_count < max_uses
                """,
                (used_by, code),
            )
            if cursor.rowcount == 0:
                conn.rollback()
                return False
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise


def save_code_registration_meta_and_finish_invitation(
    code: str,
    user_id: str,
    expire_date,
    allow_routes: str,
    block_routes: str,
) -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO users_meta
            (user_id, expire_date, allow_routes, block_routes, created_at)
            VALUES (?, ?, ?, ?, datetime('now','localtime'))
            """,
            (user_id, expire_date, allow_routes, block_routes),
        )
        cursor.execute("UPDATE invitations SET status = 1 WHERE code = ? AND used_count >= max_uses", (code,))
        conn.commit()


def renew_user_with_invitation_code(code: str, used_by: str, user_id: str):
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
                AND type = 'renew'
                """,
                (used_by, code),
            )
            if cursor.rowcount == 0:
                conn.rollback()
                return None, "invalid"

            row = cursor.execute("SELECT days FROM invitations WHERE code = ?", (code,)).fetchone()
            days = row[0]

            exp_row = cursor.execute("SELECT expire_date FROM users_meta WHERE user_id = ?", (user_id,)).fetchone()
            current_exp = exp_row[0] if exp_row and exp_row[0] else ""

            if current_exp and ("2099" in current_exp or "3000" in current_exp or "永久" in current_exp):
                conn.rollback()
                return None, "permanent"

            if days == -1 or days == 0 or days >= 36500:
                new_exp = "2099-12-31"
            else:
                today = datetime.date.today()
                try:
                    exp_date = datetime.datetime.strptime(current_exp, "%Y-%m-%d").date() if current_exp else today
                    if exp_date < today:
                        exp_date = today
                except Exception:
                    exp_date = today
                new_exp = (exp_date + datetime.timedelta(days=days)).strftime("%Y-%m-%d")

            cursor.execute("UPDATE users_meta SET expire_date = ? WHERE user_id = ?", (new_exp, user_id))
            cursor.execute("UPDATE invitations SET status = 1 WHERE code = ? AND used_count >= max_uses", (code,))
            conn.commit()
            return {"days": days, "new_exp": new_exp}, None
        except Exception:
            conn.rollback()
            raise


def create_invitation_codes(
    codes,
    days,
    created_at: str,
    template_user_id,
    code_type: str,
    routes: str,
    route_mode: str,
    req_free,
    req_free_count,
) -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.executemany(
            """
            INSERT INTO invitations
            (code, days, created_at, template_user_id, type, routes, route_mode, req_free, req_free_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (code, days, created_at, template_user_id, code_type, routes, route_mode, req_free, req_free_count)
                for code in codes
            ],
        )
        conn.commit()


def list_admin_invitations(code_type: str = "all"):
    if code_type in ("register", "renew"):
        return system_store.fetch_all("SELECT * FROM invitations WHERE type = ? ORDER BY created_at DESC", (code_type,))
    return system_store.fetch_all("SELECT * FROM invitations ORDER BY created_at DESC")


def list_invitation_usage_stats():
    return system_store.fetch_all("SELECT type, used_count, used_by FROM invitations")


def list_invitation_export_rows(code_type: str = "all"):
    fields = "code, type, days, used_count, max_uses, used_by, status, created_at, used_at, req_free, req_free_count"
    if code_type in ("register", "renew"):
        return system_store.fetch_all(f"SELECT {fields} FROM invitations WHERE type = ? ORDER BY created_at DESC", (code_type,))
    return system_store.fetch_all(f"SELECT {fields} FROM invitations ORDER BY created_at DESC")


def delete_invitation_codes(codes) -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.executemany("DELETE FROM invitations WHERE code = ?", [(code,) for code in codes])
        conn.commit()


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
