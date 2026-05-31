import sqlite3

from app.infra.db.system_store import system_store


def ensure_users_meta_column(column_name: str, column_definition: str) -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(users_meta)")
        columns = [column[1] for column in cursor.fetchall()]
        if column_name not in columns:
            cursor.execute(f"ALTER TABLE users_meta ADD COLUMN {column_definition}")
            conn.commit()


def migrate_admin_disabled(disabled_user_ids, today: str):
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(users_meta)")
        columns = [row[1] for row in cursor.fetchall()]
        if "admin_disabled" in columns:
            return None

        cursor.execute("ALTER TABLE users_meta ADD COLUMN admin_disabled INTEGER DEFAULT 0")
        migrated_count = 0
        for user_id in disabled_user_ids:
            row = cursor.execute("SELECT expire_date FROM users_meta WHERE user_id = ?", (user_id,)).fetchone()
            expire_date = row[0] if row else None
            if not expire_date or expire_date >= today:
                cursor.execute("UPDATE users_meta SET admin_disabled = 1 WHERE user_id = ?", (user_id,))
                migrated_count += 1

        conn.commit()
        return migrated_count


def list_users_with_expire_date_for_check():
    return system_store.fetch_all("SELECT user_id, expire_date FROM users_meta WHERE expire_date IS NOT NULL")


def list_all_user_meta():
    return system_store.fetch_all("SELECT * FROM users_meta")


def get_user_meta(user_id: str):
    return system_store.fetch_one("SELECT * FROM users_meta WHERE user_id = ?", (user_id,))


def set_user_admin_disabled(user_id: str, disabled: bool) -> None:
    system_store.execute(
        "UPDATE users_meta SET admin_disabled = ? WHERE user_id = ?",
        (1 if disabled else 0, user_id),
    )


def save_user_admin_disabled(user_id: str, disabled: bool, created_at: str) -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users_meta (user_id, created_at) VALUES (?, ?)", (user_id, created_at))
        cursor.execute("UPDATE users_meta SET admin_disabled = ? WHERE user_id = ?", (1 if disabled else 0, user_id))
        conn.commit()


def delete_user_meta(user_id: str) -> None:
    system_store.execute("DELETE FROM users_meta WHERE user_id = ?", (user_id,))


def delete_temp_account_by_emby_user(user_id: str) -> None:
    system_store.execute("DELETE FROM temp_accounts WHERE emby_user_id = ?", (user_id,))


def get_user_policy_meta(user_id: str):
    return system_store.fetch_one("SELECT max_concurrent, is_vip FROM users_meta WHERE user_id = ?", (user_id,))


def save_user_expire_preserve(user_id: str, expire_date, created_at: str) -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        row = cursor.execute("SELECT 1 FROM users_meta WHERE user_id = ?", (user_id,)).fetchone()
        if row:
            cursor.execute("UPDATE users_meta SET expire_date = ? WHERE user_id = ?", (expire_date, user_id))
        else:
            cursor.execute(
                "INSERT INTO users_meta (user_id, expire_date, created_at) VALUES (?, ?, ?)",
                (user_id, expire_date, created_at),
            )
        conn.commit()


def save_user_policy_meta(user_id: str, max_concurrent, is_vip, created_at: str) -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        row = cursor.execute("SELECT 1 FROM users_meta WHERE user_id = ?", (user_id,)).fetchone()
        if row:
            cursor.execute(
                "UPDATE users_meta SET max_concurrent = ?, is_vip = ? WHERE user_id = ?",
                (max_concurrent, is_vip, user_id),
            )
        else:
            cursor.execute(
                "INSERT INTO users_meta (user_id, max_concurrent, is_vip, created_at) VALUES (?, ?, ?, ?)",
                (user_id, max_concurrent, is_vip, created_at),
            )
        conn.commit()


def save_user_routes_preserve(user_id: str, allow_routes: str, block_routes: str, created_at: str) -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        row = cursor.execute("SELECT 1 FROM users_meta WHERE user_id = ?", (user_id,)).fetchone()
        if row:
            cursor.execute(
                "UPDATE users_meta SET allow_routes = ?, block_routes = ? WHERE user_id = ?",
                (allow_routes, block_routes, user_id),
            )
        else:
            cursor.execute(
                "INSERT INTO users_meta (user_id, allow_routes, block_routes, created_at) VALUES (?, ?, ?, ?)",
                (user_id, allow_routes, block_routes, created_at),
            )
        conn.commit()


