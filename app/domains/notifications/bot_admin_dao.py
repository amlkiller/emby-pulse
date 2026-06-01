from app.infra.db.system_store import system_store


def list_user_blacklist():
    return system_store.fetch_all("SELECT tg_user_id, reason, created_at FROM tg_user_blacklist ORDER BY created_at DESC")


def remove_user_blacklist(tg_user_id: str) -> None:
    system_store.execute("DELETE FROM tg_user_blacklist WHERE tg_user_id = ?", (tg_user_id,))


def list_registration_logs(days: int = 7):
    return system_store.fetch_all(
        """
        SELECT id, tg_user_id, emby_username, emby_user_id, reg_type, created_at
        FROM tg_reg_logs
        WHERE date(created_at) >= date('now', ?)
        ORDER BY created_at DESC
        LIMIT 500
        """,
        (f"-{days} days",),
    )


def get_registration_stats():
    with system_store.connect() as conn:
        today_count = conn.execute("SELECT COUNT(*) as cnt FROM tg_reg_logs WHERE date(created_at) = date('now')").fetchone()[
            "cnt"
        ]
        week_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM tg_reg_logs WHERE date(created_at) >= date('now', '-7 days')"
        ).fetchone()["cnt"]
        total_count = conn.execute("SELECT COUNT(*) as cnt FROM tg_reg_logs").fetchone()["cnt"]
        daily_stats = conn.execute(
            """
            SELECT date(created_at) as date, COUNT(*) as count
            FROM tg_reg_logs
            WHERE date(created_at) >= date('now', '-30 days')
            GROUP BY date(created_at)
            ORDER BY date DESC
            """
        ).fetchall()
        batch_used = conn.execute("SELECT COUNT(*) as cnt FROM tg_reg_logs WHERE reg_type = 'open'").fetchone()["cnt"]

    return {
        "today": today_count,
        "week": week_count,
        "total": total_count,
        "batch_used": batch_used,
        "daily": [dict(row) for row in daily_stats],
    }


def clear_registration_logs() -> None:
    system_store.execute("DELETE FROM tg_reg_logs")


def count_registration_logs() -> int:
    row = system_store.fetch_one("SELECT COUNT(*) as cnt FROM tg_reg_logs")
    return row["cnt"] if row else 0


def list_tg_bindings_for_sync():
    return system_store.fetch_all("SELECT tg_user_id, tg_username, tg_display_name FROM tg_user_bindings")


def update_tg_binding_names(tg_user_id, username, display_name) -> None:
    system_store.execute(
        "UPDATE tg_user_bindings SET tg_username = ?, tg_display_name = ? WHERE tg_user_id = ?",
        (username, display_name, tg_user_id),
    )


def list_tg_bindings():
    return system_store.fetch_all(
        """
        SELECT tg_user_id, emby_user_id, emby_username, tg_username, tg_display_name, bound_at
        FROM tg_user_bindings
        ORDER BY bound_at DESC
        """
    )


def get_lottery_draw_result(draw_date: str):
    return system_store.fetch_one(
        "SELECT winning_numbers, total_pool FROM lottery_results WHERE draw_date = ?",
        (draw_date,),
    )


def reset_lottery_draw(today: str, tomorrow: str):
    with system_store.connect() as conn:
        cursor = conn.cursor()
        result = cursor.execute("SELECT winning_numbers FROM lottery_results WHERE draw_date = ?", (today,)).fetchone()
        if not result or not result[0]:
            return {"ok": False, "message": "今日尚未开奖，无需清除"}

        today_pool_row = cursor.execute("SELECT total_pool FROM lottery_results WHERE draw_date = ?", (today,)).fetchone()
        today_pool = today_pool_row[0] if today_pool_row else 0

        winners = cursor.execute(
            "SELECT prize_level, COUNT(*), SUM(prize_amount) FROM lottery_winners WHERE draw_date = ? GROUP BY prize_level",
            (today,),
        ).fetchall()
        total_distributed = sum(row[2] for row in winners) if winners else 0
        remaining_pool = max(0, today_pool - total_distributed)

        if remaining_pool > 0:
            cursor.execute(
                "UPDATE lottery_results SET total_pool = MAX(0, total_pool - ?) WHERE draw_date = ?",
                (remaining_pool, tomorrow),
            )

        lucky_winners = cursor.execute(
            "SELECT user_id, prize_amount FROM lottery_winners WHERE draw_date = ? AND prize_level = 5",
            (today,),
        ).fetchall()
        for user_id, prize_amount in lucky_winners:
            row = cursor.execute("SELECT points FROM users_meta WHERE user_id = ?", (user_id,)).fetchone()
            if row:
                cursor.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (row[0] - prize_amount, user_id))

        normal_winners = cursor.execute(
            "SELECT user_id, prize_amount FROM lottery_winners WHERE draw_date = ? AND prize_level != 5",
            (today,),
        ).fetchall()
        for user_id, prize_amount in normal_winners:
            row = cursor.execute("SELECT points FROM users_meta WHERE user_id = ?", (user_id,)).fetchone()
            if row:
                cursor.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (row[0] - prize_amount, user_id))

        cursor.execute("UPDATE lottery_results SET winning_numbers = '' WHERE draw_date = ?", (today,))
        cursor.execute("DELETE FROM lottery_winners WHERE draw_date = ?", (today,))
        cursor.execute("DELETE FROM point_logs WHERE action LIKE '彩票%' AND date(created_at) = ?", (today,))
        conn.commit()

    return {"ok": True, "remaining_pool": remaining_pool}


