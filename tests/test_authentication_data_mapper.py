import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://localhost/test")

import app.infrastructure.data_mapper as data_mapper_module
from app.application.domain import PrincipalType, Role
from app.application.exceptions import AuthenticationException
from app.infrastructure.data_mapper import AuthenticationDataMapper
from app.infrastructure.data_mapper.auth import verify_legacy_password


class FakeCursor:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows
        self.execute_params: list[tuple[Any, ...]] = []

    async def execute(self, query: object, params: tuple[Any, ...]) -> None:
        self.execute_params.append(params)

    async def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows


def _context_for(cursor: FakeCursor) -> Any:
    @asynccontextmanager
    async def context(connection_string: str) -> AsyncIterator[FakeCursor]:
        yield cursor

    return context


def test_verify_legacy_password_compares_credentials() -> None:
    assert verify_legacy_password("matching-credential", "matching-credential") is True
    assert verify_legacy_password("submitted-credential", "stored-credential") is False


@pytest.mark.anyio
async def test_authentication_data_mapper_authenticates_enabled_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = FakeCursor([(1, "admin-user", "stored-credential", "ADMIN", True)])
    monkeypatch.setattr(data_mapper_module, "get_cursor_context", _context_for(cursor))
    mapper = AuthenticationDataMapper("postgresql://unused")

    identity = await mapper.authenticate_internal_user(
        username="admin-user",
        password="stored-credential",
    )

    assert identity.id == 1
    assert identity.username == "admin-user"
    assert identity.role is Role.ADMIN
    assert identity.principal_type is PrincipalType.USER
    assert cursor.execute_params == [("admin-user",)]


@pytest.mark.anyio
async def test_authentication_data_mapper_authenticates_enabled_buyer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = FakeCursor([(2, "buyer-user", "stored-credential", "BUYER", True)])
    monkeypatch.setattr(data_mapper_module, "get_cursor_context", _context_for(cursor))
    mapper = AuthenticationDataMapper("postgresql://unused")

    identity = await mapper.authenticate_internal_user(
        username="buyer-user",
        password="stored-credential",
    )

    assert identity.id == 2
    assert identity.username == "buyer-user"
    assert identity.role is Role.BUYER
    assert identity.principal_type is PrincipalType.USER


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("rows", "submitted_credential"),
    [
        ([], "submitted-credential"),
        (
            [(1, "internal-user", "stored-credential", "ADMIN", True)],
            "wrong-credential",
        ),
        (
            [(1, "internal-user", "stored-credential", "ADMIN", False)],
            "stored-credential",
        ),
        (
            [(1, "internal-user", "stored-credential", "MANAGER", True)],
            "stored-credential",
        ),
        (
            [
                (1, "internal-user", "stored-credential", "ADMIN", True),
                (2, "internal-user", "stored-credential", "ADMIN", True),
            ],
            "stored-credential",
        ),
    ],
)
async def test_authentication_data_mapper_rejects_internal_user_failures_generically(
    monkeypatch: pytest.MonkeyPatch,
    rows: list[tuple[Any, ...]],
    submitted_credential: str,
) -> None:
    cursor = FakeCursor(rows)
    monkeypatch.setattr(data_mapper_module, "get_cursor_context", _context_for(cursor))
    mapper = AuthenticationDataMapper("postgresql://unused")

    with pytest.raises(AuthenticationException) as exc:
        await mapper.authenticate_internal_user(
            username="internal-user",
            password=submitted_credential,
        )

    assert str(exc.value) == "Invalid credentials"


@pytest.mark.anyio
async def test_authentication_data_mapper_does_not_return_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = FakeCursor([(1, "admin-user", "stored-credential", "ADMIN", True)])
    monkeypatch.setattr(data_mapper_module, "get_cursor_context", _context_for(cursor))
    mapper = AuthenticationDataMapper("postgresql://unused")

    identity = await mapper.authenticate_internal_user(
        username="admin-user",
        password="stored-credential",
    )

    assert not hasattr(identity, "password")
    assert not hasattr(identity, "stored_credential")
    assert not hasattr(identity, "access_token")
    assert "stored-credential" not in repr(identity)
