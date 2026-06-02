import datetime

from app.infra.db.schema_bootstrap import ensure_registered_table
from app.infra.db.system_store import system_store


def ensure_lottery_table() -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        for table_name in ("lottery_tickets", "lottery_results", "lottery_winners"):
            ensure_registered_table(cursor, table_name)
        conn.commit()


def get_lottery_winning_numbers(draw_date: str):
    return system_store.fetch_one("SELECT winning_numbers FROM lottery_results WHERE draw_date = ?", (draw_date,))


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