def fix_lottery_pool(today: str, tomorrow: str):
    with system_store.connect() as conn:
        cursor = conn.cursor()
        today_drawn = cursor.execute(
            "SELECT winning_numbers FROM lottery_results WHERE draw_date = ? AND winning_numbers != ''",
            (today,),
        ).fetchone()

        if today_drawn:
            today_pool_row = cursor.execute("SELECT total_pool FROM lottery_results WHERE draw_date = ?", (today,)).fetchone()
            today_pool = today_pool_row[0] if today_pool_row else 0
            winners = cursor.execute("SELECT SUM(prize_amount) FROM lottery_winners WHERE draw_date = ?", (today,)).fetchone()
            total_distributed = winners[0] if winners and winners[0] else 0
            correct_remaining = max(0, today_pool - total_distributed)
            tomorrow_tickets = cursor.execute("SELECT SUM(cost) FROM lottery_tickets WHERE draw_date = ?", (tomorrow,)).fetchone()
            tomorrow_ticket_pool = tomorrow_tickets[0] if tomorrow_tickets and tomorrow_tickets[0] else 0
            correct_tomorrow_pool = correct_remaining + tomorrow_ticket_pool

            cursor.execute(
                "INSERT OR IGNORE INTO lottery_results (draw_date, winning_numbers, total_pool) VALUES (?, '', 0)",
                (tomorrow,),
            )
            cursor.execute("UPDATE lottery_results SET total_pool = ? WHERE draw_date = ?", (correct_tomorrow_pool, tomorrow))
            conn.commit()
            return {
                "drawn": True,
                "new_pool": correct_tomorrow_pool,
                "remaining": correct_remaining,
                "ticket_pool": tomorrow_ticket_pool,
            }

        today_tickets = cursor.execute("SELECT SUM(cost) FROM lottery_tickets WHERE draw_date = ?", (today,)).fetchone()
        today_ticket_pool = today_tickets[0] if today_tickets and today_tickets[0] else 0
        cursor.execute(
            "INSERT OR IGNORE INTO lottery_results (draw_date, winning_numbers, total_pool) VALUES (?, '', 0)",
            (today,),
        )
        cursor.execute("UPDATE lottery_results SET total_pool = ? WHERE draw_date = ?", (today_ticket_pool, today))
        conn.commit()
        return {"drawn": False, "new_pool": today_ticket_pool}


def clear_active_scratch_card():
    with system_store.connect() as conn:
        cursor = conn.cursor()
        card = cursor.execute("SELECT id, status FROM scratch_cards WHERE status = 'active'").fetchone()
        if not card:
            return {"ok": False, "message": "没有进行中的刮刮卡"}

        card_id = card[0]
        scratched = cursor.execute(
            "SELECT user_id FROM scratch_card_slots WHERE card_id = ? AND is_scratched = 1",
            (card_id,),
        ).fetchall()
        price = cursor.execute("SELECT price FROM scratch_cards WHERE id = ?", (card_id,)).fetchone()[0]

        for (user_id,) in scratched:
            row = cursor.execute("SELECT points FROM users_meta WHERE user_id = ?", (user_id,)).fetchone()
            if row:
                cursor.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (row[0] + price, user_id))

        cursor.execute("DELETE FROM scratch_card_slots WHERE card_id = ?", (card_id,))
        cursor.execute("DELETE FROM scratch_cards WHERE id = ?", (card_id,))
        conn.commit()

    return {"ok": True, "card_id": card_id, "refund_count": len(scratched)}


def get_lottery_pool_info(today: str, tomorrow: str):
    with system_store.connect() as conn:
        today_drawn = conn.execute(
            "SELECT winning_numbers FROM lottery_results WHERE draw_date = ? AND winning_numbers != ''",
            (today,),
        ).fetchone()
        target_date = tomorrow if today_drawn else today
        target_pool = conn.execute("SELECT total_pool FROM lottery_results WHERE draw_date = ?", (target_date,)).fetchone()
        target_tickets = conn.execute("SELECT COUNT(*) FROM lottery_tickets WHERE draw_date = ?", (target_date,)).fetchone()[0]
        total_accumulated = (
            conn.execute("SELECT SUM(total_pool) FROM lottery_results WHERE winning_numbers = ''").fetchone()[0] or 0
        )

    return {
        "target_date": target_date,
        "target_pool": target_pool[0] if target_pool else 0,
        "target_tickets": target_tickets,
        "total_accumulated": total_accumulated,
        "is_drawn": bool(today_drawn),
    }


def adjust_lottery_pool(today: str, tomorrow: str, init_pool: int):
    with system_store.connect() as conn:
        today_drawn = conn.execute(
            "SELECT winning_numbers FROM lottery_results WHERE draw_date = ? AND winning_numbers != ''",
            (today,),
        ).fetchone()
        target_date = tomorrow if today_drawn else today

        conn.execute(
            "INSERT OR IGNORE INTO lottery_results (draw_date, winning_numbers, total_pool) VALUES (?, '', 0)",
            (target_date,),
        )
        conn.execute("UPDATE lottery_results SET total_pool = MAX(0, total_pool + ?) WHERE draw_date = ?", (init_pool, target_date))
        conn.commit()
        new_pool = conn.execute("SELECT total_pool FROM lottery_results WHERE draw_date = ?", (target_date,)).fetchone()[0]

    return {"new_pool": new_pool, "target_date": target_date}
