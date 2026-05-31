from app.infra.db.system_store import system_store


def save_insight_ignore(item_id: str, item_name: str) -> None:
    system_store.execute(
        "INSERT OR REPLACE INTO insight_ignores (item_id, item_name) VALUES (?, ?)",
        (item_id, item_name),
    )


def save_insight_ignores(items) -> None:
    records = [(item.item_id, item.item_name) for item in items]
    if not records:
        return

    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.executemany(
            "INSERT OR REPLACE INTO insight_ignores (item_id, item_name) VALUES (?, ?)",
            records,
        )
        conn.commit()


def delete_insight_ignores(item_ids) -> None:
    if not item_ids:
        return
    placeholders = ",".join(["?"] * len(item_ids))
    system_store.execute(
        f"DELETE FROM insight_ignores WHERE item_id IN ({placeholders})",
        item_ids,
    )


def list_insight_ignores():
    return system_store.fetch_all("SELECT * FROM insight_ignores ORDER BY ignored_at DESC")


def list_insight_ignore_item_ids():
    return system_store.fetch_all("SELECT item_id FROM insight_ignores")
