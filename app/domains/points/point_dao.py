import json
import datetime
import random

from app.infra.db.schema_bootstrap import ensure_registered_table
from app.infra.db.system_store import system_store
from app.domains.points.scratch_card_dao import (
    buy_scratch_card,
    complete_scratch_card,
    create_scratch_card,
    get_active_scratch_card,
    get_scratch_card,
    get_scratch_card_origin,
    get_scratch_card_slot,
    get_scratch_card_slots,
    has_user_scratched_card,
    reveal_scratch_reward,
    save_scratch_card_message_id,
    update_scratch_card_slot,
)


_POINT_GAME_TABLES = (
    "lottery_tickets",
    "lottery_results",
    "lottery_winners",
    "scratch_cards",
    "scratch_card_slots",
    "point_checkin_streak",
    "point_red_packets",
    "point_red_packet_logs",
    "point_transfer_logs",
    "point_rob_logs",
    "pk_invitations",
    "pk_logs",
)


def get_point_config() -> dict:
    try:
        rows = system_store.fetch_all("SELECT key, value FROM point_config")
        return {row["key"]: row["value"] for row in rows}
    except Exception:
        return {}


def ensure_lottery_table() -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        for table_name in ("lottery_tickets", "lottery_results", "lottery_winners"):
            ensure_registered_table(cursor, table_name)
        conn.commit()


def ensure_points_schema() -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        ensure_registered_table(cursor, "users_meta", {"points"})
        ensure_registered_table(cursor, "point_logs")
        ensure_registered_table(cursor, "point_config")
        for table_name in _POINT_GAME_TABLES:
            ensure_registered_table(cursor, table_name)

        cursor.execute("SELECT count(*) FROM point_config")
        if cursor.fetchone()[0] == 0:
            default_store = [
                {
                    "id": "renew_30",
                    "type": "renew",
                    "name": "账号续期 30 天",
                    "cost": 500,
                    "val": 30,
                    "icon": "fa-battery-half",
                    "color": "text-emerald-500",
                    "desc": "延长一个月欢乐时光",
                    "max_buys": 0,
                },
                {
                    "id": "invite_code",
                    "type": "manual",
                    "name": "购买一枚邀请码",
                    "cost": 2000,
                    "icon": "fa-ticket",
                    "color": "text-amber-500",
                    "desc": "兑换后请凭截图联系服主发放",
                    "max_buys": 0,
                },
            ]
            defaults = [
                ("enable_points", "1"),
                ("checkin_min", "10"),
                ("checkin_max", "30"),
                ("enable_req_cost", "0"),
                ("req_cost", "50"),
                ("store_items", json.dumps(default_store, ensure_ascii=False)),
                ("enable_streak_bonus", "1"),
                ("streak_7_days", "100"),
                ("streak_30_days", "500"),
                ("streak_reset_on_miss", "1"),
                ("enable_transfer", "1"),
                ("transfer_fee_rate", "10"),
                ("transfer_min", "10"),
                ("transfer_max", "1000"),
                ("enable_red_packet", "1"),
                ("red_packet_admin_only", "1"),
                ("red_packet_expire_hours", "24"),
                ("enable_bot_checkin", "1"),
                ("enable_bot_transfer", "1"),
                ("enable_bot_red_packet", "1"),
                ("enable_bot_rank", "1"),
                ("enable_rob", "1"),
                ("rob_success_rate", "50"),
                ("rob_min", "1"),
                ("rob_max", "10"),
                ("rob_counter_rate", "30"),
                ("rob_counter_min", "1"),
                ("rob_counter_max", "5"),
                ("rob_protect_threshold", "50"),
                ("rob_max_per_day", "5"),
                ("rob_max_be_robbed", "3"),
                ("rob_cooldown_hours", "2"),
                ("enable_user_pk", "1"),
                ("user_pk_min_points", "10"),
                ("user_pk_max_points", "500"),
                ("user_pk_max_per_day", "5"),
                ("user_pk_timeout", "5"),
                ("user_pk_tax", "5"),
            ]
            cursor.executemany("INSERT INTO point_config (key, value) VALUES (?, ?)", defaults)

        conn.commit()


def save_point_config_values(configs: dict) -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        for key, value in configs.items():
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            cursor.execute("INSERT OR REPLACE INTO point_config (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()


def list_user_points():
    return system_store.fetch_all("SELECT user_id, points FROM users_meta")


def get_user_points_balance(user_id: str) -> int:
    row = system_store.fetch_one("SELECT points FROM users_meta WHERE user_id = ?", (user_id,))
    return row["points"] if row and row["points"] else 0


def batch_update_user_points(user_ids, amount: int, reason: str, name_map: dict) -> int:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        conn.execute("BEGIN IMMEDIATE")
        count = 0
        for user_id in user_ids:
            cursor.execute("SELECT points FROM users_meta WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            new_points = max(0, (row[0] or 0) + amount) if row else max(0, amount)
            if row:
                cursor.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_points, user_id))
            else:
                cursor.execute("INSERT INTO users_meta (user_id, points) VALUES (?, ?)", (user_id, new_points))
            cursor.execute(
                "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                (user_id, name_map.get(user_id, "未知用户"), f"管理员操作: {reason}", amount, new_points),
            )
            count += 1
        conn.commit()
        return count


