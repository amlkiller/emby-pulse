from app.infra.db.system_store import system_store


def buy_scratch_card(user_id: str, username: str, cost: int) -> dict:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = cursor.execute("SELECT points FROM users_meta WHERE user_id = ?", (user_id,)).fetchone()
            current_points = row[0] if row else 0
            if current_points < cost:
                conn.rollback()
                return {"status": "error", "message": f"积分不足（需要 {cost} 积分）"}

            new_points = current_points - cost
            if row:
                cursor.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_points, user_id))
            else:
                cursor.execute("INSERT INTO users_meta (user_id, points) VALUES (?, ?)", (user_id, new_points))

            cursor.execute(
                "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                (user_id, username, "刮刮乐-购买", -cost, new_points),
            )
            conn.commit()
            return {"status": "success", "new_points": new_points}
        except Exception:
            conn.rollback()
            raise


def get_active_scratch_card():
    return system_store.fetch_one(
        """
        SELECT id, total_slots, filled_slots, price, status, created_by, chat_id, message_id
        FROM scratch_cards
        WHERE status = 'active'
        ORDER BY created_at DESC
        LIMIT 1
        """
    )


def get_scratch_card_slots(card_id: int) -> list:
    return system_store.fetch_all(
        "SELECT slot_number, is_scratched, username FROM scratch_card_slots WHERE card_id = ? ORDER BY slot_number",
        (card_id,),
    )


def create_scratch_card(total_slots: int = 9, price: int = 100, created_by: str = "", chat_id=None, prizes: list = None) -> dict:
    prizes = prizes or []
    if not prizes:
        return {"status": "error", "message": "奖品配置不能为空"}

    with system_store.connect() as conn:
        cursor = conn.cursor()
        try:
            conn.execute("BEGIN EXCLUSIVE")
            existing = cursor.execute("SELECT id FROM scratch_cards WHERE status = 'active'").fetchone()
            if existing:
                conn.rollback()
                return {"status": "error", "message": "已有进行中的刮刮乐，请先刮完再创建新的"}

            cursor.execute(
                "INSERT INTO scratch_cards (total_slots, price, created_by, chat_id) VALUES (?, ?, ?, ?)",
                (total_slots, price, created_by, str(chat_id)),
            )
            new_card_id = cursor.lastrowid
            for i, prize in enumerate(prizes, 1):
                cursor.execute(
                    "INSERT INTO scratch_card_slots (card_id, slot_number, prize_amount) VALUES (?, ?, ?)",
                    (new_card_id, i, prize),
                )
            conn.commit()
            return {"status": "success", "card_id": new_card_id}
        except Exception:
            conn.rollback()
            raise


def save_scratch_card_message_id(card_id: int, message_id) -> None:
    system_store.execute("UPDATE scratch_cards SET message_id = ? WHERE id = ?", (message_id, card_id))


def get_scratch_card(card_id: int):
    return system_store.fetch_one(
        "SELECT id, total_slots, filled_slots, price, status, chat_id, message_id FROM scratch_cards WHERE id = ?",
        (card_id,),
    )


def get_scratch_card_slot(card_id: int, slot_number: int):
    return system_store.fetch_one(
        "SELECT id, is_scratched, prize_amount FROM scratch_card_slots WHERE card_id = ? AND slot_number = ?",
        (card_id, slot_number),
    )


def has_user_scratched_card(card_id: int, user_id: str):
    return system_store.fetch_one(
        "SELECT id FROM scratch_card_slots WHERE card_id = ? AND user_id = ? AND is_scratched = 1",
        (card_id, user_id),
    )


