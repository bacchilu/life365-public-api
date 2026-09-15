import subprocess
import sys
from dataclasses import FrozenInstanceError, asdict, fields, replace
from decimal import Decimal
from pathlib import Path
from typing import get_type_hints

import pytest

from app.application.dtos.customer_integration.commercial import (
    IntegrationAgent,
    IntegrationCategory,
    IntegrationCommercial,
    IntegrationSalesChannel,
)
from app.application.dtos.customer_integration.commercial_patch import (
    IntegrationCommercialPatch,
    IntegrationSalesChannelPatch,
)
from app.application.dtos.customer_integration.unset import UNSET, UnsetType


def test_commercial_patch_covers_complete_dto_fields() -> None:
    expected = {
        name: annotation | UnsetType
        for name, annotation in get_type_hints(IntegrationCommercial).items()
    }
    expected["sales_channel"] = IntegrationSalesChannelPatch | None | UnsetType

    assert get_type_hints(IntegrationCommercialPatch) == expected


def test_channel_patch_covers_complete_sales_channel_fields() -> None:
    assert get_type_hints(IntegrationSalesChannelPatch) == {
        name: annotation | UnsetType
        for name, annotation in get_type_hints(IntegrationSalesChannel).items()
    }


@pytest.mark.parametrize(
    "patch_type", [IntegrationCommercialPatch, IntegrationSalesChannelPatch]
)
def test_commercial_patch_fields_default_to_omission(
    patch_type: type[IntegrationCommercialPatch | IntegrationSalesChannelPatch],
) -> None:
    patch = patch_type()

    for field in fields(patch):
        assert getattr(patch, field.name) is UNSET


@pytest.mark.parametrize(
    "patch_type", [IntegrationCommercialPatch, IntegrationSalesChannelPatch]
)
def test_commercial_patches_are_frozen_and_slotted(
    patch_type: type[IntegrationCommercialPatch | IntegrationSalesChannelPatch],
) -> None:
    patch = patch_type()

    assert not hasattr(patch, "__dict__")
    with pytest.raises(FrozenInstanceError):
        setattr(patch, fields(patch)[0].name, UNSET)


@pytest.mark.parametrize(
    ("patch_type", "field_name"),
    [
        (IntegrationCommercialPatch, "preferred_categories"),
        (IntegrationSalesChannelPatch, "code"),
        (IntegrationSalesChannelPatch, "label"),
    ],
)
def test_required_commercial_fields_reject_null(
    patch_type: type[IntegrationCommercialPatch | IntegrationSalesChannelPatch],
    field_name: str,
) -> None:
    with pytest.raises(ValueError, match="cannot be cleared"):
        replace(patch_type(), **{field_name: None})


@pytest.mark.parametrize(
    "field_name",
    [
        "sales_channel",
        "assigned_agent",
        "payment_agreement",
        "preferred_payment_type_code",
        "payment_days",
        "payment_days_end_of_month",
        "credit_granted",
        "credit_value",
    ],
)
def test_nullable_commercial_fields_preserve_null(field_name: str) -> None:
    patch = replace(IntegrationCommercialPatch(), **{field_name: None})

    assert getattr(patch, field_name) is None
    for field in fields(patch):
        if field.name != field_name:
            assert getattr(patch, field.name) is UNSET


@pytest.mark.parametrize("field_name", ["payment_days", "payment_days_end_of_month"])
@pytest.mark.parametrize("value", [0, 30])
def test_payment_days_preserve_zero_and_other_integers(
    field_name: str, value: int
) -> None:
    patch = replace(IntegrationCommercialPatch(), **{field_name: value})

    assert type(getattr(patch, field_name)) is int
    assert getattr(patch, field_name) == value
    for field in fields(patch):
        if field.name != field_name:
            assert getattr(patch, field.name) is UNSET


@pytest.mark.parametrize("field_name", ["credit_granted", "credit_value"])
@pytest.mark.parametrize(
    "decimal_text",
    ["0.00", "7500.50", "12345678901234567890.12345678901234567890"],
)
def test_credit_values_preserve_decimal_zero_and_precision(
    field_name: str, decimal_text: str
) -> None:
    value = Decimal(decimal_text)
    patch = replace(IntegrationCommercialPatch(), **{field_name: value})

    assert getattr(patch, field_name) is value
    assert str(getattr(patch, field_name)) == decimal_text
    for field in fields(patch):
        if field.name != field_name:
            assert getattr(patch, field.name) is UNSET