def list_point_logs(user_id: str = None, page: int = 1, page_size: int = 50, action_type: str = None) -> dict:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        conditions = []
        params = []

        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)

        if action_type and action_type != "all":
            conditions.append("action LIKE ?")
            params.append(f"%{action_type}%")

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        count_sql = f"SELECT COUNT(*) FROM point_logs {where_clause}"
        total = cursor.execute(count_sql, params).fetchone()[0]

        offset = (page - 1) * page_size
        data_sql = f"""
            SELECT id, user_id, username, action, amount, balance,
                   datetime(created_at, 'localtime') as created_at
            FROM point_logs
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        cursor.execute(data_sql, params + [page_size, offset])
        columns = [desc[0] for desc in cursor.description]
        logs = [dict(zip(columns, row)) for row in cursor.fetchall()]

        for log in logs:
            if not log.get("username"):
                try:
                    user_row = cursor.execute(
                        "SELECT name FROM users_meta WHERE user_id = ?",
                        (log.get("user_id"),),
                    ).fetchone()
                    log["username"] = user_row[0] if user_row else "未知用户"
                except Exception:
                    log["username"] = "未知用户"

        return {"logs": logs, "total": total}


def get_user_points_info(user_id: str) -> dict:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        row = cursor.execute(
            "SELECT points, req_free, req_free_count FROM users_meta WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        points = row[0] if row else 0
        req_free = row[1] if row and len(row) > 1 else 0
        req_free_count = row[2] if row and len(row) > 2 else -1
        has_checked_in = bool(
            cursor.execute(
                "SELECT 1 FROM point_logs WHERE user_id = ? AND action LIKE '每日签到%' AND date(created_at, 'localtime') = date('now', 'localtime')",
                (user_id,),
            ).fetchone()
        )
        config = {row[0]: row[1] for row in cursor.execute("SELECT key, value FROM point_config").fetchall()}

    try:
        store_items = json.loads(config.get("store_items", "[]"))
    except Exception:
        store_items = []
    config["store_items"] = store_items

    return {
        "points": points,
        "has_checked_in": has_checked_in,
        "config": config,
        "req_free": req_free,
        "req_free_count": req_free_count,
    }


def list_user_point_logs(user_id: str, page: int = 1, page_size: int = 20) -> dict:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        total = cursor.execute("SELECT COUNT(*) FROM point_logs WHERE user_id = ?", (user_id,)).fetchone()[0]

        offset = (page - 1) * page_size
        cursor.execute(
            """
            SELECT action, amount, balance, datetime(created_at, 'localtime') as created_at
            FROM point_logs
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, page_size, offset),
        )
        columns = [desc[0] for desc in cursor.description]
        logs = [dict(zip(columns, row)) for row in cursor.fetchall()]

    return {"logs": logs, "total": total}