def update_scratch_card_slot(card_id: int, slot_number: int, user_id: str, username: str, price: int, display_name: str) -> dict:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        try:
            conn.execute("BEGIN EXCLUSIVE")
            card = cursor.execute(
                "SELECT total_slots, filled_slots, status, chat_id, message_id FROM scratch_cards WHERE id = ?",
                (card_id,),
            ).fetchone()
            if not card:
                conn.rollback()
                return {"status": "error", "message": "刮刮乐不存在"}
            total_slots, filled_slots, status, chat_id, message_id = card
            if status != "active":
                conn.rollback()
                return {"status": "error", "message": "刮刮乐已结束"}

            slot = cursor.execute(
                "SELECT id, is_scratched FROM scratch_card_slots WHERE card_id = ? AND slot_number = ?",
                (card_id, slot_number),
            ).fetchone()
            if not slot:
                conn.rollback()
                return {"status": "error", "message": "格子不存在"}
            if slot[1]:
                conn.rollback()
                return {"status": "error", "message": "这个格子已经被刮过了"}

            already_scratched = cursor.execute(
                "SELECT id FROM scratch_card_slots WHERE card_id = ? AND user_id = ? AND is_scratched = 1",
                (card_id, user_id),
            ).fetchone()
            if already_scratched:
                conn.rollback()
                return {"status": "error", "message": "你已经刮过这个刮刮乐了，每人只能刮一次！"}

            current_points_row = cursor.execute("SELECT points FROM users_meta WHERE user_id = ?", (user_id,)).fetchone()
            current_points = current_points_row[0] if current_points_row else 0
            if current_points < price:
                conn.rollback()
                return {"status": "error", "message": f"积分不足！需要 {price} 积分，当前: {current_points}"}

            new_points = current_points - price
            if current_points_row:
                cursor.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_points, user_id))
            else:
                cursor.execute("INSERT INTO users_meta (user_id, points) VALUES (?, ?)", (user_id, new_points))

            cursor.execute(
                "UPDATE scratch_card_slots SET is_scratched = 1, user_id = ?, username = ?, scratched_at = CURRENT_TIMESTAMP WHERE id = ?",
                (user_id, display_name, slot[0]),
            )
            new_filled = filled_slots + 1
            cursor.execute("UPDATE scratch_cards SET filled_slots = ? WHERE id = ?", (new_filled, card_id))
            cursor.execute(
                "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                (user_id, username, f"刮刮乐 #{card_id} 格子{slot_number}", -price, new_points),
            )
            conn.commit()
            return {
                "status": "success",
                "new_points": new_points,
                "new_filled": new_filled,
                "total_slots": total_slots,
                "chat_id": chat_id,
                "message_id": message_id,
            }
        except Exception:
            conn.rollback()
            raise


def complete_scratch_card(card_id: int) -> list:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        try:
            conn.execute("BEGIN EXCLUSIVE")
            card = cursor.execute("SELECT status FROM scratch_cards WHERE id = ?", (card_id,)).fetchone()
            if not card or card[0] != "active":
                conn.rollback()
                return []
            cursor.execute("UPDATE scratch_cards SET status = 'completed' WHERE id = ?", (card_id,))
            slots = cursor.execute(
                "SELECT slot_number, prize_amount, user_id, username FROM scratch_card_slots WHERE card_id = ? AND is_scratched = 1 ORDER BY slot_number",
                (card_id,),
            ).fetchall()
            for slot in slots:
                slot_number, prize_amount, user_id, username = slot
                if not user_id:
                    continue
                user_row = cursor.execute("SELECT points FROM users_meta WHERE user_id = ?", (user_id,)).fetchone()
                current_points = (user_row[0] or 0) + prize_amount if user_row else prize_amount
                if user_row:
                    cursor.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (current_points, user_id))
                else:
                    cursor.execute("INSERT INTO users_meta (user_id, points) VALUES (?, ?)", (user_id, current_points))
                display_name = username or f"用户{user_id}"
                cursor.execute(
                    "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                    (user_id, display_name, f"刮刮乐 #{card_id} 中奖", prize_amount, current_points),
                )
            conn.commit()
            return [
                {
                    "slot_number": slot[0],
                    "prize_amount": slot[1],
                    "user_id": slot[2],
                    "username": slot[3],
                }
                for slot in slots
            ]
        except Exception:
            conn.rollback()
            raise


def get_scratch_card_origin(card_id: int):
    return system_store.fetch_one("SELECT chat_id, message_id FROM scratch_cards WHERE id = ?", (card_id,))


def reveal_scratch_reward(user_id: str, username: str, reward: int) -> dict:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = cursor.execute("SELECT points FROM users_meta WHERE user_id = ?", (user_id,)).fetchone()
            current_points = row[0] if row else 0
            new_points = current_points + reward
            if row:
                cursor.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_points, user_id))
            else:
                cursor.execute("INSERT INTO users_meta (user_id, points) VALUES (?, ?)", (user_id, new_points))

            cursor.execute(
                "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                (user_id, username, "刮刮乐-中奖", reward, new_points),
            )
            conn.commit()
            return {"status": "success", "new_points": new_points}
        except Exception:
            conn.rollback()
            raise