@pytest.mark.parametrize(
    ("patch_type", "field_name"),
    [
        (IntegrationCommercialPatch, "payment_agreement"),
        (IntegrationCommercialPatch, "preferred_payment_type_code"),
        (IntegrationSalesChannelPatch, "code"),
        (IntegrationSalesChannelPatch, "label"),
    ],
)
def test_empty_commercial_strings_are_not_normalized(
    patch_type: type[IntegrationCommercialPatch | IntegrationSalesChannelPatch],
    field_name: str,
) -> None:
    patch = replace(patch_type(), **{field_name: ""})

    assert getattr(patch, field_name) == ""
    for field in fields(patch):
        if field.name != field_name:
            assert getattr(patch, field.name) is UNSET


def test_categories_distinguish_omission_clearing_and_replacement() -> None:
    categories = (
        IntegrationCategory("networking", "Network&Security"),
        IntegrationCategory("lighting", "Lighting"),
    )
    omitted = IntegrationCommercialPatch()
    cleared = IntegrationCommercialPatch(preferred_categories=())
    replacement = IntegrationCommercialPatch(preferred_categories=categories)

    assert omitted.preferred_categories is UNSET
    assert cleared.preferred_categories == ()
    assert replacement.preferred_categories is categories
    for field in fields(replacement):
        if field.name != "preferred_categories":
            assert getattr(replacement, field.name) is UNSET


def test_agent_assignment_distinguishes_omission_fallback_and_reference() -> None:
    agent = IntegrationAgent(
        reference_id=117,
        user_login="test-agent",
        name="Test Agent",
        email="agent@example.com",
        phone=None,
    )
    omitted = IntegrationCommercialPatch()
    fallback = IntegrationCommercialPatch(assigned_agent=None)
    assigned = IntegrationCommercialPatch(assigned_agent=agent)

    assert omitted.assigned_agent is UNSET
    assert fallback.assigned_agent is None
    assert assigned.assigned_agent is agent
    for patch in (fallback, assigned):
        for field in fields(patch):
            if field.name != "assigned_agent":
                assert getattr(patch, field.name) is UNSET


@pytest.mark.parametrize(
    ("field_name", "value"), [("code", "N13"), ("label", "Updated channel label")]
)
def test_channel_patch_preserves_changes_to_one_nested_field(
    field_name: str, value: str
) -> None:
    channel = replace(IntegrationSalesChannelPatch(), **{field_name: value})
    patch = IntegrationCommercialPatch(sales_channel=channel)

    assert patch.sales_channel is channel
    assert getattr(channel, field_name) == value
    for field in fields(channel):
        if field.name != field_name:
            assert getattr(channel, field.name) is UNSET
    for field in fields(patch):
        if field.name != "sales_channel":
            assert getattr(patch, field.name) is UNSET


def test_empty_channel_patch_is_distinct_from_omission_and_null() -> None:
    channel = IntegrationSalesChannelPatch()
    patch = IntegrationCommercialPatch(sales_channel=channel)

    assert IntegrationCommercialPatch().sales_channel is UNSET
    assert IntegrationCommercialPatch(sales_channel=None).sales_channel is None
    assert patch.sales_channel is channel
    assert channel.code is UNSET
    assert channel.label is UNSET


def test_dictionary_conversion_preserves_mixed_commercial_update_intent() -> None:
    patch = IntegrationCommercialPatch(
        preferred_categories=(),
        sales_channel=IntegrationSalesChannelPatch(code="N13"),
        assigned_agent=None,
        payment_agreement="",
        payment_days=0,
        credit_value=Decimal("0.00"),
    )

    assert asdict(patch) == {
        "preferred_categories": (),
        "sales_channel": {"code": "N13", "label": UNSET},
        "assigned_agent": None,
        "payment_agreement": "",
        "preferred_payment_type_code": UNSET,
        "payment_days": 0,
        "payment_days_end_of_month": UNSET,
        "credit_granted": UNSET,
        "credit_value": Decimal("0.00"),
    }


def test_commercial_patches_import_without_third_party_packages() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-S",
            "-c",
            "import app.application.dtos.customer_integration.commercial_patch",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