def list_red_packet_logs(packet_id: int) -> list[dict]:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT user_name, amount, datetime(created_at, 'localtime') as created_at
            FROM point_red_packet_logs
            WHERE packet_id = ?
            ORDER BY created_at
            """,
            (packet_id,),
        )
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def list_point_rank(limit: int = 10):
    return system_store.fetch_all(
        "SELECT user_id, points FROM users_meta WHERE points > 0 ORDER BY points DESC LIMIT ?",
        (limit,),
    )


def get_lottery_winning_numbers(draw_date: str):
    return system_store.fetch_one("SELECT winning_numbers FROM lottery_results WHERE draw_date = ?", (draw_date,))


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


def save_red_packet_message_id(packet_id: int, message_id) -> None:
    system_store.execute(
        "UPDATE point_red_packets SET message_id = ? WHERE id = ?",
        (str(message_id), packet_id),
    )


def transfer_points(
    from_user_id: str,
    from_user_name: str,
    to_user_id: str,
    to_user_name: str,
    amount: int,
    target_exists=None,
) -> dict:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        try:
            conn.execute("BEGIN IMMEDIATE")
            config = {row[0]: row[1] for row in cursor.execute("SELECT key, value FROM point_config").fetchall()}

            if int(config.get("enable_transfer", 0)) == 0:
                conn.rollback()
                return {"status": "error", "message": "积分转赠功能未开启"}

            min_amount = int(config.get("transfer_min", 10))
            max_amount = int(config.get("transfer_max", 1000))
            if amount < min_amount or amount > max_amount:
                conn.rollback()
                return {"status": "error", "message": f"转赠金额需在 {min_amount}-{max_amount} 之间"}

            if to_user_id == from_user_id:
                conn.rollback()
                return {"status": "error", "message": "不能转赠给自己"}

            to_user_row = cursor.execute("SELECT user_id FROM users_meta WHERE user_id = ?", (to_user_id,)).fetchone()
            if not to_user_row:
                if target_exists is None:
                    conn.rollback()
                    return {"status": "error", "message": "无法验证目标用户"}
                if not target_exists:
                    conn.rollback()
                    return {"status": "error", "message": "目标用户不存在"}

            from_row = cursor.execute("SELECT points FROM users_meta WHERE user_id = ?", (from_user_id,)).fetchone()
            from_points = from_row[0] if from_row else 0

            if from_points < amount:
                conn.rollback()
                return {"status": "error", "message": f"积分不足！当前积分: {from_points}"}

            fee_rate = int(config.get("transfer_fee_rate", 10))
            fee = int(amount * fee_rate / 100)
            actual_amount = amount - fee

            to_row = cursor.execute("SELECT points FROM users_meta WHERE user_id = ?", (to_user_id,)).fetchone()
            to_points = (to_row[0] or 0) + actual_amount if to_row else actual_amount

            new_from_points = from_points - amount
            if to_row:
                cursor.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (to_points, to_user_id))
            else:
                cursor.execute("INSERT INTO users_meta (user_id, points) VALUES (?, ?)", (to_user_id, to_points))

            if from_row:
                cursor.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_from_points, from_user_id))
            else:
                cursor.execute("INSERT INTO users_meta (user_id, points) VALUES (?, ?)", (from_user_id, new_from_points))

            to_user_name = to_user_name or "未知用户"
            cursor.execute(
                "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                (from_user_id, from_user_name, f"转赠给 {to_user_name} (手续费{fee})", -amount, new_from_points),
            )
            cursor.execute(
                "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                (to_user_id, to_user_name, f"收到 {from_user_name} 转赠", actual_amount, to_points),
            )
            cursor.execute(
                "INSERT INTO point_transfer_logs (from_user_id, from_user_name, to_user_id, to_user_name, amount, fee) VALUES (?, ?, ?, ?, ?, ?)",
                (from_user_id, from_user_name, to_user_id, to_user_name, amount, fee),
            )

            conn.commit()
            return {
                "status": "success",
                "message": f"转赠成功！已转赠 {actual_amount} 积分给 {to_user_name}（手续费 {fee}）",
                "actual_amount": actual_amount,
                "fee": fee,
                "balance": new_from_points,
            }
        except Exception:
            conn.rollback()
            raise


def redeem_store_item(user_id: str, user_name: str, item_id: str) -> dict:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        try:
            conn.execute("BEGIN IMMEDIATE")
            config = {row[0]: row[1] for row in cursor.execute("SELECT key, value FROM point_config").fetchall()}
            try:
                store_items = json.loads(config.get("store_items", "[]"))
            except Exception:
                store_items = []

            target_item = next((x for x in store_items if x.get("id") == item_id), None)
            if not target_item:
                conn.rollback()
                return {"status": "error", "message": "商品不存在或已下架"}

            item_name = target_item.get("name", "未知商品")
            item_type = target_item.get("type", "")

            max_buys = int(target_item.get("max_buys", 0))
            if max_buys > 0:
                buy_count_row = cursor.execute(
                    "SELECT COUNT(*) FROM point_logs WHERE user_id = ? AND action LIKE ?",
                    (user_id, f"商城兑换: {item_name}%"),
                ).fetchone()
                buy_count = buy_count_row[0] if buy_count_row else 0
                if buy_count >= max_buys:
                    conn.rollback()
                    return {"status": "error", "message": f"该商品限购 {max_buys} 次，您已购买 {buy_count} 次"}

            cost = int(target_item.get("cost", 0))
            user_row = cursor.execute(
                "SELECT points, expire_date, admin_disabled FROM users_meta WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            current_points = user_row[0] if user_row else 0
            current_exp = user_row[1] if user_row and len(user_row) > 1 else None
            admin_disabled = user_row[2] if user_row and len(user_row) > 2 else 0

            if current_points < cost:
                conn.rollback()
                return {"status": "error", "message": f"余额不足！需要 {cost} 积分。"}

            is_permanent = not current_exp or current_exp == "" or "2099" in current_exp or "3000" in current_exp or "永久" in current_exp
            if item_type in ["renew", "random_renew"] and is_permanent:
                conn.rollback()
                return {"status": "error", "message": "您的账号当前为【永久有效】，无需兑换续期！"}

            new_points = current_points - cost
            cursor.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_points, user_id))

            new_exp_str = ""
            actual_days = 0
            random_bonus = 0
            base_days = 0
            random_min = 0
            random_max = 0

            if item_type == "renew":
                days = int(target_item.get("val", 30))
                today = datetime.date.today()
                try:
                    exp_date = datetime.datetime.strptime(current_exp, "%Y-%m-%d").date()
                    if exp_date < today:
                        exp_date = today
                except Exception:
                    exp_date = today

                new_exp_date = exp_date + datetime.timedelta(days=days)
                new_exp_str = new_exp_date.strftime("%Y-%m-%d")
                cursor.execute("UPDATE users_meta SET expire_date = ? WHERE user_id = ?", (new_exp_str, user_id))
                action_desc = f"商城兑换: {item_name} (至 {new_exp_str})"

            elif item_type == "random_renew":
                base_days = int(target_item.get("base_days", 30))
                random_min = int(target_item.get("random_min", -10))
                random_max = int(target_item.get("random_max", 60))
                luck_mode = target_item.get("luck_mode", "normal")
                luck_value = int(target_item.get("luck_value", 50))

                if luck_mode == "lucky":
                    times = max(1, int(luck_value / 25))
                    random_bonus = max(random.randint(random_min, random_max) for _ in range(times))
                elif luck_mode == "unlucky":
                    times = max(1, int(luck_value / 25))
                    random_bonus = min(random.randint(random_min, random_max) for _ in range(times))
                else:
                    random_bonus = random.randint(random_min, random_max)

                actual_days = max(1, base_days + random_bonus)
                today = datetime.date.today()
                try:
                    exp_date = datetime.datetime.strptime(current_exp, "%Y-%m-%d").date()
                    if exp_date < today:
                        exp_date = today
                except Exception:
                    exp_date = today

                new_exp_date = exp_date + datetime.timedelta(days=actual_days)
                new_exp_str = new_exp_date.strftime("%Y-%m-%d")
                cursor.execute("UPDATE users_meta SET expire_date = ? WHERE user_id = ?", (new_exp_str, user_id))
                bonus_text = f"+{random_bonus}" if random_bonus >= 0 else str(random_bonus)
                action_desc = f"🎲商城兑换: {item_name} (基础{base_days}天{bonus_text}={actual_days}天，至{new_exp_str})"
            else:
                action_desc = f"商城兑换: {item_name}"

            cursor.execute(
                "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                (user_id, user_name, action_desc, -cost, new_points),
            )
            conn.commit()
            return {
                "status": "success",
                "item_name": item_name,
                "item_type": item_type,
                "cost": cost,
                "balance": new_points,
                "new_exp_str": new_exp_str,
                "actual_days": actual_days,
                "random_bonus": random_bonus,
                "base_days": base_days,
                "random_min": random_min,
                "random_max": random_max,
                "admin_disabled": admin_disabled,
                "message": f"兑换成功！{item_name}已生效。",
            }
        except Exception:
            conn.rollback()
            raise


def rob_points(from_user_id: str, from_user_name: str, to_user_id: str, to_user_name: str) -> dict:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        try:
            conn.execute("BEGIN IMMEDIATE")
            config = {row[0]: row[1] for row in cursor.execute("SELECT key, value FROM point_config").fetchall()}

            if int(config.get("enable_rob", 0)) == 0:
                conn.rollback()
                return {"status": "error", "message": "打劫功能未开启"}

            if to_user_id == from_user_id:
                conn.rollback()
                return {"status": "error", "message": "不能打劫自己"}

            success_rate = int(config.get("rob_success_rate", 50))
            rob_min = int(config.get("rob_min", 1))
            rob_max = int(config.get("rob_max", 10))
            counter_rate = int(config.get("rob_counter_rate", 30))
            counter_min = int(config.get("rob_counter_min", 1))
            counter_max = int(config.get("rob_counter_max", 5))
            protect_threshold = int(config.get("rob_protect_threshold", 50))
            max_per_day = int(config.get("rob_max_per_day", 5))
            max_be_robbed = int(config.get("rob_max_be_robbed", 3))
            cooldown_hours = int(config.get("rob_cooldown_hours", 2))

            from_row = cursor.execute("SELECT points FROM users_meta WHERE user_id = ?", (from_user_id,)).fetchone()
            from_points = from_row[0] if from_row else 0
            if from_points < protect_threshold:
                conn.rollback()
                return {"status": "error", "message": f"你的积分低于 {protect_threshold}，无法打劫他人"}

            to_row = cursor.execute("SELECT points FROM users_meta WHERE user_id = ?", (to_user_id,)).fetchone()
            to_points = to_row[0] if to_row else 0
            if to_points < protect_threshold:
                conn.rollback()
                return {"status": "error", "message": f"对方积分低于 {protect_threshold}，处于保护状态"}

            today_rob_count = cursor.execute(
                "SELECT COUNT(*) FROM point_rob_logs WHERE from_user_id = ? AND date(created_at, 'localtime') = date('now', 'localtime')",
                (from_user_id,),
            ).fetchone()[0]
            if today_rob_count >= max_per_day:
                conn.rollback()
                return {"status": "error", "message": f"今日打劫次数已达上限（{max_per_day}次）"}

            today_be_robbed_count = cursor.execute(
                "SELECT COUNT(*) FROM point_rob_logs WHERE to_user_id = ? AND date(created_at, 'localtime') = date('now', 'localtime')",
                (to_user_id,),
            ).fetchone()[0]
            if today_be_robbed_count >= max_be_robbed:
                conn.rollback()
                return {"status": "error", "message": f"对方今日已被打劫 {max_be_robbed} 次，休息一下吧"}

            last_rob = cursor.execute(
                "SELECT created_at FROM point_rob_logs WHERE from_user_id = ? AND to_user_id = ? ORDER BY created_at DESC LIMIT 1",
                (from_user_id, to_user_id),
            ).fetchone()
            if last_rob:
                try:
                    last_time = datetime.datetime.fromisoformat(str(last_rob[0]).replace("Z", "+00:00"))
                    cooldown_end = last_time + datetime.timedelta(hours=cooldown_hours)
                    now_time = datetime.datetime.now(last_time.tzinfo)
                    if now_time < cooldown_end:
                        remaining = int((cooldown_end - now_time).total_seconds() / 60)
                        conn.rollback()
                        return {"status": "error", "message": f"冷却中，还需等待 {remaining} 分钟"}
                except Exception:
                    pass

            rob_amount = random.randint(rob_min, rob_max)
            is_success = random.randint(1, 100) <= success_rate

            if is_success:
                actual_amount = min(rob_amount, to_points)
                new_from_points = from_points + actual_amount
                new_to_points = to_points - actual_amount

                if from_row:
                    cursor.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_from_points, from_user_id))
                else:
                    cursor.execute("INSERT INTO users_meta (user_id, points) VALUES (?, ?)", (from_user_id, new_from_points))

                if to_row:
                    cursor.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_to_points, to_user_id))
                else:
                    cursor.execute("INSERT INTO users_meta (user_id, points) VALUES (?, ?)", (to_user_id, new_to_points))

                cursor.execute(
                    "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                    (from_user_id, from_user_name, f"打劫 {to_user_name}", actual_amount, new_from_points),
                )
                cursor.execute(
                    "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                    (to_user_id, to_user_name, f"被 {from_user_name} 打劫", -actual_amount, new_to_points),
                )
                cursor.execute(
                    "INSERT INTO point_rob_logs (from_user_id, from_user_name, to_user_id, to_user_name, amount, success, counter_amount) VALUES (?, ?, ?, ?, ?, 1, 0)",
                    (from_user_id, from_user_name, to_user_id, to_user_name, actual_amount),
                )

                conn.commit()
                return {
                    "status": "success",
                    "message": f"🎉 打劫成功！从 {to_user_name} 身上抢到 {actual_amount} 积分",
                    "success": True,
                    "amount": actual_amount,
                    "balance": new_from_points,
                }

            counter_amount = random.randint(counter_min, counter_max)
            actual_counter = min(counter_amount, from_points)
            new_from_points = from_points - actual_counter
            new_to_points = to_points + actual_counter

            if from_row:
                cursor.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_from_points, from_user_id))
            else:
                cursor.execute("INSERT INTO users_meta (user_id, points) VALUES (?, ?)", (from_user_id, new_from_points))

            if to_row:
                cursor.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_to_points, to_user_id))
            else:
                cursor.execute("INSERT INTO users_meta (user_id, points) VALUES (?, ?)", (to_user_id, new_to_points))

            cursor.execute(
                "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                (from_user_id, from_user_name, f"打劫 {to_user_name} 失败", -actual_counter, new_from_points),
            )
            cursor.execute(
                "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                (to_user_id, to_user_name, f"反杀 {from_user_name}", actual_counter, new_to_points),
            )
            cursor.execute(
                "INSERT INTO point_rob_logs (from_user_id, from_user_name, to_user_id, to_user_name, amount, success, counter_amount) VALUES (?, ?, ?, ?, ?, 0, ?)",
                (from_user_id, from_user_name, to_user_id, to_user_name, 0, actual_counter),
            )

            conn.commit()
            return {
                "status": "success",
                "message": f"😢 打劫失败！被 {to_user_name} 反杀，损失 {actual_counter} 积分",
                "success": False,
                "counter_amount": actual_counter,
                "balance": new_from_points,
            }
        except Exception:
            conn.rollback()
            raise


def create_red_packet(total_amount: int, total_count: int, chat_id, creator_id: str, creator_name: str) -> dict:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        try:
            conn.execute("BEGIN IMMEDIATE")
            config = {row[0]: row[1] for row in cursor.execute("SELECT key, value FROM point_config").fetchall()}

            if int(config.get("enable_red_packet", 0)) == 0:
                conn.rollback()
                return {"status": "error", "message": "积分红包功能未开启"}

            if total_count < 1 or total_count > 100:
                conn.rollback()
                return {"status": "error", "message": "红包数量需在 1-100 之间"}

            row = cursor.execute("SELECT points FROM users_meta WHERE user_id = ?", (creator_id,)).fetchone()
            current_points = row[0] if row else 0
            if current_points < total_amount:
                conn.rollback()
                return {"status": "error", "message": f"积分不足！当前积分: {current_points}"}

            expire_hours = int(config.get("red_packet_expire_hours", 24))
            expires_at = datetime.datetime.now() + datetime.timedelta(hours=expire_hours)
            new_points = current_points - total_amount
            cursor.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_points, creator_id))

            cursor.execute(
                """
                INSERT INTO point_red_packets
                (total_amount, remain_amount, total_count, remain_count, creator_id, creator_name, chat_id, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (total_amount, total_amount, total_count, total_count, creator_id, creator_name, chat_id, expires_at),
            )
            packet_id = cursor.lastrowid

            cursor.execute(
                "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                (creator_id, creator_name, f"发放红包 #{packet_id}", -total_amount, new_points),
            )
            conn.commit()
            return {
                "status": "success",
                "message": f"红包创建成功！共 {total_count} 个红包，总计 {total_amount} 积分",
                "packet_id": packet_id,
                "balance": new_points,
            }
        except Exception:
            conn.rollback()
            raise


