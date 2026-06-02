import datetime
import random

from app.infra.db.system_store import system_store


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


def save_red_packet_message_id(packet_id: int, message_id) -> None:
    system_store.execute(
        "UPDATE point_red_packets SET message_id = ? WHERE id = ?",
        (str(message_id), packet_id),
    )


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
