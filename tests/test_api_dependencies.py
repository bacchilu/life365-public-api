from pathlib import Path

import pytest

from app.api import dependencies
from app.infrastructure.data_mapper.auth import (
    InMemoryTokenSessionDataMapper,
    SQLiteTokenSessionDataMapper,
)


@pytest.mark.anyio
async def test_token_session_gateway_factory_creates_in_memory_mapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        dependencies, "TOKEN_SESSION_BACKEND", dependencies.TokenSessionBackend.MEMORY
    )

    gateway = await dependencies._create_token_session_gateway()

    assert isinstance(gateway, InMemoryTokenSessionDataMapper)


@pytest.mark.anyio
async def test_token_session_gateway_factory_initializes_sqlite_mapper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "token-sessions.sqlite3"
    monkeypatch.setattr(
        dependencies, "TOKEN_SESSION_BACKEND", dependencies.TokenSessionBackend.SQLITE
    )
    monkeypatch.setattr(
        dependencies, "SQLITE_TOKEN_SESSION_DATABASE_PATH", database_path
    )

    gateway = await dependencies._create_token_session_gateway()

    assert isinstance(gateway, SQLiteTokenSessionDataMapper)
    assert database_path.is_file()
    assert await gateway.is_token_known("unknown-token-id") is False
