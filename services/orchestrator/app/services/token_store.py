from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT_DB_PATH = Path(os.getenv("OAUTH_DB_PATH", "app/oauth.db")).resolve()


@dataclass
class OAuthToken:
    provider: str
    account: str
    token: Dict[str, Any]


class OAuthTokenStore:
    """
    Simple SQLite-backed store for OAuth tokens with upsert semantics.
    Unique key is (provider, account).
    """

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS oauth_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    account TEXT NOT NULL,
                    token_json TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(provider, account)
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_oauth_provider ON oauth_tokens(provider)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_oauth_account ON oauth_tokens(account)")
            con.commit()

    def load(self, provider: str, account: str) -> Optional[Dict[str, Any]]:
        with self._connect() as con:
            row = con.execute(
                "SELECT token_json FROM oauth_tokens WHERE provider=? AND account=?",
                (provider, account),
            ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row["token_json"])  # type: ignore[index]
        except Exception:
            return None

    def save(self, provider: str, account: str, token: Dict[str, Any]) -> None:
        token_json = json.dumps(token)
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO oauth_tokens (provider, account, token_json)
                VALUES (?, ?, ?)
                ON CONFLICT(provider, account)
                DO UPDATE SET token_json=excluded.token_json, updated_at=CURRENT_TIMESTAMP
                """,
                (provider, account, token_json),
            )
            con.commit() 