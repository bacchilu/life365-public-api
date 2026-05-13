import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://localhost/test")

import app.infrastructure.data_mapper as data_mapper_root
import app.infrastructure.data_mapper.auth as auth_mapper_module
from app.application.domain import PrincipalType, Role, TokenSession
from app.application.exceptions import AuthenticationException
from app.infrastructure.data_mapper import AuthenticationDataMapper
from app.infrastructure.data_mapper.auth import (
    AuthenticationDataMapper as AuthDataMapper,
)
from app.infrastructure.data_mapper.auth import verify_legacy_password
from app.infrastructure.data_mapper.auth.customer import CUSTOMER_COLUMNS


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


def test_data_mapper_root_exports_authentication_data_mapper() -> None:
    assert data_mapper_root.AuthenticationDataMapper is AuthenticationDataMapper
    assert data_mapper_root.AuthenticationDataMapper is AuthDataMapper


def test_customer_authentication_columns_do_not_include_verified() -> None:
    assert CUSTOMER_COLUMNS == ("id", "login", "pass")
    assert "verified" not in CUSTOMER_COLUMNS


@pytest.mark.anyio
async def test_authentication_data_mapper_stores_token_sessions_in_memory() -> None:
    mapper = AuthenticationDataMapper("postgresql://unused")
    issued_at = datetime.now(timezone.utc)
    session = TokenSession(
        token_id="token-id",
        principal_id=1,
        principal_type=PrincipalType.USER,
        issued_at=issued_at,
        expires_at=issued_at + timedelta(days=30),
    )

    await mapper.register_token_session(session)

    assert await mapper.get_token_session("token-id") == session
    assert await mapper.is_token_known("token-id") is True
    assert await mapper.is_token_known("unknown-token-id") is False
    assert await mapper.is_token_revoked("token-id") is False


@pytest.mark.anyio
async def test_authentication_data_mapper_authenticates_enabled_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = FakeCursor([(1, "admin-user", "stored-credential", "ADMIN", True)])
    monkeypatch.setattr(auth_mapper_module, "get_cursor_context", _context_for(cursor))
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
    monkeypatch.setattr(auth_mapper_module, "get_cursor_context", _context_for(cursor))
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
async def test_authentication_data_mapper_authenticates_customer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = FakeCursor([(3, "customer-login", "stored-credential")])
    monkeypatch.setattr(auth_mapper_module, "get_cursor_context", _context_for(cursor))
    mapper = AuthenticationDataMapper("postgresql://unused")

    identity = await mapper.authenticate_customer(
        username="customer-login",
        password="stored-credential",
    )

    assert identity.id == 3
    assert identity.username == "customer-login"
    assert identity.role is Role.CUSTOMER
    assert identity.principal_type is PrincipalType.CUSTOMER
    assert cursor.execute_params == [("customer-login",)]


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
    monkeypatch.setattr(auth_mapper_module, "get_cursor_context", _context_for(cursor))
    mapper = AuthenticationDataMapper("postgresql://unused")

    with pytest.raises(AuthenticationException) as exc:
        await mapper.authenticate_internal_user(
            username="internal-user",
            password=submitted_credential,
        )

    assert str(exc.value) == "Invalid credentials"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method_name", "rows", "username"),
    [
        (
            "authenticate_internal_user",
            [(1, "admin-user", "stored-credential", "ADMIN", True)],
            "admin-user",
        ),
        (
            "authenticate_customer",
            [(3, "customer-login", "stored-credential")],
            "customer-login",
        ),
    ],
)
async def test_authentication_data_mapper_does_not_return_credentials(
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
    rows: list[tuple[Any, ...]],
    username: str,
) -> None:
    cursor = FakeCursor(rows)
    monkeypatch.setattr(auth_mapper_module, "get_cursor_context", _context_for(cursor))
    mapper = AuthenticationDataMapper("postgresql://unused")
    authenticate = getattr(mapper, method_name)

    identity = await authenticate(
        username=username,
        password="stored-credential",
    )

    assert not hasattr(identity, "password")
    assert not hasattr(identity, "stored_credential")
    assert not hasattr(identity, "access_token")
    assert "stored-credential" not in repr(identity)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("rows", "submitted_credential"),
    [
        ([], "submitted-credential"),
        (
            [(3, "customer-login", "stored-credential")],
            "wrong-credential",
        ),
        (
            [
                (3, "customer-login", "stored-credential"),
                (4, "customer-login", "stored-credential"),
            ],
            "stored-credential",
        ),
    ],
)
async def test_authentication_data_mapper_rejects_customer_failures_generically(
    monkeypatch: pytest.MonkeyPatch,
    rows: list[tuple[Any, ...]],
    submitted_credential: str,
) -> None:
    cursor = FakeCursor(rows)
    monkeypatch.setattr(auth_mapper_module, "get_cursor_context", _context_for(cursor))
    mapper = AuthenticationDataMapper("postgresql://unused")

    with pytest.raises(AuthenticationException) as exc:
        await mapper.authenticate_customer(
            username="customer-login",
            password=submitted_credential,
        )

    assert str(exc.value) == "Invalid credentials"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method_name", "rows", "username"),
    [
        (
            "authenticate_internal_user",
            [(1, "internal-user", "stored-credential", "ADMIN")],
            "internal-user",
        ),
        (
            "authenticate_customer",
            [(3, "customer-login")],
            "customer-login",
        ),
    ],
)
async def test_authentication_data_mapper_rejects_malformed_rows_generically(
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
    rows: list[tuple[Any, ...]],
    username: str,
) -> None:
    cursor = FakeCursor(rows)
    monkeypatch.setattr(auth_mapper_module, "get_cursor_context", _context_for(cursor))
    mapper = AuthenticationDataMapper("postgresql://unused")
    authenticate = getattr(mapper, method_name)

    with pytest.raises(AuthenticationException) as exc:
        await authenticate(username=username, password="stored-credential")

    assert str(exc.value) == "Invalid credentials"


@pytest.mark.anyio
async def test_authentication_data_mapper_uses_same_generic_failure_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mapper = AuthenticationDataMapper("postgresql://unused")
    cases = [
        (
            "authenticate_internal_user",
            [],
            "internal-user",
            "submitted-credential",
        ),
        (
            "authenticate_internal_user",
            [(1, "internal-user", "stored-credential", "ADMIN", True)],
            "internal-user",
            "wrong-credential",
        ),
        (
            "authenticate_customer",
            [],
            "customer-login",
            "submitted-credential",
        ),
        (
            "authenticate_customer",
            [(3, "customer-login", "stored-credential")],
            "customer-login",
            "wrong-credential",
        ),
    ]
    messages: list[str] = []

    for method_name, rows, username, submitted_credential in cases:
        cursor = FakeCursor(rows)
        monkeypatch.setattr(
            auth_mapper_module,
            "get_cursor_context",
            _context_for(cursor),
        )
        authenticate = getattr(mapper, method_name)

        with pytest.raises(AuthenticationException) as exc:
            await authenticate(username=username, password=submitted_credential)

        messages.append(str(exc.value))

    assert messages == ["Invalid credentials"] * len(cases)