def grab_red_packet(packet_id: int, user_id: str, user_name: str, allow_creator: bool = True) -> dict:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("BEGIN EXCLUSIVE")
            packet_row = cursor.execute(
                """
                SELECT id, total_amount, remain_amount, total_count, remain_count, creator_id, creator_name, expires_at
                FROM point_red_packets
                WHERE id = ?
                """,
                (packet_id,),
            ).fetchone()
            if not packet_row:
                conn.rollback()
                return {"status": "error", "message": "红包不存在"}

            (
                packet_id,
                total_amount,
                remain_amount,
                total_count,
                remain_count,
                creator_id,
                creator_name,
                expires_at,
            ) = packet_row

            if not allow_creator and creator_id == user_id:
                conn.rollback()
                return {"status": "error", "message": "不能抢自己发的红包"}

            if expires_at and datetime.datetime.fromisoformat(str(expires_at)) < datetime.datetime.now():
                conn.rollback()
                return {"status": "error", "message": "红包已过期"}

            if remain_count <= 0 or remain_amount <= 0:
                conn.rollback()
                return {"status": "error", "message": "红包已抢完"}

            if cursor.execute(
                "SELECT 1 FROM point_red_packet_logs WHERE packet_id = ? AND user_id = ?",
                (packet_id, user_id),
            ).fetchone():
                conn.rollback()
                return {"status": "error", "message": "您已抢过该红包"}

            if remain_count == 1:
                grab_amount = remain_amount
            else:
                max_grab = remain_amount // remain_count * 2
                grab_amount = random.randint(1, min(max_grab, remain_amount - remain_count + 1))

            new_remain_amount = remain_amount - grab_amount
            new_remain_count = remain_count - 1
            cursor.execute(
                "UPDATE point_red_packets SET remain_amount = ?, remain_count = ? WHERE id = ?",
                (new_remain_amount, new_remain_count, packet_id),
            )

            row = cursor.execute("SELECT points FROM users_meta WHERE user_id = ?", (user_id,)).fetchone()
            new_points = (row[0] or 0) + grab_amount if row else grab_amount
            if row:
                cursor.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_points, user_id))
            else:
                cursor.execute("INSERT INTO users_meta (user_id, points) VALUES (?, ?)", (user_id, new_points))

            cursor.execute(
                "INSERT INTO point_red_packet_logs (packet_id, user_id, user_name, amount) VALUES (?, ?, ?, ?)",
                (packet_id, user_id, user_name, grab_amount),
            )
            cursor.execute(
                "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                (user_id, user_name, f"抢红包 #{packet_id} (来自{creator_name})", grab_amount, new_points),
            )

            is_last_one = new_remain_count == 0
            grab_logs = []
            chat_id = None
            message_id = None
            if is_last_one:
                grab_logs = [
                    {"user_name": row[0], "amount": row[1]}
                    for row in cursor.execute(
                        "SELECT user_name, amount FROM point_red_packet_logs WHERE packet_id = ? ORDER BY created_at",
                        (packet_id,),
                    ).fetchall()
                ]
                chat_row = cursor.execute("SELECT chat_id, message_id FROM point_red_packets WHERE id = ?", (packet_id,)).fetchone()
                chat_id = chat_row[0] if chat_row else None
                message_id = chat_row[1] if chat_row and len(chat_row) > 1 else None

            conn.commit()
            return {
                "status": "success",
                "message": f"恭喜！抢到 {grab_amount} 积分",
                "amount": grab_amount,
                "balance": new_points,
                "creator_name": creator_name,
                "is_last_one": is_last_one,
                "total_amount": total_amount,
                "total_count": total_count,
                "grab_logs": grab_logs,
                "chat_id": chat_id,
                "message_id": message_id,
            }
        except Exception:
            conn.rollback()
            raise


