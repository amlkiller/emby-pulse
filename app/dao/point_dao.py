import json
import datetime
import random

from app.infra.db.system_store import system_store


def get_point_config() -> dict:
    try:
        rows = system_store.fetch_all("SELECT key, value FROM point_config")
        return {row["key"]: row["value"] for row in rows}
    except Exception:
        return {}


def ensure_lottery_table() -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='lottery_tickets'")
        if not cursor.fetchone():
            cursor.execute(
                """
                CREATE TABLE lottery_tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    username TEXT,
                    numbers TEXT NOT NULL,
                    cost INTEGER,
                    draw_date TEXT,
                    created_at TEXT
                )
                """
            )
            conn.commit()


def ensure_points_schema() -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(users_meta)")
        columns = [column[1] for column in cursor.fetchall()]
        if "points" not in columns:
            cursor.execute("ALTER TABLE users_meta ADD COLUMN points INTEGER DEFAULT 0")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS point_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, username TEXT, action TEXT,
                amount INTEGER, balance INTEGER, created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute("CREATE TABLE IF NOT EXISTS point_config (key TEXT PRIMARY KEY, value TEXT)")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS point_checkin_streak (
                user_id TEXT PRIMARY KEY,
                streak_count INTEGER DEFAULT 0,
                last_checkin DATE
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS point_red_packets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                total_amount INTEGER,
                remain_amount INTEGER,
                total_count INTEGER,
                remain_count INTEGER,
                creator_id TEXT,
                creator_name TEXT,
                chat_id TEXT,
                message_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS point_red_packet_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                packet_id INTEGER,
                user_id TEXT,
                user_name TEXT,
                amount INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS point_transfer_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_user_id TEXT,
                from_user_name TEXT,
                to_user_id TEXT,
                to_user_name TEXT,
                amount INTEGER,
                fee INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS point_rob_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_user_id TEXT,
                from_user_name TEXT,
                to_user_id TEXT,
                to_user_name TEXT,
                amount INTEGER,
                success INTEGER DEFAULT 0,
                counter_amount INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS pk_invitations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                challenger_id TEXT,
                challenger_name TEXT,
                challenger_tg_name TEXT,
                target_id TEXT,
                target_name TEXT,
                target_tg_name TEXT,
                points INTEGER,
                chat_id TEXT,
                message_id TEXT,
                command_message_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME,
                status TEXT DEFAULT 'pending'
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS pk_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                challenger_id TEXT,
                challenger_name TEXT,
                target_id TEXT,
                target_name TEXT,
                points INTEGER,
                challenger_roll INTEGER,
                target_roll INTEGER,
                winner_id TEXT,
                winner_name TEXT,
                tax INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        red_packet_columns = cursor.execute("PRAGMA table_info(point_red_packets)").fetchall()
        red_packet_column_names = [column[1] for column in red_packet_columns]
        if "message_id" not in red_packet_column_names:
            cursor.execute("ALTER TABLE point_red_packets ADD COLUMN message_id TEXT")

        columns = cursor.execute("PRAGMA table_info(pk_invitations)").fetchall()
        column_names = [column[1] for column in columns]

        if "challenger_tg_name" not in column_names:
            cursor.execute("ALTER TABLE pk_invitations ADD COLUMN challenger_tg_name TEXT")
        if "target_tg_name" not in column_names:
            cursor.execute("ALTER TABLE pk_invitations ADD COLUMN target_tg_name TEXT")
        if "command_message_id" not in column_names:
            cursor.execute("ALTER TABLE pk_invitations ADD COLUMN command_message_id TEXT")

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
