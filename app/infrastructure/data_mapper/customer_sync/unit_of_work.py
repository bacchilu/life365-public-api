"""One PostgreSQL transaction for a customer synchronization event."""

from collections.abc import Callable
from types import TracebackType
from typing import Self

import psycopg
from psycopg.rows import TupleRow

from app.application.exceptions import DBException
from app.application.ports import (
    CustomerResourceVersionGateway,
    CustomerSynchronizationGateway,
    CustomerSynchronizationUnitOfWork,
    ProcessedCustomerEventGateway,
)

from .events import PostgreSQLProcessedCustomerEventDataMapper
from .versions import PostgreSQLCustomerResourceVersionDataMapper

CustomerMapperFactory = Callable[
    [psycopg.AsyncCursor[TupleRow]], CustomerSynchronizationGateway
]


class PostgreSQLCustomerSynchronizationUnitOfWork(
    CustomerSynchronizationUnitOfWork
):
    def __init__(
        self,
        connection_string: str,
        fingerprint_secret: bytes,
        customer_mapper_factory: CustomerMapperFactory,
    ) -> None:
        if len(fingerprint_secret) < 32:
            raise ValueError("Event fingerprint secret must be at least 32 bytes")
        self._connection_string = connection_string
        self._fingerprint_secret = fingerprint_secret
        self._customer_mapper_factory = customer_mapper_factory
        self._connection: psycopg.AsyncConnection[TupleRow] | None = None
        self._cursor: psycopg.AsyncCursor[TupleRow] | None = None
        self._customers: CustomerSynchronizationGateway | None = None
        self._processed_events: ProcessedCustomerEventGateway | None = None
        self._resource_versions: CustomerResourceVersionGateway | None = None
        self._commit_requested = False

    @property
    def customers(self) -> CustomerSynchronizationGateway:
        if self._customers is None:
            raise RuntimeError("The unit of work has no active transaction")
        return self._customers

    @customers.setter
    def customers(self, gateway: CustomerSynchronizationGateway) -> None:
        self._customers = gateway

    @property
    def processed_events(self) -> ProcessedCustomerEventGateway:
        if self._processed_events is None:
            raise RuntimeError("The unit of work has no active transaction")
        return self._processed_events

    @processed_events.setter
    def processed_events(self, gateway: ProcessedCustomerEventGateway) -> None:
        self._processed_events = gateway

    @property
    def resource_versions(self) -> CustomerResourceVersionGateway:
        if self._resource_versions is None:
            raise RuntimeError("The unit of work has no active transaction")
        return self._resource_versions

    @resource_versions.setter
    def resource_versions(self, gateway: CustomerResourceVersionGateway) -> None:
        self._resource_versions = gateway

    async def __aenter__(self) -> Self:
        if self._connection is not None:
            raise RuntimeError("The unit of work already has an active transaction")

        try:
            connection = await psycopg.AsyncConnection.connect(
                self._connection_string, autocommit=False
            )
        except psycopg.Error as exc:
            raise DBException("Customer synchronization connection failed") from exc

        try:
            cursor = connection.cursor()
            customers = self._customer_mapper_factory(cursor)
            processed_events = PostgreSQLProcessedCustomerEventDataMapper(
                cursor, self._fingerprint_secret
            )
            resource_versions = PostgreSQLCustomerResourceVersionDataMapper(cursor)
        except BaseException:
            await connection.close()
            raise

        self._connection = connection
        self._cursor = cursor
        self.customers = customers
        self.processed_events = processed_events
        self.resource_versions = resource_versions
        self._commit_requested = False
        return self

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        connection = self._require_connection()
        cursor = self._cursor
        if cursor is None:
            raise RuntimeError("The unit of work has no active cursor")

        try:
            if exception is None and self._commit_requested:
                await connection.commit()
            else:
                await connection.rollback()
        except psycopg.Error as exc:
            raise DBException("Customer synchronization transaction failed") from exc
        finally:
            self._connection = None
            self._cursor = None
            self._customers = None
            self._processed_events = None
            self._resource_versions = None
            self._commit_requested = False
            try:
                await cursor.close()
            finally:
                await connection.close()

        if isinstance(exception, psycopg.Error):
            raise DBException("Customer synchronization query failed") from exception

    async def commit(self) -> None:
        self._require_connection()
        self._commit_requested = True

    async def rollback(self) -> None:
        connection = self._require_connection()
        try:
            await connection.rollback()
        except psycopg.Error as exc:
            raise DBException("Customer synchronization rollback failed") from exc
        self._commit_requested = False

    def _require_connection(self) -> psycopg.AsyncConnection[TupleRow]:
        if self._connection is None:
            raise RuntimeError("The unit of work has no active transaction")
        return self._connection
