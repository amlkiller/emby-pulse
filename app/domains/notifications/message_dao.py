from app.infra.db.schema_bootstrap import ensure_registered_table
from app.infra.db.schema_registry import TABLE_SCHEMAS
from app.infra.db.system_store import system_store


MESSAGE_TABLES = ("msg_conversations", "msg_items", "msg_notify_block")
ANNOUNCEMENT_TABLES = ("announcements", "announcement_reads")


def ensure_msg_tables() -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        for table_name in MESSAGE_TABLES:
            cursor.execute(TABLE_SCHEMAS[table_name])
        conn.commit()


def list_user_remarks():
    return system_store.fetch_all("SELECT user_id, remark FROM users_meta WHERE remark IS NOT NULL AND remark != ''")


def get_local_user_profile_by_emby_id(user_id: str):
    return system_store.fetch_one("SELECT avatar, remark FROM local_users WHERE emby_user_id = ?", (user_id,))


def get_local_user_remark_by_emby_id(user_id: str):
    return system_store.fetch_one("SELECT remark FROM local_users WHERE emby_user_id = ?", (user_id,))


def get_user_meta_remark(user_id: str):
    return system_store.fetch_one("SELECT remark FROM users_meta WHERE user_id = ?", (user_id,))


def list_conversations(limit: int, offset: int):
    return system_store.fetch_all(
        """
        SELECT c.*,
               (SELECT COUNT(*) FROM msg_items WHERE conversation_id = c.id AND sender_type = 'user' AND created_at > COALESCE(
                   (SELECT created_at FROM msg_items WHERE conversation_id = c.id AND sender_type = 'admin' ORDER BY created_at DESC LIMIT 1), '1970-01-01'
               )) as new_replies
        FROM msg_conversations c
        ORDER BY c.last_time DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    )


def count_conversations() -> int:
    row = system_store.fetch_one("SELECT COUNT(*) as cnt FROM msg_conversations")
    return row["cnt"] if row else 0


def get_conversation_by_user(user_id: str):
    return system_store.fetch_one("SELECT * FROM msg_conversations WHERE user_id = ?", (user_id,))


def create_conversation(user_id: str, username: str, user_avatar=None) -> int:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO msg_conversations (user_id, username, user_avatar, created_at, last_time)
            VALUES (?, ?, ?, datetime('now','localtime'), datetime('now','localtime'))
            """,
            (user_id, username, user_avatar),
        )
        conn.commit()
        return cursor.lastrowid


def get_or_create_conversation(user_id: str, username: str, user_avatar=None):
    conversation = get_conversation_by_user(user_id)
    if conversation:
        return conversation["id"], dict(conversation)
    conversation_id = create_conversation(user_id, username, user_avatar)
    return conversation_id, {"id": conversation_id, "user_id": user_id, "username": username, "user_avatar": user_avatar}


def list_messages(conversation_id: int, limit: int, offset: int):
    return system_store.fetch_all(
        """
        SELECT * FROM msg_items
        WHERE conversation_id = ?
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """,
        (conversation_id, limit, offset),
    )


def mark_admin_read(conversation_id: int) -> None:
    system_store.execute("UPDATE msg_conversations SET unread_admin = 0 WHERE id = ?", (conversation_id,))


def mark_user_read(conversation_id: int) -> None:
    system_store.execute("UPDATE msg_conversations SET unread_user = 0 WHERE id = ?", (conversation_id,))


