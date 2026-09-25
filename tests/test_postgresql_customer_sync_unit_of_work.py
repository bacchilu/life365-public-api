"""Offline tests for the PostgreSQL transaction boundary."""

from typing import cast

import psycopg
import pytest
from psycopg.rows import TupleRow

from app.application.exceptions import DBException
from app.application.ports import CustomerSynchronizationGateway
from app.infrastructure.data_mapper.customer_sync.unit_of_work import (
    PostgreSQLCustomerSynchronizationUnitOfWork,
)


class _FakeCursor:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _FakeConnection:
    def __init__(self) -> None:
        self.cursor_instance = _FakeCursor()
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
        self.commit_error: psycopg.Error | None = None

    def cursor(self) -> _FakeCursor:
        return self.cursor_instance

    async def commit(self) -> None:
        if self.commit_error is not None:
            raise self.commit_error
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def close(self) -> None:
        self.closed = True


def _unit_of_work(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[PostgreSQLCustomerSynchronizationUnitOfWork, _FakeConnection]:
    connection = _FakeConnection()

    async def connect(
        connection_string: str, *, autocommit: bool
    ) -> psycopg.AsyncConnection[TupleRow]:
        assert connection_string == "unused-test-connection"
        assert autocommit is False
        return cast(psycopg.AsyncConnection[TupleRow], connection)

    monkeypatch.setattr(psycopg.AsyncConnection, "connect", connect)
    work = PostgreSQLCustomerSynchronizationUnitOfWork(
        connection_string="unused-test-connection",
        fingerprint_secret=b"test-customer-sync-hmac-key-32-bytes",
        customer_mapper_factory=lambda cursor: cast(
            CustomerSynchronizationGateway, object()
        ),
    )
    return work, connection


@pytest.mark.anyio
async def test_commit_closes_the_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work, connection = _unit_of_work(monkeypatch)

    async with work:
        assert work.customers is not None
        assert work.processed_events is not None
        assert work.resource_versions is not None
        await work.commit()

    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert connection.cursor_instance.closed
    assert connection.closed
    with pytest.raises(RuntimeError, match="no active transaction"):
        _ = work.customers


@pytest.mark.anyio
async def test_exit_without_commit_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work, connection = _unit_of_work(monkeypatch)

    async with work:
        pass

    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.cursor_instance.closed
    assert connection.closed


@pytest.mark.anyio
async def test_exception_rolls_back_even_after_commit_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work, connection = _unit_of_work(monkeypatch)

    with pytest.raises(ValueError, match="stop"):
        async with work:
            await work.commit()
            raise ValueError("stop")

    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.cursor_instance.closed
    assert connection.closed


@pytest.mark.anyio
async def test_commit_failure_is_translated_and_closes_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work, connection = _unit_of_work(monkeypatch)
    connection.commit_error = psycopg.OperationalError("commit failed")

    with pytest.raises(DBException, match="transaction failed"):
        async with work:
            await work.commit()

    assert connection.cursor_instance.closed
    assert connection.closed
