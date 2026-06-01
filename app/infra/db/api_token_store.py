from app.infra.db.system_store import system_store


def create_api_token_record(user_id: str, token_hash: str, name: str, expires_at: str, created_at: str) -> None:
    system_store.execute(
        """
        INSERT INTO api_tokens (user_id, token, name, expires_at, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, token_hash, name, expires_at, created_at),
    )


def list_api_tokens(user_id: str):
    rows = system_store.fetch_all(
        """
        SELECT id, name, expires_at, created_at, last_used_at
        FROM api_tokens
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (user_id,),
    )
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "expires_at": row["expires_at"],
            "created_at": row["created_at"],
            "last_used_at": row["last_used_at"],
        }
        for row in rows
    ]


def delete_api_token(token_id: int, user_id: str) -> None:
    system_store.execute(
        "DELETE FROM api_tokens WHERE id = ? AND user_id = ?",
        (token_id, user_id),
    )


def mark_api_token_used(token_hash: str) -> None:
    system_store.execute(
        """
        UPDATE api_tokens
        SET last_used_at = datetime('now')
        WHERE token = ?
        """,
        (token_hash,),
    )


def get_api_token_by_hash(token_hash: str):
    return system_store.fetch_one(
        "SELECT expires_at FROM api_tokens WHERE token = ?",
        (token_hash,),
    )
