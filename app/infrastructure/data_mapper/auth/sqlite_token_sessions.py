import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import cast

from app.application.domain import PrincipalType, TokenSession
from app.application.ports import TokenSessionGateway

_CREATE_TOKEN_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS token_sessions (
    token_id TEXT PRIMARY KEY,
    principal_id INTEGER NOT NULL,
    principal_type TEXT NOT NULL CHECK (principal_type IN ('user', 'customer')),
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0 CHECK (revoked IN (0, 1))
)
"""

_INSERT_TOKEN_SESSION = """
INSERT INTO token_sessions (token_id, principal_id, principal_type, issued_at, expires_at, revoked
) VALUES (:token_id, :principal_id, :principal_type, :issued_at, :expires_at, :revoked)
"""

_SELECT_TOKEN_SESSION = """
SELECT token_id, principal_id, principal_type, issued_at, expires_at, revoked FROM token_sessions WHERE token_id = :token_id
"""

_SELECT_TOKEN_EXISTS = """
SELECT 1 FROM token_sessions WHERE token_id = :token_id
"""

_SELECT_TOKEN_REVOKED = """
SELECT revoked FROM token_sessions WHERE token_id = :token_id
"""

_REVOKE_TOKEN = """
UPDATE token_sessions SET revoked = 1 WHERE token_id = :token_id
"""

_CONNECTION_TIMEOUT_SECONDS = 5.0

TokenSessionRow = tuple[str, int, str, str, str, int]


class SQLiteTokenSessionDataMapper(TokenSessionGateway):
    def __init__(self, database_path: str | Path) -> None:
        self._database_path = Path(database_path)

    async def initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)

        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(_CREATE_TOKEN_SESSIONS_TABLE)
            connection.commit()

    async def register_token_session(self, session: TokenSession) -> None:
        with self._connect() as connection:
            connection.execute(
                _INSERT_TOKEN_SESSION,
                {
                    "token_id": session.token_id,
                    "principal_id": session.principal_id,
                    "principal_type": session.principal_type.value,
                    "issued_at": session.issued_at.isoformat(),
                    "expires_at": session.expires_at.isoformat(),
                    "revoked": int(session.revoked),
                },
            )
            connection.commit()

    async def get_token_session(self, token_id: str) -> TokenSession | None:
        with self._connect() as connection:
            row: tuple[object, ...] | None = connection.execute(
                _SELECT_TOKEN_SESSION, {"token_id": token_id}
            ).fetchone()

        if row is None:
            return None

        (
            stored_token_id,
            principal_id,
            principal_type,
            issued_at,
            expires_at,
            revoked,
        ) = cast(TokenSessionRow, row)

        return TokenSession(
            token_id=stored_token_id,
            principal_id=principal_id,
            principal_type=PrincipalType(principal_type),
            issued_at=datetime.fromisoformat(issued_at),
            expires_at=datetime.fromisoformat(expires_at),
            revoked=bool(revoked),
        )

    async def is_token_known(self, token_id: str) -> bool:
        with self._connect() as connection:
            row: tuple[object, ...] | None = connection.execute(
                _SELECT_TOKEN_EXISTS, {"token_id": token_id}
            ).fetchone()

        return row is not None

    async def is_token_revoked(self, token_id: str) -> bool:
        with self._connect() as connection:
            row: tuple[object, ...] | None = connection.execute(
                _SELECT_TOKEN_REVOKED, {"token_id": token_id}
            ).fetchone()

        return row is not None and bool(row[0])

    async def revoke_token(self, token_id: str) -> None:
        with self._connect() as connection:
            connection.execute(_REVOKE_TOKEN, {"token_id": token_id})
            connection.commit()

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection]:
        connection = sqlite3.connect(
            self._database_path, timeout=_CONNECTION_TIMEOUT_SECONDS
        )
        connection.execute("PRAGMA busy_timeout = 5000")

        try:
            yield connection
        finally:
            connection.close()
