from app.infra.db.system_store import system_store


def ensure_user_bot_tables() -> None:
    with system_store.connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tg_user_bindings (
                tg_user_id TEXT PRIMARY KEY,
                emby_user_id TEXT,
                emby_username TEXT,
                tg_username TEXT,
                tg_display_name TEXT,
                init_password TEXT DEFAULT '',
                bound_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        try:
            conn.execute("ALTER TABLE tg_user_bindings ADD COLUMN init_password TEXT DEFAULT ''")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE tg_user_bindings ADD COLUMN tg_username TEXT")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE tg_user_bindings ADD COLUMN tg_display_name TEXT")
        except Exception:
            pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tg_user_blacklist (
                tg_user_id TEXT PRIMARY KEY,
                reason TEXT DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tg_reg_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_user_id TEXT,
                emby_username TEXT,
                emby_user_id TEXT,
                reg_type TEXT DEFAULT 'open',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tg_bot_users (
                tg_user_id TEXT PRIMARY KEY,
                tg_name TEXT DEFAULT '',
                first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tg_channel_bindings (
                channel_id TEXT PRIMARY KEY,
                tg_user_id TEXT,
                channel_title TEXT DEFAULT '',
                bound_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def delete_user_binding(tg_user_id) -> None:
    system_store.execute("DELETE FROM tg_user_bindings WHERE tg_user_id = ?", (str(tg_user_id),))


def get_binding_by_emby_id(emby_user_id):
    emby_id_str = str(emby_user_id).strip()
    row = system_store.fetch_one(
        """
        SELECT tg_user_id, emby_username, init_password, tg_username, tg_display_name
        FROM tg_user_bindings
        WHERE emby_user_id = ?
        """,
        (emby_id_str,),
    )
    if not row:
        row = system_store.fetch_one(
            """
            SELECT tg_user_id, emby_username, init_password, tg_username, tg_display_name
            FROM tg_user_bindings
            WHERE CAST(emby_user_id AS TEXT) = ?
            """,
            (emby_id_str,),
        )
    if not row:
        return None
    return {
        "tg_user_id": row["tg_user_id"],
        "emby_username": row["emby_username"],
        "init_password": row["init_password"] or "",
        "tg_username": row["tg_username"] or "",
        "tg_name": row["tg_display_name"] or "",
    }


def get_binding(tg_user_id):
    row = system_store.fetch_one(
        """
        SELECT emby_user_id, emby_username, init_password, tg_username, tg_display_name
        FROM tg_user_bindings
        WHERE tg_user_id = ?
        """,
        (str(tg_user_id),),
    )
    if not row:
        return None
    return {
        "emby_user_id": row["emby_user_id"],
        "emby_username": row["emby_username"],
        "init_password": row["init_password"] or "",
        "tg_username": row["tg_username"] or "",
        "tg_name": row["tg_display_name"] or "",
    }


def get_tg_user_id_by_username(tg_username: str):
    row = system_store.fetch_one(
        "SELECT tg_user_id FROM tg_user_bindings WHERE tg_username = ?",
        (tg_username,),
    )
    return row["tg_user_id"] if row else None


def get_binding_by_tg_user_or_username(identifier):
    row = system_store.fetch_one(
        """
        SELECT emby_user_id, emby_username, tg_display_name
        FROM tg_user_bindings
        WHERE tg_user_id = ? OR tg_username = ?
        """,
        (str(identifier), str(identifier)),
    )
    if not row:
        return None
    return {
        "emby_user_id": row["emby_user_id"],
        "emby_username": row["emby_username"],
        "tg_display_name": row["tg_display_name"] or row["emby_username"],
    }


def get_channel_binding(channel_id):
    return system_store.fetch_one(
        "SELECT tg_user_id, channel_title FROM tg_channel_bindings WHERE channel_id = ?",
        (str(channel_id),),
    )


def bind_channel(channel_id, tg_user_id, channel_title: str = "") -> None:
    system_store.execute(
        """
        INSERT OR REPLACE INTO tg_channel_bindings (channel_id, tg_user_id, channel_title, bound_at)
        VALUES (?, ?, ?, datetime('now','localtime'))
        """,
        (str(channel_id), str(tg_user_id), channel_title),
    )


def unbind_channel(channel_id) -> None:
    system_store.execute("DELETE FROM tg_channel_bindings WHERE channel_id = ?", (str(channel_id),))


def list_bindings():
    rows = system_store.fetch_all("SELECT tg_user_id, emby_user_id, emby_username FROM tg_user_bindings")
    return [{"tg_user_id": row["tg_user_id"], "emby_user_id": row["emby_user_id"], "emby_username": row["emby_username"]} for row in rows]


def list_tg_binding_names():
    return system_store.fetch_all("SELECT emby_user_id, tg_username, tg_display_name FROM tg_user_bindings")


def list_emby_tg_user_bindings():
    return system_store.fetch_all("SELECT emby_user_id, tg_user_id FROM tg_user_bindings")


def count_bindings() -> int:
    row = system_store.fetch_one("SELECT COUNT(*) as count FROM tg_user_bindings")
    return row["count"] if row else 0


def create_registration_log(tg_user_id, emby_username, emby_user_id, reg_type: str = "open") -> None:
    system_store.execute(
        "INSERT INTO tg_reg_logs (tg_user_id, emby_username, emby_user_id, reg_type) VALUES (?, ?, ?, ?)",
        (str(tg_user_id), emby_username, emby_user_id, reg_type),
    )


def search_whois_bindings(normalized: str):
    select_sql = """
        SELECT
            b.tg_user_id,
            b.tg_username,
            b.tg_display_name,
            b.emby_user_id,
            b.emby_username,
            b.bound_at,
            m.expire_date
        FROM tg_user_bindings b
        LEFT JOIN users_meta m ON m.user_id = b.emby_user_id
    """

    params = []
    where_parts = []
    if normalized.isdigit():
        where_parts.append("b.tg_user_id = ?")
        params.append(normalized)

    where_parts.extend(
        [
            "LOWER(COALESCE(b.tg_username, '')) = LOWER(?)",
            "LOWER(COALESCE(b.emby_username, '')) = LOWER(?)",
        ]
    )
    params.extend([normalized, normalized])

    rows = system_store.fetch_all(
        f"{select_sql} WHERE {' OR '.join(where_parts)} ORDER BY b.bound_at DESC LIMIT 10",
        tuple(params),
    )
    if rows:
        return rows

    like_keyword = f"%{normalized}%"
    return system_store.fetch_all(
        f"""
        {select_sql}
        WHERE LOWER(COALESCE(b.tg_display_name, '')) LIKE LOWER(?)
           OR LOWER(COALESCE(b.tg_username, '')) LIKE LOWER(?)
           OR LOWER(COALESCE(b.emby_username, '')) LIKE LOWER(?)
        ORDER BY b.bound_at DESC
        LIMIT 10
        """,
        (like_keyword, like_keyword, like_keyword),
    )


def record_bot_user(tg_user_id, tg_name: str = "") -> None:
    system_store.execute(
        """
        INSERT INTO tg_bot_users (tg_user_id, tg_name, first_seen, last_seen)
        VALUES (?, ?, datetime('now','localtime'), datetime('now','localtime'))
        ON CONFLICT(tg_user_id) DO UPDATE SET
        tg_name = excluded.tg_name,
        last_seen = datetime('now','localtime')
        """,
        (str(tg_user_id), tg_name),
    )


def list_bot_users():
    rows = system_store.fetch_all("SELECT tg_user_id, tg_name FROM tg_bot_users")
    return [{"tg_user_id": row["tg_user_id"], "tg_name": row["tg_name"]} for row in rows]


def bind_user(tg_user_id, emby_user_id, emby_username, init_password: str = "", tg_username: str = "", tg_display_name: str = "") -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tg_user_bindings WHERE emby_user_id = ?", (emby_user_id,))
        cursor.execute(
            """
            INSERT OR REPLACE INTO tg_user_bindings
            (tg_user_id, tg_username, tg_display_name, emby_user_id, emby_username, init_password)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (str(tg_user_id), tg_username, tg_display_name, emby_user_id, emby_username, init_password),
        )
        conn.commit()


def update_binding_init_password(tg_user_id, init_password: str) -> None:
    system_store.execute(
        "UPDATE tg_user_bindings SET init_password = ? WHERE tg_user_id = ?",
        (init_password, str(tg_user_id)),
    )


def is_blacklisted(tg_user_id) -> bool:
    row = system_store.fetch_one("SELECT 1 FROM tg_user_blacklist WHERE tg_user_id = ?", (str(tg_user_id),))
    return bool(row)


def add_to_blacklist(tg_user_id, reason: str = "") -> None:
    system_store.execute(
        "INSERT OR REPLACE INTO tg_user_blacklist (tg_user_id, reason) VALUES (?, ?)",
        (str(tg_user_id), reason),
    )
