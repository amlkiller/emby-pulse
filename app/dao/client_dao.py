from app.infra.db.system_store import system_store


def list_client_blacklist():
    return system_store.fetch_all("SELECT * FROM client_blacklist ORDER BY created_at DESC")


def list_client_blacklist_names():
    return system_store.fetch_all("SELECT app_name FROM client_blacklist")


def add_client_blacklist(app_name: str) -> None:
    system_store.execute("INSERT INTO client_blacklist (app_name) VALUES (?)", (app_name,))


def delete_client_blacklist(app_name: str) -> None:
    system_store.execute("DELETE FROM client_blacklist WHERE app_name = ?", (app_name,))


def list_client_whitelist():
    return system_store.fetch_all("SELECT * FROM client_whitelist ORDER BY created_at DESC")


def list_client_whitelist_user_ids():
    return system_store.fetch_all("SELECT user_id FROM client_whitelist")


def add_client_whitelist(user_id: str, user_name: str) -> None:
    system_store.execute(
        "INSERT INTO client_whitelist (user_id, user_name) VALUES (?, ?)",
        (user_id, user_name),
    )


def delete_client_whitelist(user_id: str) -> None:
    system_store.execute("DELETE FROM client_whitelist WHERE user_id = ?", (user_id,))
