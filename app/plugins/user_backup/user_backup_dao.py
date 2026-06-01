from app.dao.user_dao import get_user_meta, list_all_user_meta, upsert_user_meta_fields
from app.infra.db.system_store import system_store


def list_users_meta_for_backup():
    return list_all_user_meta()


def list_point_logs_for_backup(limit: int = 1000):
    return system_store.fetch_all(
        """
        SELECT id, user_id, username, action, amount, balance, created_at
        FROM point_logs
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    )


def list_tg_bindings_for_backup():
    return system_store.fetch_all("SELECT emby_user_id, tg_user_id FROM tg_user_bindings")


def list_tg_bindings_detail_for_backup():
    return system_store.fetch_all(
        "SELECT tg_user_id, emby_user_id, emby_username, bound_at FROM tg_user_bindings"
    )


def get_user_meta_for_backup(user_id: str):
    return get_user_meta(user_id)


def upsert_user_meta_for_backup(user_id: str, fields: dict, created_at: str) -> None:
    upsert_user_meta_fields(user_id, fields, created_at)


def replace_point_logs_for_backup(point_logs: list[dict]) -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM point_logs")
        for log in point_logs:
            cursor.execute(
                """
                INSERT INTO point_logs (id, user_id, username, action, amount, balance, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log.get("id"),
                    log.get("user_id"),
                    log.get("username"),
                    log.get("action"),
                    log.get("amount"),
                    log.get("balance"),
                    log.get("created_at"),
                ),
            )
        conn.commit()
