import os
import sqlite3
from contextlib import contextmanager

from app.core.config import SYSTEM_DB_PATH

from .row import to_data_row


class SystemStore:
    """Explicit access boundary for the EmbyPulse system database."""

    def __init__(self, db_path: str = SYSTEM_DB_PATH):
        self.db_path = db_path

    @contextmanager
    def connect(self, timeout: float = 20.0):
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        conn = sqlite3.connect(self.db_path, timeout=timeout)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def fetch_all(self, sql: str, params=()):
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            return [to_data_row(row) for row in cur.fetchall()]

    def fetch_one(self, sql: str, params=()):
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            return to_data_row(cur.fetchone())

    def execute(self, sql: str, params=()) -> int:
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            conn.commit()
            return cur.rowcount


system_store = SystemStore()
