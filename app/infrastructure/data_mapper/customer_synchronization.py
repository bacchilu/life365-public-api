"""In-memory persistence for Salesforce customer synchronization."""

from asyncio import Lock
from copy import deepcopy
from dataclasses import dataclass, field
from types import TracebackType
from typing import Self
from uuid import UUID

from app.application.dtos.customer_integration.customer import IntegrationCustomerData
from app.application.dtos.customer_integration.customer_patch import CustomerUpdatedData
from app.application.dtos.customer_integration.events import (
    CustomerIntegrationEvent,
    CustomerSynchronizationResult,
)
from app.application.exceptions import (
    CustomerNotFoundException,
    CustomerSynchronizationConflictException,
)
from app.application.ports import (
    CustomerResourceVersionGateway,
    CustomerSynchronizationGateway,
    CustomerSynchronizationUnitOfWork,
    ProcessedCustomerEventGateway,
)


@dataclass(slots=True)
class _Snapshot:
    customers: dict[int, IntegrationCustomerData] = field(default_factory=dict)
    updates: dict[int, list[CustomerUpdatedData]] = field(default_factory=dict)
    processed_events: dict[
        UUID,
        tuple[CustomerIntegrationEvent, CustomerSynchronizationResult],
    ] = field(default_factory=dict)
    resource_versions: dict[int, int] = field(default_factory=dict)
    next_reference_id: int = 1


@dataclass(slots=True)
class InMemoryCustomerSynchronizationStore:
    """Shared committed state for one or more in-memory units of work."""

    snapshot: _Snapshot = field(default_factory=_Snapshot)
    lock: Lock = field(default_factory=Lock)


class _CustomerGateway(CustomerSynchronizationGateway):
    def __init__(self, snapshot: _Snapshot) -> None:
        self._snapshot = snapshot

    async def customer_exists(self, reference_id: int) -> bool:
        return reference_id in self._snapshot.customers

    async def create_customer(self, data: IntegrationCustomerData) -> int:
        reference_id = self._snapshot.next_reference_id
        self._snapshot.next_reference_id += 1
        self._snapshot.customers[reference_id] = data
        return reference_id

    async def update_customer(
        self, reference_id: int, data: CustomerUpdatedData
    ) -> None:
        if reference_id not in self._snapshot.customers:
            raise CustomerNotFoundException(
                f"Customer {reference_id} does not exist"
            )
        self._snapshot.updates.setdefault(reference_id, []).append(data)


class _ProcessedEventGateway(ProcessedCustomerEventGateway):
    def __init__(self, snapshot: _Snapshot) -> None:
        self._snapshot = snapshot

    async def get_processed_result(
        self, event: CustomerIntegrationEvent
    ) -> CustomerSynchronizationResult | None:
        stored = self._snapshot.processed_events.get(event.event_id)
        if stored is None:
            return None
        stored_event, result = stored
        if stored_event != event:
            raise CustomerSynchronizationConflictException(
                f"Event id {event.event_id} has different content"
            )
        return result

    async def save_processed_result(
        self,
        event: CustomerIntegrationEvent,
        result: CustomerSynchronizationResult,
    ) -> None:
        stored = self._snapshot.processed_events.get(event.event_id)
        if stored is not None and stored[0] != event:
            raise CustomerSynchronizationConflictException(
                f"Event id {event.event_id} has different content"
            )
        self._snapshot.processed_events[event.event_id] = (event, result)


class _ResourceVersionGateway(CustomerResourceVersionGateway):
    def __init__(self, snapshot: _Snapshot) -> None:
        self._snapshot = snapshot

    async def get_resource_version(self, reference_id: int) -> int | None:
        return self._snapshot.resource_versions.get(reference_id)

    async def save_resource_version(
        self, reference_id: int, resource_version: int
    ) -> None:
        self._snapshot.resource_versions[reference_id] = resource_version


class InMemoryCustomerSynchronizationUnitOfWork(
    CustomerSynchronizationUnitOfWork
):
    def __init__(self, store: InMemoryCustomerSynchronizationStore) -> None:
        self._store = store
        self._snapshot = deepcopy(store.snapshot)
        self.customers: CustomerSynchronizationGateway = _CustomerGateway(
            self._snapshot
        )
        self.processed_events: ProcessedCustomerEventGateway = (
            _ProcessedEventGateway(self._snapshot)
        )
        self.resource_versions: CustomerResourceVersionGateway = (
            _ResourceVersionGateway(self._snapshot)
        )
        self._active = False

    async def __aenter__(self) -> Self:
        await self._store.lock.acquire()
        self._active = True
        self._replace_snapshot(deepcopy(self._store.snapshot))
        return self

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            if exception is not None:
                await self.rollback()
        finally:
            self._active = False
            self._store.lock.release()

    async def commit(self) -> None:
        self._require_active()
        self._store.snapshot = deepcopy(self._snapshot)

    async def rollback(self) -> None:
        self._require_active()
        self._replace_snapshot(deepcopy(self._store.snapshot))

    def _replace_snapshot(self, snapshot: _Snapshot) -> None:
        self._snapshot = snapshot
        self.customers = _CustomerGateway(snapshot)
        self.processed_events = _ProcessedEventGateway(snapshot)
        self.resource_versions = _ResourceVersionGateway(snapshot)

    def _require_active(self) -> None:
        if not self._active:
            raise RuntimeError("The unit of work has no active transaction")