def count_today_point_logs(user_id: str, action: str = None, action_like: str = None) -> int:
    conditions = ["user_id = ?", "date(created_at, 'localtime') = date('now', 'localtime')"]
    params = [user_id]
    if action is not None:
        conditions.append("action = ?")
        params.append(action)
    if action_like is not None:
        conditions.append("action LIKE ?")
        params.append(action_like)

    row = system_store.fetch_one(
        f"SELECT COUNT(*) AS count FROM point_logs WHERE {' AND '.join(conditions)}",
        tuple(params),
    )
    return row["count"] if row else 0


def apply_game_point_change(
    user_id: str,
    username: str,
    action: str,
    amount: int,
    require_min_points: int = None,
    log_amount: int = None,
) -> dict:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = cursor.execute("SELECT points FROM users_meta WHERE user_id = ?", (user_id,)).fetchone()
            current_points = row[0] if row else 0
            if require_min_points is not None and current_points < require_min_points:
                conn.rollback()
                return {"status": "error", "message": f"积分不足（需要 {require_min_points} 积分）", "points": current_points}

            new_points = current_points + amount
            if row:
                cursor.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_points, user_id))
            else:
                cursor.execute("INSERT INTO users_meta (user_id, points) VALUES (?, ?)", (user_id, new_points))

            cursor.execute(
                "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                (user_id, username, action, amount if log_amount is None else log_amount, new_points),
            )
            conn.commit()
            return {"status": "success", "points": new_points}
        except Exception:
            conn.rollback()
            raise