def save_manage_user_meta(
    user_id: str,
    expire_date,
    max_concurrent,
    is_vip,
    remark: str,
    allow_routes,
    block_routes,
    req_free,
    req_free_count,
    tags: str,
    created_at: str,
) -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        row = cursor.execute("SELECT * FROM users_meta WHERE user_id = ?", (user_id,)).fetchone()
        if row:
            columns = [description[0] for description in cursor.description]
            existing = dict(zip(columns, row))
            update_fields = [
                "expire_date = ?",
                "max_concurrent = ?",
                "is_vip = ?",
                "remark = ?",
                "req_free = ?",
                "req_free_count = ?",
                "tags = ?",
            ]
            update_values = [expire_date, max_concurrent, is_vip, remark, req_free, req_free_count, tags]

            old_allow = existing.get("allow_routes", "") or ""
            old_block = existing.get("block_routes", "") or ""
            if allow_routes != old_allow:
                update_fields.append("allow_routes = ?")
                update_values.append(allow_routes if allow_routes else "")
            if block_routes != old_block:
                update_fields.append("block_routes = ?")
                update_values.append(block_routes if block_routes else "")

            update_values.append(user_id)
            cursor.execute(f"UPDATE users_meta SET {', '.join(update_fields)} WHERE user_id = ?", update_values)
        else:
            cursor.execute(
                """
                INSERT INTO users_meta
                (user_id, expire_date, max_concurrent, is_vip, remark, allow_routes, block_routes, req_free, req_free_count, tags, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    expire_date,
                    max_concurrent,
                    is_vip,
                    remark,
                    allow_routes,
                    block_routes,
                    req_free,
                    req_free_count,
                    tags,
                    created_at,
                ),
            )
        conn.commit()


def create_user_meta(
    user_id: str,
    expire_date,
    max_concurrent,
    is_vip,
    remark: str,
    allow_routes: str,
    block_routes: str,
    req_free,
    req_free_count,
    created_at: str,
) -> None:
    system_store.execute(
        """
        INSERT INTO users_meta
        (user_id, expire_date, max_concurrent, is_vip, remark, allow_routes, block_routes, req_free, req_free_count, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, expire_date, max_concurrent, is_vip, remark, allow_routes, block_routes, req_free, req_free_count, created_at),
    )


def sync_user_library_permissions(user_id: str, enable_all_folders: bool, enabled_folders):
    ensure_users_meta_column("admin_enabled_folders", "admin_enabled_folders TEXT")
    ensure_users_meta_column("hidden_libraries", "hidden_libraries TEXT")
    enabled_folder_set = set(enabled_folders or [])

    with system_store.connect() as conn:
        cursor = conn.cursor()
        row = cursor.execute("SELECT hidden_libraries FROM users_meta WHERE user_id = ?", (user_id,)).fetchone()
        user_hidden_str = row[0] if row and row[0] else ""
        user_hidden_folders = set(g.strip() for g in user_hidden_str.split(",") if g.strip()) if user_hidden_str else set()

        if enable_all_folders:
            cursor.execute("UPDATE users_meta SET admin_enabled_folders = NULL WHERE user_id = ?", (user_id,))
            conn.commit()
            return None

        admin_folders_str = ",".join(enabled_folder_set) if enabled_folder_set else ""
        cursor.execute("UPDATE users_meta SET admin_enabled_folders = ? WHERE user_id = ?", (admin_folders_str, user_id))
        valid_hidden = user_hidden_folders & enabled_folder_set
        hidden_str = ",".join(valid_hidden) if valid_hidden else ""
        cursor.execute("UPDATE users_meta SET hidden_libraries = ? WHERE user_id = ?", (hidden_str, user_id))
        conn.commit()
        return [folder for folder in enabled_folder_set if folder not in valid_hidden]


def get_user_library_settings(user_id: str):
    ensure_users_meta_column("admin_enabled_folders", "admin_enabled_folders TEXT")
    ensure_users_meta_column("hidden_libraries", "hidden_libraries TEXT DEFAULT ''")
    return system_store.fetch_one(
        "SELECT admin_enabled_folders, hidden_libraries FROM users_meta WHERE user_id = ?",
        (user_id,),
    )


def get_user_admin_enabled_folders(user_id: str):
    ensure_users_meta_column("admin_enabled_folders", "admin_enabled_folders TEXT")
    return system_store.fetch_one("SELECT admin_enabled_folders FROM users_meta WHERE user_id = ?", (user_id,))


def save_user_admin_enabled_folders(user_id: str, admin_enabled_folders: str) -> None:
    ensure_users_meta_column("admin_enabled_folders", "admin_enabled_folders TEXT")
    system_store.execute("UPDATE users_meta SET admin_enabled_folders = ? WHERE user_id = ?", (admin_enabled_folders, user_id))


def save_user_hidden_libraries(user_id: str, hidden_libraries: str) -> None:
    ensure_users_meta_column("hidden_libraries", "hidden_libraries TEXT DEFAULT ''")
    system_store.execute("UPDATE users_meta SET hidden_libraries = ? WHERE user_id = ?", (hidden_libraries, user_id))


