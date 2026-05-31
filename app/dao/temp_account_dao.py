from app.infra.db.system_store import system_store


def ensure_temp_account_tables() -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS temp_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                emby_user_id TEXT,
                current_password TEXT NOT NULL,
                template_user_id TEXT,
                allow_routes TEXT DEFAULT '',
                block_routes TEXT DEFAULT '',
                req_free INTEGER DEFAULT 0,
                req_free_count INTEGER DEFAULT -1,
                auto_update_enabled INTEGER DEFAULT 1,
                update_interval_hours INTEGER DEFAULT 24,
                update_interval_minutes INTEGER DEFAULT 0,
                last_password_update TEXT,
                next_password_update TEXT,
                notify_tg INTEGER DEFAULT 1,
                notify_wecom INTEGER DEFAULT 0,
                enabled INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                remark TEXT DEFAULT '临时账号',
                tags TEXT DEFAULT ''
            )
            """
        )
        for ddl in [
            "ALTER TABLE temp_accounts ADD COLUMN allow_routes TEXT DEFAULT ''",
            "ALTER TABLE temp_accounts ADD COLUMN block_routes TEXT DEFAULT ''",
            "ALTER TABLE temp_accounts ADD COLUMN tags TEXT DEFAULT ''",
            "ALTER TABLE temp_accounts ADD COLUMN req_free INTEGER DEFAULT 0",
            "ALTER TABLE temp_accounts ADD COLUMN req_free_count INTEGER DEFAULT -1",
        ]:
            try:
                cursor.execute(ddl)
            except Exception:
                pass
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS temp_account_password_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                old_password TEXT,
                new_password TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                notify_sent INTEGER DEFAULT 0,
                FOREIGN KEY (account_id) REFERENCES temp_accounts(id)
            )
            """
        )
        conn.commit()


def list_temp_accounts():
    ensure_temp_account_tables()
    return system_store.fetch_all("SELECT * FROM temp_accounts ORDER BY created_at DESC")


def get_temp_account(account_id: int):
    ensure_temp_account_tables()
    return system_store.fetch_one("SELECT * FROM temp_accounts WHERE id = ?", (account_id,))


def get_temp_account_identity(account_id: int):
    ensure_temp_account_tables()
    return system_store.fetch_one("SELECT emby_user_id, username FROM temp_accounts WHERE id = ?", (account_id,))


def temp_account_username_exists(username: str) -> bool:
    ensure_temp_account_tables()
    return bool(system_store.fetch_one("SELECT id FROM temp_accounts WHERE username = ?", (username,)))


def delete_temp_account_record(account_id: int) -> None:
    ensure_temp_account_tables()
    with system_store.connect() as conn:
        conn.execute("DELETE FROM temp_accounts WHERE id = ?", (account_id,))
        conn.execute("DELETE FROM temp_account_password_history WHERE account_id = ?", (account_id,))
        conn.commit()


def set_temp_account_enabled(account_id: int, enabled: int) -> None:
    ensure_temp_account_tables()
    system_store.execute("UPDATE temp_accounts SET enabled = ? WHERE id = ?", (enabled, account_id))


def update_temp_account_config(account_id: int, data: dict, next_password_update=None, emby_user_id=None) -> None:
    ensure_temp_account_tables()
    update_fields = []
    update_values = []
    for field in [
        "remark",
        "auto_update_enabled",
        "update_interval_hours",
        "update_interval_minutes",
        "notify_tg",
        "notify_wecom",
        "allow_routes",
        "block_routes",
        "req_free",
        "req_free_count",
        "tags",
    ]:
        if field in data:
            update_fields.append(f"{field} = ?")
            update_values.append(data[field])

    if next_password_update is not None:
        update_fields.append("next_password_update = ?")
        update_values.append(next_password_update)

    if not update_fields:
        return

    with system_store.connect() as conn:
        cursor = conn.cursor()
        update_values.append(account_id)
        cursor.execute(f"UPDATE temp_accounts SET {', '.join(update_fields)} WHERE id = ?", update_values)

        if emby_user_id:
            meta_fields = []
            meta_values = []
            for field in ["remark", "allow_routes", "block_routes", "req_free", "req_free_count", "tags"]:
                if field in data:
                    meta_fields.append(f"{field} = ?")
                    meta_values.append(data[field])
            if meta_fields:
                meta_values.append(emby_user_id)
                cursor.execute(f"UPDATE users_meta SET {', '.join(meta_fields)} WHERE user_id = ?", meta_values)

        conn.commit()


def list_temp_account_password_history(account_id: int, limit: int = 20):
    ensure_temp_account_tables()
    return system_store.fetch_all(
        """
        SELECT * FROM temp_account_password_history
        WHERE account_id = ?
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (account_id, limit),
    )


def create_temp_account_with_meta(
    username: str,
    emby_user_id: str,
    password: str,
    template_user_id: str,
    allow_routes: str,
    block_routes: str,
    req_free: int,
    req_free_count: int,
    update_interval_hours: int,
    update_interval_minutes: int,
    notify_tg: int,
    notify_wecom: int,
    now_iso: str,
    next_update_iso: str,
    remark: str,
    tags: str,
) -> None:
    ensure_temp_account_tables()
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO temp_accounts (
                username, emby_user_id, current_password, template_user_id,
                allow_routes, block_routes, req_free, req_free_count,
                auto_update_enabled, update_interval_hours, update_interval_minutes,
                last_password_update, next_password_update,
                notify_tg, notify_wecom, enabled, created_at, remark, tags
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                username,
                emby_user_id,
                password,
                template_user_id,
                allow_routes,
                block_routes,
                req_free,
                req_free_count,
                1,
                update_interval_hours,
                update_interval_minutes,
                now_iso,
                next_update_iso,
                notify_tg,
                notify_wecom,
                1,
                now_iso,
                remark,
                tags,
            ),
        )
        cursor.execute(
            """
            INSERT OR REPLACE INTO users_meta
            (user_id, remark, is_vip, max_concurrent, req_free, req_free_count, allow_routes, block_routes, tags)
            VALUES (?, ?, 0, NULL, ?, ?, ?, ?, ?)
            """,
            (emby_user_id, remark, req_free, req_free_count, allow_routes, block_routes, tags),
        )
        if tags:
            for tag_name in tags.split(","):
                tag_name = tag_name.strip()
                if not tag_name:
                    continue
                existing = cursor.execute("SELECT id FROM user_tags WHERE name = ?", (tag_name,)).fetchone()
                if not existing:
                    cursor.execute("INSERT INTO user_tags (name, color) VALUES (?, 'blue')", (tag_name,))
        conn.commit()


def update_temp_account_password(account_id: int, new_password: str, last_update: str, next_update: str, old_password: str) -> None:
    ensure_temp_account_tables()
    with system_store.connect() as conn:
        conn.execute(
            """
            UPDATE temp_accounts
            SET current_password = ?, last_password_update = ?, next_password_update = ?
            WHERE id = ?
            """,
            (new_password, last_update, next_update, account_id),
        )
        conn.execute(
            """
            INSERT INTO temp_account_password_history (account_id, old_password, new_password, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (account_id, old_password, new_password, last_update),
        )
        conn.commit()


def list_temp_accounts_for_password_update():
    ensure_temp_account_tables()
    return system_store.fetch_all(
        """
        SELECT id, username, next_password_update
        FROM temp_accounts
        WHERE enabled = 1 AND auto_update_enabled = 1
        """
    )