def insert_point_log(user_id: str, username: str, action: str, amount: int, balance: int) -> None:
    system_store.execute(
        "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
        (user_id, username, action, amount, balance),
    )


def list_lottery_ticket_numbers(user_id: str, draw_date: str) -> list:
    rows = system_store.fetch_all(
        "SELECT numbers FROM lottery_tickets WHERE user_id = ? AND draw_date = ?",
        (user_id, draw_date),
    )
    return [row["numbers"] for row in rows]


def list_user_lottery_tickets(user_id: str, days: int = 7) -> list:
    days = max(int(days), 1)
    return system_store.fetch_all(
        f"""
        SELECT numbers, cost, draw_date, created_at
        FROM lottery_tickets
        WHERE user_id = ? AND draw_date >= date('now', '-{days} days')
        ORDER BY draw_date DESC, created_at DESC
        """,
        (user_id,),
    )


def get_latest_lottery_result():
    return system_store.fetch_one(
        """
        SELECT draw_date, winning_numbers, total_pool
        FROM lottery_results
        WHERE winning_numbers != ''
        ORDER BY draw_date DESC
        LIMIT 1
        """
    )


def list_lottery_winners_for_date(draw_date: str) -> list:
    return system_store.fetch_all(
        """
        SELECT user_id, username, prize_level, prize_amount
        FROM lottery_winners
        WHERE draw_date = ?
        ORDER BY prize_level
        """,
        (draw_date,),
    )


def get_lottery_draw_context(draw_date: str) -> dict:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        result = cursor.execute("SELECT winning_numbers FROM lottery_results WHERE draw_date = ?", (draw_date,)).fetchone()
        pool_row = cursor.execute("SELECT total_pool FROM lottery_results WHERE draw_date = ?", (draw_date,)).fetchone()
        tickets = cursor.execute(
            "SELECT id, user_id, username, numbers FROM lottery_tickets WHERE draw_date = ?",
            (draw_date,),
        ).fetchall()
        return {
            "already_drawn": bool(result and result[0]),
            "winning_numbers": result[0] if result and result[0] else "",
            "total_pool": pool_row[0] if pool_row else 0,
            "tickets": [
                {"id": row[0], "user_id": row[1], "username": row[2], "numbers": row[3]}
                for row in tickets
            ],
        }


