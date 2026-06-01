from app.infra.db.schema_bootstrap import ensure_registered_table
from app.infra.db.system_store import system_store


def ensure_pwa_config_table() -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        ensure_registered_table(cursor, "pwa_config")
        conn.commit()


def get_pwa_config_values() -> dict:
    ensure_pwa_config_table()
    rows = system_store.fetch_all("SELECT key, value FROM pwa_config")
    return {row["key"]: row["value"] for row in rows}


def save_pwa_config_value(key: str, value: str) -> None:
    ensure_pwa_config_table()
    system_store.execute(
        "INSERT OR REPLACE INTO pwa_config (key, value) VALUES (?, ?)",
        (key, value),
    )


def ensure_user_pwa_icons_table() -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        ensure_registered_table(cursor, "user_pwa_icons")
        conn.commit()


def get_user_pwa_icon(user_id: str):
    ensure_user_pwa_icons_table()
    row = system_store.fetch_one(
        "SELECT icon_id FROM user_pwa_icons WHERE user_id = ?",
        (user_id,),
    )
    return row["icon_id"] if row else None


def set_user_pwa_icon(user_id: str, icon_id: str) -> None:
    ensure_user_pwa_icons_table()
    system_store.execute(
        "INSERT OR REPLACE INTO user_pwa_icons (user_id, icon_id) VALUES (?, ?)",
        (user_id, icon_id),
    )
