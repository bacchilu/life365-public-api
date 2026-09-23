"""In-memory persistence for Salesforce customer synchronization."""

from asyncio import Lock
from copy import deepcopy
from dataclasses import dataclass, field, fields, is_dataclass, replace
from types import TracebackType
from typing import Any, Self
from uuid import UUID

from app.application.dtos.customer_integration.address import IntegrationAddress
from app.application.dtos.customer_integration.address_patch import (
    IntegrationAddressPatch,
)
from app.application.dtos.customer_integration.commercial import (
    IntegrationSalesChannel,
)
from app.application.dtos.customer_integration.commercial_patch import (
    IntegrationSalesChannelPatch,
)
from app.application.dtos.customer_integration.customer import IntegrationCustomerData
from app.application.dtos.customer_integration.customer_patch import CustomerUpdatedData
from app.application.dtos.customer_integration.events import (
    CustomerIntegrationEvent,
    CustomerSynchronizationResult,
)
from app.application.dtos.customer_integration.operations_patch import (
    IntegrationCustomerExtensionsPatch,
)
from app.application.dtos.customer_integration.unset import UNSET
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


def _merge_json(existing: dict[str, Any] | None, patch: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(existing) if existing is not None else {}
    for key, value in patch.items():
        if value is None:
            merged.pop(key, None)
        elif isinstance(value, dict):
            current = merged.get(key)
            merged[key] = _merge_json(
                current if isinstance(current, dict) else None, value
            )
        else:
            merged[key] = deepcopy(value)
    return merged


def _create_nested_value(patch: Any) -> Any:
    if isinstance(patch, IntegrationAddressPatch):
        complete_type = IntegrationAddress
    elif isinstance(patch, IntegrationSalesChannelPatch):
        complete_type = IntegrationSalesChannel
    else:
        return deepcopy(patch)

    values = {field.name: getattr(patch, field.name) for field in fields(complete_type)}
    if any(value is UNSET for value in values.values()):
        raise CustomerSynchronizationConflictException(
            "A patch for a missing nested object must supply every field"
        )
    return complete_type(**values)


def _apply_patch(current: Any, patch: Any) -> Any:
    changes: dict[str, Any] = {}
    for patch_field in fields(patch):
        value = getattr(patch, patch_field.name)
        if value is UNSET:
            continue

        previous = getattr(current, patch_field.name)
        if isinstance(patch, IntegrationCustomerExtensionsPatch) and isinstance(
            value, dict
        ):
            value = _merge_json(previous, value)
        elif is_dataclass(value) and not isinstance(value, type):
            value = (
                _apply_patch(previous, value)
                if previous is not None and is_dataclass(previous)
                else _create_nested_value(value)
            )
        else:
            value = deepcopy(value)
        changes[patch_field.name] = value

    return replace(current, **changes)


class _CustomerGateway(CustomerSynchronizationGateway):
    def __init__(self, snapshot: _Snapshot) -> None:
        self._snapshot = snapshot

    async def customer_exists(self, reference_id: int) -> bool:
        return reference_id in self._snapshot.customers

    async def get_customer(
        self, reference_id: int
    ) -> IntegrationCustomerData | None:
        customer = self._snapshot.customers.get(reference_id)
        return deepcopy(customer) if customer is not None else None

    async def create_customer(self, data: IntegrationCustomerData) -> int:
        reference_id = self._snapshot.next_reference_id
        self._snapshot.next_reference_id += 1
        self._snapshot.customers[reference_id] = deepcopy(data)
        return reference_id

    async def update_customer(
        self, reference_id: int, data: CustomerUpdatedData
    ) -> None:
        current = self._snapshot.customers.get(reference_id)
        if current is None:
            raise CustomerNotFoundException(
                f"Customer {reference_id} does not exist"
            )
        self._snapshot.customers[reference_id] = _apply_patch(current, data)


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
        return deepcopy(result)

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
        self._snapshot.processed_events[event.event_id] = (
            deepcopy(event),
            deepcopy(result),
        )


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
        self._snapshot = _Snapshot()
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
        self._commit_requested = False

    async def __aenter__(self) -> Self:
        await self._store.lock.acquire()
        self._active = True
        self._commit_requested = False
        self._replace_snapshot(deepcopy(self._store.snapshot))
        return self

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            if exception is None and self._commit_requested:
                self._store.snapshot = deepcopy(self._snapshot)
        finally:
            self._active = False
            self._commit_requested = False
            self._store.lock.release()

    async def commit(self) -> None:
        self._require_active()
        self._commit_requested = True

    async def rollback(self) -> None:
        self._require_active()
        self._commit_requested = False
        self._replace_snapshot(deepcopy(self._store.snapshot))

    def _replace_snapshot(self, snapshot: _Snapshot) -> None:
        self._snapshot = snapshot
        self.customers = _CustomerGateway(snapshot)
        self.processed_events = _ProcessedEventGateway(snapshot)
        self.resource_versions = _ResourceVersionGateway(snapshot)

    def _require_active(self) -> None:
        if not self._active:
            raise RuntimeError("The unit of work has no active transaction")
