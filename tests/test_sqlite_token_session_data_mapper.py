import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.application.domain import PrincipalType, TokenSession
from app.infrastructure.data_mapper import SQLiteTokenSessionDataMapper


def _token_session(
    token_id: str = "token-id",
    principal_type: PrincipalType = PrincipalType.USER,
) -> TokenSession:
    issued_at = datetime.now(timezone.utc)
    return TokenSession(
        token_id=token_id,
        principal_id=123,
        principal_type=principal_type,
        issued_at=issued_at,
        expires_at=issued_at + timedelta(days=30),
    )


@pytest.mark.anyio
async def test_initialize_creates_token_sessions_table(tmp_path: Path) -> None:
    database_path = tmp_path / "sessions" / "token-sessions.sqlite3"
    mapper = SQLiteTokenSessionDataMapper(database_path)

    await mapper.initialize()
    await mapper.initialize()

    with closing(sqlite3.connect(database_path)) as connection:
        row = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'token_sessions'
            """
        ).fetchone()

    assert row == ("token_sessions",)


@pytest.mark.anyio
async def test_mapper_registers_and_reads_token_session(tmp_path: Path) -> None:
    database_path = tmp_path / "token-sessions.sqlite3"
    mapper = SQLiteTokenSessionDataMapper(database_path)
    session = _token_session(principal_type=PrincipalType.CUSTOMER)

    await mapper.initialize()
    await mapper.register_token_session(session)

    assert await mapper.get_token_session(session.token_id) == session
    assert await mapper.is_token_known(session.token_id) is True
    assert await mapper.is_token_known("unknown-token-id") is False
    assert await mapper.is_token_revoked(session.token_id) is False


@pytest.mark.anyio
async def test_mapper_persists_sessions_between_instances(tmp_path: Path) -> None:
    database_path = tmp_path / "token-sessions.sqlite3"
    first_mapper = SQLiteTokenSessionDataMapper(database_path)
    session = _token_session()

    await first_mapper.initialize()
    await first_mapper.register_token_session(session)

    second_mapper = SQLiteTokenSessionDataMapper(database_path)
    await second_mapper.initialize()

    assert await second_mapper.get_token_session(session.token_id) == session


@pytest.mark.anyio
async def test_mapper_persists_token_revocation(tmp_path: Path) -> None:
    database_path = tmp_path / "token-sessions.sqlite3"
    mapper = SQLiteTokenSessionDataMapper(database_path)
    session = _token_session()

    await mapper.initialize()
    await mapper.register_token_session(session)
    await mapper.revoke_token(session.token_id)

    revoked_session = await mapper.get_token_session(session.token_id)

    assert await mapper.is_token_revoked(session.token_id) is True
    assert revoked_session is not None
    assert revoked_session.revoked is True

    reloaded_mapper = SQLiteTokenSessionDataMapper(database_path)

    assert await reloaded_mapper.is_token_revoked(session.token_id) is True
