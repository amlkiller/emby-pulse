import json

from app.infra.db.system_store import system_store


def ensure_notify_rules_table() -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS notify_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                notify_type TEXT UNIQUE NOT NULL,
                notify_name TEXT NOT NULL,
                channels TEXT DEFAULT '[]',
                enabled INTEGER DEFAULT 1,
                config TEXT DEFAULT '{}',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        conn.commit()


def get_notify_rule_row(notify_type: str):
    return system_store.fetch_one(
        "SELECT * FROM notify_rules WHERE notify_type = ?",
        (notify_type,),
    )


def list_notify_rule_rows():
    return system_store.fetch_all("SELECT * FROM notify_rules")


def save_notify_rules(rules: dict) -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()

        for notify_type, rule in rules.items():
            channels_json = json.dumps(rule.get("channels", []))
            config_json = json.dumps(rule.get("config", {}))
            enabled = 1 if rule.get("enabled", False) else 0
            notify_name = rule.get("notify_name", notify_type)

            cursor.execute(
                """
                INSERT OR REPLACE INTO notify_rules
                (notify_type, notify_name, channels, enabled, config, updated_at)
                VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'))
                """,
                (notify_type, notify_name, channels_json, enabled, config_json),
            )

        conn.commit()