def save_lottery_draw_result(draw_date: str, winning_numbers: str, winners_by_level: dict, lucky_winners: list, remaining_pool: int) -> dict:
    tomorrow = (datetime.datetime.strptime(draw_date, "%Y-%m-%d") + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    with system_store.connect() as conn:
        cursor = conn.cursor()
        try:
            conn.execute("BEGIN IMMEDIATE")
            result = cursor.execute("SELECT winning_numbers, total_pool FROM lottery_results WHERE draw_date = ?", (draw_date,)).fetchone()
            if result and result[0]:
                conn.rollback()
                return {"status": "skipped", "winning_numbers": result[0], "total_pool": result[1] or 0}

            total_pool = result[1] if result else 0
            level_names = {1: "一等奖", 2: "二等奖", 3: "三等奖", 4: "安慰奖"}

            for level, winner_list in winners_by_level.items():
                for winner in winner_list:
                    user_id = winner["user_id"]
                    username = winner["username"]
                    prize_amount = winner["prize_amount"]
                    ticket_id = winner["ticket_id"]
                    row = cursor.execute("SELECT points FROM users_meta WHERE user_id = ?", (user_id,)).fetchone()
                    current_points = (row[0] or 0) + prize_amount if row else prize_amount
                    if row:
                        cursor.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (current_points, user_id))
                    else:
                        cursor.execute("INSERT INTO users_meta (user_id, points) VALUES (?, ?)", (user_id, current_points))
                    cursor.execute(
                        "INSERT INTO lottery_winners (user_id, username, ticket_id, prize_level, prize_amount, draw_date) VALUES (?, ?, ?, ?, ?, ?)",
                        (user_id, username, ticket_id, level, prize_amount, draw_date),
                    )
                    cursor.execute(
                        "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                        (user_id, username, f"彩票{level_names[level]}", prize_amount, current_points),
                    )

            for winner in lucky_winners:
                user_id = winner["user_id"]
                username = winner["username"]
                prize_amount = winner["prize_amount"]
                ticket_id = winner["ticket_id"]
                row = cursor.execute("SELECT points FROM users_meta WHERE user_id = ?", (user_id,)).fetchone()
                current_points = (row[0] or 0) + prize_amount if row else prize_amount
                if row:
                    cursor.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (current_points, user_id))
                else:
                    cursor.execute("INSERT INTO users_meta (user_id, points) VALUES (?, ?)", (user_id, current_points))
                cursor.execute(
                    "INSERT INTO lottery_winners (user_id, username, ticket_id, prize_level, prize_amount, draw_date) VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, username, ticket_id, 5, prize_amount, draw_date),
                )
                cursor.execute(
                    "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                    (user_id, username, "彩票幸运奖", prize_amount, current_points),
                )

            cursor.execute("UPDATE lottery_results SET winning_numbers = ? WHERE draw_date = ?", (winning_numbers, draw_date))
            if remaining_pool > 0:
                cursor.execute(
                    "INSERT OR IGNORE INTO lottery_results (draw_date, winning_numbers, total_pool) VALUES (?, '', 0)",
                    (tomorrow,),
                )
                cursor.execute(
                    "UPDATE lottery_results SET total_pool = total_pool + ? WHERE draw_date = ?",
                    (remaining_pool, tomorrow),
                )

            conn.commit()
            return {"status": "success", "winning_numbers": winning_numbers, "total_pool": total_pool}
        except Exception:
            conn.rollback()
            raise


def buy_lottery_tickets(user_id: str, username: str, count: int, cost: int, max_per_day: int, draw_date: str, tickets: list) -> dict:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        try:
            conn.execute("BEGIN IMMEDIATE")
            ticket_count = len(tickets)
            today_count = cursor.execute(
                "SELECT COUNT(*) FROM lottery_tickets WHERE user_id = ? AND draw_date = ?",
                (user_id, draw_date),
            ).fetchone()[0]
            if today_count + ticket_count > max_per_day:
                conn.rollback()
                return {"status": "error", "message": f"今日最多购买 {max_per_day} 张"}

            row = cursor.execute("SELECT points FROM users_meta WHERE user_id = ?", (user_id,)).fetchone()
            current_points = row[0] if row else 0
            total_cost = cost * ticket_count
            if current_points < total_cost:
                conn.rollback()
                return {"status": "error", "message": "积分不足"}

            new_points = current_points - total_cost
            if row:
                cursor.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_points, user_id))
            else:
                cursor.execute("INSERT INTO users_meta (user_id, points) VALUES (?, ?)", (user_id, new_points))

            created_at = datetime.datetime.now().isoformat()
            for ticket_number in tickets:
                cursor.execute(
                    "INSERT INTO lottery_tickets (user_id, username, numbers, cost, draw_date, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, username, ticket_number, cost, draw_date, created_at),
                )

            cursor.execute(
                "INSERT OR IGNORE INTO lottery_results (draw_date, winning_numbers, total_pool) VALUES (?, '', 0)",
                (draw_date,),
            )
            cursor.execute(
                "UPDATE lottery_results SET total_pool = total_pool + ? WHERE draw_date = ?",
                (total_cost, draw_date),
            )

            cursor.execute(
                "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                (user_id, username, "购买彩票", -total_cost, new_points),
            )
            conn.commit()
            return {"status": "success", "today_tickets": today_count + ticket_count, "new_points": new_points}
        except Exception:
            conn.rollback()
            raise