def set_user_pinned(user_id: str, pinned: bool, created_at: str) -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT remark FROM users_meta WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        current_remark = row[0] if row and row[0] else ""

        has_pin = current_remark.startswith("[PINNED]")
        if pinned and not has_pin:
            new_remark = "[PINNED]" + current_remark
        elif not pinned and has_pin:
            new_remark = current_remark[8:]
        else:
            new_remark = current_remark

        if row:
            cursor.execute("UPDATE users_meta SET remark = ? WHERE user_id = ?", (new_remark, user_id))
        else:
            cursor.execute(
                "INSERT INTO users_meta (user_id, remark, created_at) VALUES (?, ?, ?)",
                (user_id, new_remark, created_at),
            )
        conn.commit()


def save_user_req_permission(user_id: str, req_free: int, req_free_count: int, created_at: str) -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM users_meta WHERE user_id = ?", (user_id,))
        exist = cursor.fetchone()
        if exist:
            cursor.execute(
                "UPDATE users_meta SET req_free = ?, req_free_count = ? WHERE user_id = ?",
                (req_free, req_free_count, user_id),
            )
        else:
            cursor.execute(
                "INSERT INTO users_meta (user_id, req_free, req_free_count, created_at) VALUES (?, ?, ?, ?)",
                (user_id, req_free, req_free_count, created_at),
            )
        conn.commit()


def get_user_req_permission(user_id: str) -> dict:
    row = system_store.fetch_one("SELECT req_free, req_free_count FROM users_meta WHERE user_id = ?", (user_id,))
    if row:
        return {
            "req_free": row["req_free"] or 0,
            "req_free_count": row["req_free_count"] if row["req_free_count"] is not None else -1,
        }
    return {"req_free": 0, "req_free_count": -1}


def list_users_with_expire_date():
    return system_store.fetch_all("SELECT user_id, expire_date FROM users_meta WHERE expire_date IS NOT NULL AND expire_date != ''")


def get_user_points_expire(user_id: str):
    return system_store.fetch_one("SELECT points, expire_date FROM users_meta WHERE user_id = ?", (user_id,))


def get_user_routes(user_id: str):
    return system_store.fetch_one("SELECT allow_routes, block_routes FROM users_meta WHERE user_id = ?", (user_id,))


def save_user_expire(user_id: str, expire_date: str) -> None:
    system_store.execute(
        "INSERT OR REPLACE INTO users_meta (user_id, expire_date, created_at) VALUES (?, ?, datetime('now','localtime'))",
        (user_id, expire_date),
    )


def save_user_expire_routes(user_id: str, expire_date: str, allow_routes: str, block_routes: str) -> None:
    system_store.execute(
        """
        INSERT OR REPLACE INTO users_meta
        (user_id, expire_date, allow_routes, block_routes, created_at)
        VALUES (?, ?, ?, ?, datetime('now','localtime'))
        """,
        (user_id, expire_date, allow_routes, block_routes),
    )


def list_user_tags():
    return system_store.fetch_all("SELECT id, name, color FROM user_tags ORDER BY name")


def create_user_tag(name: str, color: str) -> int:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO user_tags (name, color) VALUES (?, ?)", (name, color))
        except sqlite3.IntegrityError as exc:
            raise ValueError("duplicate") from exc
        conn.commit()
        return cursor.lastrowid


def delete_user_tag(tag_id: int) -> None:
    system_store.execute("DELETE FROM user_tags WHERE id = ?", (tag_id,))


def delete_user_tag_by_name(tag_name: str) -> bool:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        row = cursor.execute("SELECT id FROM user_tags WHERE name = ?", (tag_name,)).fetchone()
        if not row:
            return False

        tag_id = row[0]
        cursor.execute("DELETE FROM user_tags WHERE id = ?", (tag_id,))
        cursor.execute("SELECT user_id, tags FROM users_meta WHERE tags IS NOT NULL AND tags != ''")
        users_with_tags = cursor.fetchall()

        for user_id, user_tags in users_with_tags:
            tag_list = [tag.strip() for tag in user_tags.split(",") if tag.strip() and tag.strip() != tag_name]
            new_tags = ",".join(tag_list) if tag_list else ""
            cursor.execute("UPDATE users_meta SET tags = ? WHERE user_id = ?", (new_tags, user_id))

        conn.commit()
        return True


def save_user_tags(user_id: str, tags: str, created_at: str) -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM users_meta WHERE user_id = ?", (user_id,))
        exist = cursor.fetchone()
        if exist:
            cursor.execute("UPDATE users_meta SET tags = ? WHERE user_id = ?", (tags, user_id))
        else:
            cursor.execute(
                "INSERT INTO users_meta (user_id, tags, created_at) VALUES (?, ?, ?)",
                (user_id, tags, created_at),
            )
        conn.commit()


def get_user_tags(user_id: str) -> str:
    row = system_store.fetch_one("SELECT tags FROM users_meta WHERE user_id = ?", (user_id,))
    return row["tags"] if row and row["tags"] else ""
