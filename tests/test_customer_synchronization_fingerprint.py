from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from app.application.dtos.customer_integration.commercial_patch import (
    IntegrationCommercialPatch,
)
from app.application.dtos.customer_integration.customer_patch import CustomerUpdatedData
from app.application.dtos.customer_integration.events import CustomerUpdatedEvent
from app.application.dtos.customer_integration.operations_patch import (
    IntegrationCustomerExtensionsPatch,
    IntegrationCustomerNotesPatch,
)
from app.application.dtos.customer_integration.profile_patch import (
    IntegrationCommunicationPreferencesPatch,
    IntegrationCompanyPatch,
    IntegrationCustomerCredentialsPatch,
)
from app.infrastructure.data_mapper.customer_sync.fingerprint import event_fingerprint

_KEY = b"test-event-fingerprint-key-32-bytes"


def _event(data: CustomerUpdatedData | None = None) -> CustomerUpdatedEvent:
    return CustomerUpdatedEvent(
        schema_version=1,
        event_id=UUID(int=1),
        occurred_at=datetime(2026, 9, 25, 10, 0, tzinfo=UTC),
        resource_version=2,
        reference_id=42,
        data=data if data is not None else CustomerUpdatedData(),
    )


def test_same_event_has_the_same_32_byte_fingerprint() -> None:
    event = _event()

    first = event_fingerprint(event, _KEY)

    assert isinstance(first, bytes)
    assert len(first) == 32
    assert first == event_fingerprint(event, _KEY)


@pytest.mark.parametrize(
    "patch",
    [
        CustomerUpdatedData(company=IntegrationCompanyPatch(website=None)),
        CustomerUpdatedData(company=IntegrationCompanyPatch(website="")),
        CustomerUpdatedData(
            communication_preferences=IntegrationCommunicationPreferencesPatch(
                newsletter=False
            )
        ),
        CustomerUpdatedData(commercial=IntegrationCommercialPatch(payment_days=0)),
        CustomerUpdatedData(notes=IntegrationCustomerNotesPatch(items=())),
    ],
)
def test_supplied_update_values_differ_from_omitted_values(
    patch: CustomerUpdatedData,
) -> None:
    assert event_fingerprint(_event(patch), _KEY) != event_fingerprint(
        _event(), _KEY
    )


def test_json_map_order_and_equal_numbers_do_not_change_the_fingerprint() -> None:
    first = CustomerUpdatedData(
        extensions=IntegrationCustomerExtensionsPatch(
            parameters={"outer": {"a": 1, "b": Decimal("2.00")}, "flag": True}
        )
    )
    second = CustomerUpdatedData(
        extensions=IntegrationCustomerExtensionsPatch(
            parameters={"flag": True, "outer": {"b": 2.0, "a": 1.0}}
        )
    )

    assert event_fingerprint(_event(first), _KEY) == event_fingerprint(
        _event(second), _KEY
    )


def test_password_changes_the_fingerprint() -> None:
    first = CustomerUpdatedData(
        credentials=IntegrationCustomerCredentialsPatch(password="first-password")
    )
    second = CustomerUpdatedData(
        credentials=IntegrationCustomerCredentialsPatch(password="second-password")
    )

    assert event_fingerprint(_event(first), _KEY) != event_fingerprint(
        _event(second), _KEY
    )


def test_event_metadata_changes_the_fingerprint() -> None:
    event = _event()
    original = event_fingerprint(event, _KEY)

    assert original != event_fingerprint(replace(event, event_id=UUID(int=2)), _KEY)
    assert original != event_fingerprint(replace(event, resource_version=3), _KEY)
    assert original != event_fingerprint(replace(event, reference_id=43), _KEY)
    assert original != event_fingerprint(
        replace(event, occurred_at=event.occurred_at + timedelta(seconds=1)), _KEY
    )


def test_equal_datetimes_with_different_offsets_have_one_fingerprint() -> None:
    event = _event()
    same_instant = event.occurred_at.astimezone(timezone(timedelta(hours=2)))

    assert event_fingerprint(event, _KEY) == event_fingerprint(
        replace(event, occurred_at=same_instant), _KEY
    )


def test_fingerprint_depends_on_a_long_stable_secret() -> None:
    event = _event()

    assert event_fingerprint(event, _KEY) != event_fingerprint(event, b"x" * 32)
    with pytest.raises(ValueError, match="at least 32 bytes"):
        event_fingerprint(event, b"short")


def test_non_finite_numbers_are_rejected() -> None:
    event = _event(
        CustomerUpdatedData(
            extensions=IntegrationCustomerExtensionsPatch(
                parameters={"invalid": float("nan")}
            )
        )
    )

    with pytest.raises(ValueError, match="finite"):
        event_fingerprint(event, _KEY)
