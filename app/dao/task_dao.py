from app.infra.db.system_store import system_store


def ensure_task_config_defaults() -> None:
    system_store.execute("INSERT OR IGNORE INTO task_config (key, value) VALUES ('enable_notify', '1')")


def is_task_notify_enabled() -> bool:
    row = system_store.fetch_one("SELECT value FROM task_config WHERE key = 'enable_notify'")
    return row["value"] == "1" if row else True


def set_task_notify_enabled(enabled: bool) -> None:
    system_store.execute(
        "INSERT OR REPLACE INTO task_config (key, value) VALUES ('enable_notify', ?)",
        ("1" if enabled else "0",),
    )


def list_task_translations():
    return system_store.fetch_all("SELECT original_name, translated_name FROM task_translations")


def save_task_translation(original_name: str, translated_name: str) -> None:
    system_store.execute(
        "INSERT OR REPLACE INTO task_translations (original_name, translated_name) VALUES (?, ?)",
        (original_name, translated_name),
    )


def delete_task_translation(original_name: str) -> None:
    system_store.execute(
        "DELETE FROM task_translations WHERE original_name = ?",
        (original_name,),
    )