def insert_admin_message(conversation_id: int, sender_id: str, sender_name: str, content: str, last_message: str) -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO msg_items (conversation_id, sender_type, sender_id, sender_name, content, created_at)
            VALUES (?, 'admin', ?, ?, ?, datetime('now','localtime'))
            """,
            (conversation_id, sender_id, sender_name, content),
        )
        cursor.execute(
            """
            UPDATE msg_conversations SET last_message = ?, last_time = datetime('now','localtime'), unread_user = unread_user + 1
            WHERE id = ?
            """,
            (last_message, conversation_id),
        )
        conn.commit()


def count_admin_unread_conversations() -> int:
    row = system_store.fetch_one("SELECT COUNT(*) as cnt FROM msg_conversations WHERE unread_admin > 0")
    return row["cnt"] if row else 0


def get_user_messages(user_id: str, limit: int, offset: int):
    conversation = get_conversation_by_user(user_id)
    if not conversation:
        return None
    messages = list_messages(conversation["id"], limit, offset)
    mark_user_read(conversation["id"])
    return dict(conversation), messages


def get_local_user_avatar_by_emby_id(user_id: str):
    return system_store.fetch_one("SELECT avatar FROM local_users WHERE emby_user_id = ?", (user_id,))


def insert_user_message(user_id: str, username: str, user_avatar, content: str, last_message: str, notification_message: str) -> int:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM msg_conversations WHERE user_id = ?", (user_id,))
        conversation = cursor.fetchone()
        if not conversation:
            cursor.execute(
                """
                INSERT INTO msg_conversations (user_id, username, user_avatar, created_at, last_time)
                VALUES (?, ?, ?, datetime('now','localtime'), datetime('now','localtime'))
                """,
                (user_id, username, user_avatar),
            )
            conversation_id = cursor.lastrowid
        else:
            conversation_id = conversation[0]

        cursor.execute(
            """
            INSERT INTO msg_items (conversation_id, sender_type, sender_id, sender_name, content, created_at)
            VALUES (?, 'user', ?, ?, ?, datetime('now','localtime'))
            """,
            (conversation_id, user_id, username, content),
        )
        cursor.execute(
            """
            UPDATE msg_conversations SET last_message = ?, last_time = datetime('now','localtime'), unread_admin = unread_admin + 1
            WHERE id = ?
            """,
            (last_message, conversation_id),
        )
        try:
            cursor.execute("SELECT id FROM msg_notify_block WHERE user_id = ?", (user_id,))
            if not cursor.fetchone():
                cursor.execute(
                    """
                    INSERT INTO sys_notifications (type, title, message, action_url, created_at)
                    VALUES ('message', ?, ?, ?, datetime('now','localtime'))
                    """,
                    ("新消息", notification_message, f"/messages?user={user_id}"),
                )
        except Exception:
            pass
        conn.commit()
        return conversation_id


def get_user_unread_count(user_id: str) -> int:
    row = system_store.fetch_one("SELECT unread_user FROM msg_conversations WHERE user_id = ?", (user_id,))
    return row["unread_user"] if row else 0


def list_notify_blocks():
    return system_store.fetch_all(
        """
        SELECT b.id, b.user_id, c.username, c.user_avatar, b.created_at
        FROM msg_notify_block b
        LEFT JOIN msg_conversations c ON b.user_id = c.user_id
        ORDER BY b.created_at DESC
        """
    )


def is_notify_blocked(user_id: str) -> bool:
    return system_store.fetch_one("SELECT id FROM msg_notify_block WHERE user_id = ?", (user_id,)) is not None


def add_notify_block(user_id: str) -> bool:
    if is_notify_blocked(user_id):
        return False
    system_store.execute("INSERT INTO msg_notify_block (user_id) VALUES (?)", (user_id,))
    return True


def remove_notify_block(user_id: str) -> None:
    system_store.execute("DELETE FROM msg_notify_block WHERE user_id = ?", (user_id,))


def ensure_mute_table() -> None:
    with system_store.connect() as conn:
        conn.execute(TABLE_SCHEMAS["user_mutes"])
        conn.commit()


def get_active_mute(user_id: str):
    return system_store.fetch_one("SELECT * FROM user_mutes WHERE user_id = ? AND is_muted = 1", (user_id,))


def set_user_unmuted(user_id: str) -> None:
    system_store.execute("UPDATE user_mutes SET is_muted = 0 WHERE user_id = ?", (user_id,))


def list_active_mutes(limit: int, offset: int):
    return system_store.fetch_all(
        """
        SELECT * FROM user_mutes
        WHERE is_muted = 1
        ORDER BY muted_at DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    )


def count_active_mutes() -> int:
    row = system_store.fetch_one("SELECT COUNT(*) as cnt FROM user_mutes WHERE is_muted = 1")
    return row["cnt"] if row else 0


def upsert_user_mute(user_id: str, username: str, muted_until, reason: str, admin_id: str, admin_name: str) -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM user_mutes WHERE user_id = ?", (user_id,))
        if cursor.fetchone():
            cursor.execute(
                """
                UPDATE user_mutes SET
                    is_muted = 1,
                    username = ?,
                    muted_until = ?,
                    muted_reason = ?,
                    muted_by = ?,
                    muted_by_name = ?,
                    muted_at = datetime('now','localtime')
                WHERE user_id = ?
                """,
                (username, muted_until, reason, admin_id, admin_name, user_id),
            )
        else:
            cursor.execute(
                """
                INSERT INTO user_mutes (user_id, username, is_muted, muted_until, muted_reason, muted_by, muted_by_name, muted_at)
                VALUES (?, ?, 1, ?, ?, ?, ?, datetime('now','localtime'))
                """,
                (user_id, username, muted_until, reason, admin_id, admin_name),
            )
        conn.commit()


def set_users_unmuted(user_ids) -> None:
    if not user_ids:
        return
    placeholders = ",".join(["?" for _ in user_ids])
    system_store.execute(f"UPDATE user_mutes SET is_muted = 0 WHERE user_id IN ({placeholders})", user_ids)


def ensure_announcement_tables() -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        for table_name in ANNOUNCEMENT_TABLES:
            ensure_registered_table(cursor, table_name)
        conn.commit()