def get_lottery_pool_info(user_id, today: str, target_date: str) -> dict:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        today_drawn = cursor.execute(
            "SELECT winning_numbers FROM lottery_results WHERE draw_date = ? AND winning_numbers != ''",
            (today,),
        ).fetchone()
        cursor.execute("INSERT OR IGNORE INTO lottery_results (draw_date, winning_numbers, total_pool) VALUES (?, '', 0)", (target_date,))
        conn.commit()

        target_pool_row = cursor.execute("SELECT total_pool FROM lottery_results WHERE draw_date = ?", (target_date,)).fetchone()
        target_pool = target_pool_row[0] if target_pool_row else 0
        target_tickets = cursor.execute("SELECT COUNT(*) FROM lottery_tickets WHERE draw_date = ?", (target_date,)).fetchone()[0]

        user_today_tickets = 0
        if user_id:
            user_today_tickets = cursor.execute(
                "SELECT COUNT(*) FROM lottery_tickets WHERE user_id = ? AND draw_date = ?",
                (user_id, target_date),
            ).fetchone()[0]

        today_winning = cursor.execute(
            "SELECT winning_numbers FROM lottery_results WHERE draw_date = ? AND winning_numbers != ''",
            (today,),
        ).fetchone()
        today_winning_number = today_winning[0] if today_winning else None

        my_winning = []
        my_prize_total = 0
        if user_id and today_winning_number:
            my_tickets = cursor.execute(
                "SELECT numbers FROM lottery_tickets WHERE user_id = ? AND draw_date = ?",
                (user_id, today),
            ).fetchall()
            my_winning = [ticket[0] for ticket in my_tickets if ticket[0] == today_winning_number]
            if my_winning:
                today_pool_row = cursor.execute("SELECT total_pool FROM lottery_results WHERE draw_date = ?", (today,)).fetchone()
                today_pool = today_pool_row[0] if today_pool_row else 0
                winner_count = cursor.execute("SELECT COUNT(*) FROM lottery_winners WHERE draw_date = ?", (today,)).fetchone()[0]
                winner_count = max(winner_count, 1)
                my_prize_total = len(my_winning) * (today_pool // winner_count)

        return {
            "today_drawn": today_drawn is not None,
            "today_pool": target_pool,
            "today_tickets": target_tickets,
            "user_today_tickets": user_today_tickets,
            "today_winning_number": today_winning_number,
            "my_winning_tickets": my_winning,
            "my_prize_total": my_prize_total,
        }


def list_lottery_results(user_id=None) -> list:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        results = cursor.execute(
            """
            SELECT draw_date, winning_numbers, total_pool
            FROM lottery_results
            WHERE winning_numbers != ''
            ORDER BY draw_date DESC
            LIMIT 7
            """
        ).fetchall()

        formatted_results = []
        for row in results:
            draw_date = row[0]
            winning_number = row[1]
            pool = row[2]

            winner_count = cursor.execute(
                "SELECT COUNT(*) FROM lottery_winners WHERE draw_date = ?",
                (draw_date,),
            ).fetchone()[0]

            winners_list = []
            if winner_count > 0:
                winners_data = cursor.execute(
                    """
                    SELECT w.user_id, w.username, w.prize_level, w.prize_amount
                    FROM lottery_winners w
                    WHERE w.draw_date = ?
                    ORDER BY w.prize_amount DESC
                    """,
                    (draw_date,),
                ).fetchall()
                for winner in winners_data:
                    winner_user_id = winner[0]
                    username = winner[1] or ""
                    if user_id and winner_user_id == user_id:
                        masked_username = username
                    elif len(username) > 3:
                        masked_username = username[:3] + "***"
                    else:
                        masked_username = username[:1] + "***" if username else "***"
                    winners_list.append(
                        {
                            "username": masked_username,
                            "prize_level": winner[2],
                            "prize_amount": winner[3],
                        }
                    )

            my_won = False
            my_prize = 0
            my_winning_tickets = []
            if user_id:
                my_tickets = cursor.execute(
                    "SELECT numbers FROM lottery_tickets WHERE user_id = ? AND draw_date = ?",
                    (user_id, draw_date),
                ).fetchall()
                for ticket in my_tickets:
                    ticket_number = ticket[0]
                    if ticket_number == winning_number:
                        my_won = True
                        my_winning_tickets.append(ticket_number)
                if my_won and winner_count > 0:
                    my_prize = len(my_winning_tickets) * (pool // winner_count)

            formatted_results.append(
                {
                    "date": draw_date,
                    "winning_number": winning_number,
                    "pool": pool,
                    "winners": winner_count,
                    "winners_list": winners_list,
                    "my_won": my_won,
                    "my_prize": my_prize,
                    "my_winning_tickets": my_winning_tickets,
                }
            )

        return formatted_results


def perform_user_checkin(user_id: str, username: str) -> dict:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        try:
            conn.execute("BEGIN IMMEDIATE")
            if cursor.execute(
                "SELECT 1 FROM point_logs WHERE user_id = ? AND action LIKE '每日签到%' AND date(created_at, 'localtime') = date('now', 'localtime')",
                (user_id,),
            ).fetchone():
                conn.rollback()
                return {"status": "error", "message": "今天已经签到过了，明天再来吧！"}

            config = {row[0]: row[1] for row in cursor.execute("SELECT key, value FROM point_config").fetchall()}
            reward = random.randint(int(config.get("checkin_min", 10)), int(config.get("checkin_max", 30)))

            streak_bonus = 0
            streak_count = 0
            if int(config.get("enable_streak_bonus", 0)) == 1:
                today = datetime.date.today()
                yesterday = today - datetime.timedelta(days=1)

                streak_row = cursor.execute(
                    "SELECT streak_count, last_checkin FROM point_checkin_streak WHERE user_id = ?",
                    (user_id,),
                ).fetchone()

                if streak_row:
                    last_checkin = streak_row[1]
                    if last_checkin == str(yesterday):
                        streak_count = streak_row[0] + 1
                    elif last_checkin == str(today):
                        streak_count = streak_row[0]
                    elif int(config.get("streak_reset_on_miss", 1)) == 1:
                        streak_count = 1
                    else:
                        streak_count = streak_row[0] + 1
                else:
                    streak_count = 1

                if streak_count >= 7 and streak_count % 7 == 0:
                    streak_bonus = int(config.get("streak_7_days", 100))
                if streak_count >= 30 and streak_count % 30 == 0:
                    streak_bonus += int(config.get("streak_30_days", 500))

                cursor.execute(
                    "INSERT OR REPLACE INTO point_checkin_streak (user_id, streak_count, last_checkin) VALUES (?, ?, ?)",
                    (user_id, streak_count, str(today)),
                )

            total_reward = reward + streak_bonus

            row = cursor.execute("SELECT points FROM users_meta WHERE user_id = ?", (user_id,)).fetchone()
            new_points = (row[0] or 0) + total_reward if row else total_reward
            if row:
                cursor.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_points, user_id))
            else:
                cursor.execute("INSERT INTO users_meta (user_id, points) VALUES (?, ?)", (user_id, new_points))

            action_desc = "每日签到"
            if streak_bonus > 0:
                action_desc += f" (连续{streak_count}天奖励+{streak_bonus})"

            cursor.execute(
                "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                (user_id, username, action_desc, total_reward, new_points),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    return {
        "status": "success",
        "message": f"签到成功！抽中 {reward} 积分",
        "reward": reward,
        "balance": new_points,
        "streak_count": streak_count,
        "streak_bonus": streak_bonus,
    }
