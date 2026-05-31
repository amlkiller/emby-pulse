from app.infra.db.system_store import system_store


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


def list_user_tags():
    return system_store.fetch_all("SELECT id, name, color FROM user_tags ORDER BY name")


def create_user_tag(name: str, color: str) -> int:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO user_tags (name, color) VALUES (?, ?)", (name, color))
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