def list_announcements(active_only: bool = False):
    if active_only:
        return system_store.fetch_all(
            """
            SELECT * FROM announcements
            WHERE is_active = 1
            ORDER BY priority DESC, created_at DESC
            """
        )
    return system_store.fetch_all(
        """
        SELECT * FROM announcements
        ORDER BY is_active DESC, priority DESC, created_at DESC
        """
    )


def create_announcement(title: str, content: str, is_active: bool, priority: int, admin_id: str, admin_name: str) -> int:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO announcements (title, content, is_active, priority, created_by, created_by_name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now','localtime'), datetime('now','localtime'))
            """,
            (title, content, 1 if is_active else 0, priority, admin_id, admin_name),
        )
        conn.commit()
        return cursor.lastrowid


def update_announcement_fields(announcement_id: int, updates: dict) -> None:
    allowed_fields = {"title", "content", "is_active", "priority"}
    invalid_fields = set(updates) - allowed_fields
    if invalid_fields:
        raise ValueError(f"Unsupported announcement update fields: {', '.join(sorted(invalid_fields))}")
    values = dict(updates)
    assignments = ", ".join([f"{field} = ?" for field in values.keys()])
    params = list(values.values()) + [announcement_id]
    system_store.execute(f"UPDATE announcements SET {assignments}, updated_at = datetime('now','localtime') WHERE id = ?", params)


def delete_announcement_by_id(announcement_id: int) -> None:
    system_store.execute("DELETE FROM announcements WHERE id = ?", (announcement_id,))


def increment_announcement_view_count(announcement_id: int) -> None:
    system_store.execute("UPDATE announcements SET view_count = view_count + 1 WHERE id = ?", (announcement_id,))


def list_active_announcements_with_reads(user_id: str):
    with system_store.connect() as conn:
        conn.row_factory = None
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, title, content, view_count, created_at
            FROM announcements
            WHERE is_active = 1
            ORDER BY priority DESC, created_at DESC
            """
        )
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        cursor.execute("SELECT announcement_id FROM announcement_reads WHERE user_id = ?", (user_id,))
        read_ids = {row[0] for row in cursor.fetchall()}

    announcements = []
    for row in rows:
        announcement = dict(zip(columns, row))
        announcement["is_new"] = announcement["id"] not in read_ids
        announcements.append(announcement)
    return announcements


def mark_announcement_read(announcement_id: int, user_id: str) -> None:
    system_store.execute(
        """
        INSERT OR IGNORE INTO announcement_reads (announcement_id, user_id, read_at)
        VALUES (?, ?, datetime('now','localtime'))
        """,
        (announcement_id, user_id),
    )


def get_user_tg_id(user_id: str):
    return system_store.fetch_one("SELECT tg_id FROM tg_bot_users WHERE emby_user_id = ?", (user_id,))


def delete_conversation_by_user(user_id: str) -> bool:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM msg_conversations WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            return False
        conversation_id = row[0]
        cursor.execute("DELETE FROM msg_items WHERE conversation_id = ?", (conversation_id,))
        cursor.execute("DELETE FROM msg_conversations WHERE id = ?", (conversation_id,))
        conn.commit()
        return True


def delete_all_conversations() -> None:
    with system_store.connect() as conn:
        conn.execute("DELETE FROM msg_items")
        conn.execute("DELETE FROM msg_conversations")
        conn.commit()


def send_broadcast_messages(user_entries, admin_id: str, admin_name: str, content: str):
    success_count = 0
    failed = []
    with system_store.connect() as conn:
        cursor = conn.cursor()
        for user_id, username in user_entries:
            try:
                cursor.execute("SELECT id FROM msg_conversations WHERE user_id = ?", (user_id,))
                conversation = cursor.fetchone()
                if not conversation:
                    cursor.execute(
                        """
                        INSERT INTO msg_conversations (user_id, username, user_avatar, created_at, last_time)
                        VALUES (?, ?, '', datetime('now','localtime'), datetime('now','localtime'))
                        """,
                        (user_id, username),
                    )
                    conversation_id = cursor.lastrowid
                else:
                    conversation_id = conversation[0]

                cursor.execute(
                    """
                    INSERT INTO msg_items (conversation_id, sender_type, sender_id, sender_name, content, created_at)
                    VALUES (?, 'admin', ?, ?, ?, datetime('now','localtime'))
                    """,
                    (conversation_id, admin_id, admin_name, content),
                )
                cursor.execute(
                    """
                    UPDATE msg_conversations
                    SET last_message = ?, last_time = datetime('now','localtime'), unread_user = unread_user + 1
                    WHERE id = ?
                    """,
                    (content[:100], conversation_id),
                )
                success_count += 1
            except Exception as exc:
                failed.append((user_id, exc))
        conn.commit()
    return success_count, failed
