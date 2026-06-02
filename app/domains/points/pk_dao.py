import datetime
import random

from app.infra.db.system_store import system_store


def list_expired_pending_pk_invites_with_messages():
    return system_store.fetch_all(
        """
        SELECT id, chat_id, message_id, challenger_tg_name, target_tg_name
        FROM pk_invitations
        WHERE expires_at < datetime('now', 'localtime')
          AND status = 'pending'
          AND message_id IS NOT NULL
        """
    )


def get_pending_pk_invitation(invite_id):
    return system_store.fetch_one(
        """
        SELECT id, challenger_id, challenger_name, challenger_tg_name, target_id, target_name, target_tg_name,
               chat_id, message_id, command_message_id
        FROM pk_invitations
        WHERE id = ? AND status = 'pending'
        """,
        (invite_id,),
    )


def set_pk_invitation_status(invite_id, status: str) -> None:
    system_store.execute("UPDATE pk_invitations SET status = ? WHERE id = ?", (status, invite_id))


def mark_pk_invitation_expired(invite_id) -> None:
    system_store.execute("UPDATE pk_invitations SET status = 'expired' WHERE id = ?", (invite_id,))


def get_latest_pending_pk_invitation_for_target(target_id: str):
    return system_store.fetch_one(
        """
        SELECT id, challenger_id, challenger_name, chat_id
        FROM pk_invitations
        WHERE target_id = ? AND status = 'pending'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (target_id,),
    )


def list_pending_pk_invitations_for_target(target_id: str):
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE pk_invitations SET status = 'expired' WHERE expires_at < datetime('now', 'localtime') AND status = 'pending'"
        )
        cursor.execute(
            """
            SELECT id, challenger_id, challenger_name, points, created_at, expires_at
            FROM pk_invitations
            WHERE target_id = ? AND status = 'pending'
            ORDER BY created_at DESC
            """,
            (target_id,),
        )
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        conn.commit()
        return rows


def reject_pending_pk_invitation(invite_id, target_id: str) -> dict:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        try:
            conn.execute("BEGIN IMMEDIATE")
            invite = cursor.execute(
                """
                SELECT id, challenger_name, target_id
                FROM pk_invitations
                WHERE id = ? AND status = 'pending'
                """,
                (invite_id,),
            ).fetchone()
            if not invite:
                conn.rollback()
                return {"status": "error", "message": "邀请不存在或已处理"}
            if invite[2] != target_id:
                conn.rollback()
                return {"status": "error", "message": "这不是发给你的PK邀请"}

            cursor.execute("UPDATE pk_invitations SET status = 'rejected' WHERE id = ?", (invite_id,))
            conn.commit()
            return {"status": "success", "challenger_name": invite[1]}
        except Exception:
            conn.rollback()
            raise


def clear_pk_invitations() -> int:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM pk_invitations")
        count = cursor.rowcount
        conn.commit()
        return count


def save_pk_invitation_message_id(invite_id, message_id) -> None:
    system_store.execute(
        "UPDATE pk_invitations SET message_id = ? WHERE id = ?",
        (str(message_id), invite_id),
    )


def create_pk_invitation(
    challenger_id: str,
    challenger_name: str,
    challenger_tg_name: str,
    target_id: str,
    target_name: str,
    target_tg_name: str,
    points: int,
    chat_id,
    command_message_id=None,
    expired_cleanup: str = "mark",
) -> dict:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        try:
            conn.execute("BEGIN IMMEDIATE")
            config = {row[0]: row[1] for row in cursor.execute("SELECT key, value FROM point_config").fetchall()}

            if int(config.get("enable_user_pk", 0)) == 0:
                conn.rollback()
                return {"status": "error", "code": "disabled", "message": "用户PK功能未开启"}

            min_points = int(config.get("user_pk_min_points", 10))
            max_points = int(config.get("user_pk_max_points", 500))
            if points < min_points or points > max_points:
                conn.rollback()
                return {
                    "status": "error",
                    "code": "range",
                    "message": f"下注积分需在 {min_points}-{max_points} 之间",
                    "min_points": min_points,
                    "max_points": max_points,
                }

            challenger_row = cursor.execute("SELECT points FROM users_meta WHERE user_id = ?", (challenger_id,)).fetchone()
            challenger_points = challenger_row[0] if challenger_row else 0
            if challenger_points < points:
                conn.rollback()
                return {
                    "status": "error",
                    "code": "challenger_balance",
                    "message": f"积分不足，当前积分：{challenger_points}",
                    "current_points": challenger_points,
                }

            target_row = cursor.execute("SELECT points FROM users_meta WHERE user_id = ?", (target_id,)).fetchone()
            target_points = target_row[0] if target_row else 0
            if target_points < points:
                conn.rollback()
                return {
                    "status": "error",
                    "code": "target_balance",
                    "message": f"对方积分不足（{target_points}），无法接受此PK",
                    "target_points": target_points,
                }

            today_pk_count = cursor.execute(
                """
                SELECT COUNT(*)
                FROM pk_logs
                WHERE challenger_id = ?
                  AND date(created_at, 'localtime') = date('now', 'localtime')
                """,
                (challenger_id,),
            ).fetchone()[0]
            max_per_day = int(config.get("user_pk_max_per_day", 5))
            if today_pk_count >= max_per_day:
                conn.rollback()
                return {
                    "status": "error",
                    "code": "daily_limit",
                    "message": f"今日PK次数已达上限（{max_per_day}次）",
                    "max_per_day": max_per_day,
                }

            if expired_cleanup == "delete":
                cursor.execute("DELETE FROM pk_invitations WHERE expires_at < datetime('now', 'localtime')")
            else:
                cursor.execute(
                    "UPDATE pk_invitations SET status = 'expired' WHERE expires_at < datetime('now', 'localtime') AND status = 'pending'"
                )
            pending = cursor.execute(
                """
                SELECT id
                FROM pk_invitations
                WHERE challenger_id = ? AND target_id = ? AND status = 'pending'
                """,
                (challenger_id, target_id),
            ).fetchone()
            if pending:
                conn.rollback()
                return {"status": "error", "code": "pending", "message": "已有待处理的PK邀请，请等待对方回应"}

            timeout_minutes = int(config.get("user_pk_timeout", 5))
            expires_at = datetime.datetime.now() + datetime.timedelta(minutes=timeout_minutes)
            cursor.execute(
                """
                INSERT INTO pk_invitations (
                    challenger_id, challenger_name, challenger_tg_name,
                    target_id, target_name, target_tg_name,
                    points, chat_id, command_message_id, created_at, expires_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'), ?, 'pending')
                """,
                (
                    challenger_id,
                    challenger_name,
                    challenger_tg_name,
                    target_id,
                    target_name,
                    target_tg_name,
                    points,
                    str(chat_id),
                    str(command_message_id) if command_message_id else None,
                    expires_at.isoformat(),
                ),
            )
            invite_id = cursor.lastrowid
            conn.commit()
            return {
                "status": "success",
                "invite_id": invite_id,
                "expires_at": expires_at.isoformat(),
                "timeout_minutes": timeout_minutes,
            }
        except Exception:
            conn.rollback()
            raise


def accept_pk_invitation(
    invite_id,
    target_id: str,
    challenger_roll: int = None,
    target_roll: int = None,
    cancel_on_insufficient: bool = False,
) -> dict:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        try:
            conn.execute("BEGIN IMMEDIATE")
            config = {row[0]: row[1] for row in cursor.execute("SELECT key, value FROM point_config").fetchall()}

            invite = cursor.execute(
                """
                SELECT id, challenger_id, challenger_name, challenger_tg_name, target_id, target_name, target_tg_name,
                       points, chat_id, message_id, command_message_id, expires_at
                FROM pk_invitations
                WHERE id = ? AND status = 'pending'
                """,
                (invite_id,),
            ).fetchone()
            if not invite:
                conn.rollback()
                return {"status": "error", "message": "邀请不存在或已过期"}

            (
                pk_invite_id,
                challenger_id,
                challenger_name,
                challenger_tg_name,
                invite_target_id,
                target_name,
                target_tg_name,
                points,
                chat_id,
                message_id,
                command_message_id,
                expires_at_value,
            ) = invite
            context = {
                "invite_id": pk_invite_id,
                "challenger_id": challenger_id,
                "challenger_name": challenger_name,
                "challenger_tg_name": challenger_tg_name,
                "target_id": invite_target_id,
                "target_name": target_name,
                "target_tg_name": target_tg_name,
                "points": points,
                "chat_id": chat_id,
                "message_id": message_id,
                "command_message_id": command_message_id,
            }

            if invite_target_id != target_id:
                conn.rollback()
                return {"status": "error", "message": "这不是发给你的PK邀请"}

            expires_at = datetime.datetime.fromisoformat(expires_at_value)
            if datetime.datetime.now() > expires_at:
                cursor.execute("UPDATE pk_invitations SET status = 'expired' WHERE id = ?", (invite_id,))
                conn.commit()
                return dict(context, status="error", message="PK邀请已过期")

            min_points = int(config.get("user_pk_min_points", 10))
            max_points = int(config.get("user_pk_max_points", 500))
            if points < min_points or points > max_points:
                cursor.execute("UPDATE pk_invitations SET status = 'cancelled' WHERE id = ?", (invite_id,))
                conn.commit()
                return dict(context, status="error", message=f"积分范围已变更，PK取消（需在 {min_points}-{max_points} 之间）")

            tax_rate = int(config.get("user_pk_tax", 5))
            challenger_points_row = cursor.execute("SELECT points FROM users_meta WHERE user_id = ?", (challenger_id,)).fetchone()
            challenger_points = challenger_points_row[0] if challenger_points_row else 0
            target_points_row = cursor.execute("SELECT points FROM users_meta WHERE user_id = ?", (invite_target_id,)).fetchone()
            target_points = target_points_row[0] if target_points_row else 0

            if challenger_points < points or target_points < points:
                if cancel_on_insufficient:
                    cursor.execute("UPDATE pk_invitations SET status = 'cancelled' WHERE id = ?", (invite_id,))
                    conn.commit()
                    return dict(context, status="error", message="双方积分不足，PK取消")
                conn.rollback()
                return dict(context, status="error", message="双方积分不足，PK取消")

            if challenger_roll is None:
                challenger_roll = random.randint(1, 100)
            if target_roll is None:
                target_roll = random.randint(1, 100)

            if challenger_roll > target_roll:
                winner_id = challenger_id
                winner_name = challenger_name
                loser_id = invite_target_id
                loser_name = target_name
            elif target_roll > challenger_roll:
                winner_id = invite_target_id
                winner_name = target_name
                loser_id = challenger_id
                loser_name = challenger_name
            else:
                cursor.execute("UPDATE pk_invitations SET status = 'completed' WHERE id = ?", (invite_id,))
                conn.commit()
                return dict(
                    context,
                    status="success",
                    message=f"平局！{challenger_name}({challenger_roll}点) vs {target_name}({target_roll}点)，积分退还",
                    challenger_roll=challenger_roll,
                    target_roll=target_roll,
                    tie=True,
                )

            win_amount = points
            tax = int(win_amount * tax_rate / 100)
            actual_win = win_amount - tax
            challenger_points_now = cursor.execute("SELECT points FROM users_meta WHERE user_id = ?", (challenger_id,)).fetchone()
            target_points_now = cursor.execute("SELECT points FROM users_meta WHERE user_id = ?", (invite_target_id,)).fetchone()
            challenger_balance = challenger_points_now[0] if challenger_points_now else 0
            target_balance = target_points_now[0] if target_points_now else 0

            loser_balance = challenger_balance if loser_id == challenger_id else target_balance
            if loser_balance < points:
                cursor.execute("UPDATE pk_invitations SET status = 'cancelled' WHERE id = ?", (invite_id,))
                conn.commit()
                return dict(context, status="error", message=f"积分不足，PK取消（输家积分：{loser_balance}，需要：{points}）")

            cursor.execute("UPDATE users_meta SET points = points + ? WHERE user_id = ?", (actual_win, winner_id))
            cursor.execute("UPDATE users_meta SET points = points - ? WHERE user_id = ?", (points, loser_id))
            cursor.execute(
                "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, (SELECT points FROM users_meta WHERE user_id = ?))",
                (winner_id, winner_name, f"PK战胜 {loser_name}", actual_win, winner_id),
            )
            cursor.execute(
                "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, (SELECT points FROM users_meta WHERE user_id = ?))",
                (loser_id, loser_name, f"PK败给 {winner_name}", -points, loser_id),
            )
            cursor.execute(
                "INSERT INTO pk_logs (challenger_id, challenger_name, target_id, target_name, points, challenger_roll, target_roll, winner_id, winner_name, tax) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (challenger_id, challenger_name, invite_target_id, target_name, points, challenger_roll, target_roll, winner_id, winner_name, tax),
            )
            cursor.execute("UPDATE pk_invitations SET status = 'completed' WHERE id = ?", (invite_id,))
            conn.commit()
            return dict(
                context,
                status="success",
                message=f"🎉 {winner_name}({max(challenger_roll, target_roll)}点) 战胜 {loser_name}({min(challenger_roll, target_roll)}点)，获得 {actual_win} 积分（扣{tax_rate}%手续费）",
                challenger_roll=challenger_roll,
                target_roll=target_roll,
                winner_name=winner_name,
                win_amount=actual_win,
                tax=tax,
                tax_rate=tax_rate,
            )
        except Exception:
            conn.rollback()
            raise
