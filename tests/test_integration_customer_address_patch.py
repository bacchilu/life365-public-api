import subprocess
import sys
from dataclasses import FrozenInstanceError, asdict, fields, replace
from pathlib import Path
from typing import get_type_hints

import pytest

from app.application.dtos.customer_integration.address import (
    IntegrationAddress,
    IntegrationDelivery,
)
from app.application.dtos.customer_integration.address_patch import (
    IntegrationAddressPatch,
    IntegrationDeliveryPatch,
)
from app.application.dtos.customer_integration.unset import UNSET, UnsetType


def test_address_patch_covers_complete_address_fields() -> None:
    assert get_type_hints(IntegrationAddressPatch) == {
        name: annotation | UnsetType
        for name, annotation in get_type_hints(IntegrationAddress).items()
    }


def test_delivery_patch_uses_a_nested_address_patch() -> None:
    expected = {
        name: annotation | UnsetType
        for name, annotation in get_type_hints(IntegrationDelivery).items()
    }
    expected["address"] = IntegrationAddressPatch | None | UnsetType

    assert get_type_hints(IntegrationDeliveryPatch) == expected


@pytest.mark.parametrize(
    "patch_type", [IntegrationAddressPatch, IntegrationDeliveryPatch]
)
def test_address_and_delivery_fields_default_to_omission(
    patch_type: type[IntegrationAddressPatch | IntegrationDeliveryPatch],
) -> None:
    patch = patch_type()

    for field in fields(patch):
        assert getattr(patch, field.name) is UNSET


@pytest.mark.parametrize(
    "patch_type", [IntegrationAddressPatch, IntegrationDeliveryPatch]
)
def test_address_and_delivery_patches_are_frozen_and_slotted(
    patch_type: type[IntegrationAddressPatch | IntegrationDeliveryPatch],
) -> None:
    patch = patch_type()

    assert not hasattr(patch, "__dict__")
    with pytest.raises(FrozenInstanceError):
        setattr(patch, fields(patch)[0].name, UNSET)


@pytest.mark.parametrize(
    "field_name", ["street", "city", "country_code", "region_name"]
)
def test_required_address_fields_reject_explicit_null(field_name: str) -> None:
    with pytest.raises(ValueError, match="cannot be cleared"):
        replace(IntegrationAddressPatch(), **{field_name: None})


@pytest.mark.parametrize(
    "field_name", ["street", "city", "country_code", "region_name"]
)
def test_empty_address_strings_are_preserved_as_supplied(field_name: str) -> None:
    patch = replace(IntegrationAddressPatch(), **{field_name: ""})

    assert getattr(patch, field_name) == ""
    for field in fields(patch):
        if field.name != field_name:
            assert getattr(patch, field.name) is UNSET


@pytest.mark.parametrize("value", [None, "", "00100"])
def test_postal_code_preserves_null_empty_string_and_leading_zeros(
    value: str | None,
) -> None:
    patch = IntegrationAddressPatch(postal_code=value)

    assert patch.postal_code is value
    assert patch.street is UNSET
    assert patch.city is UNSET
    assert patch.country_code is UNSET
    assert patch.region_name is UNSET


@pytest.mark.parametrize("field_name", ["business_name", "contact_name", "phone"])
@pytest.mark.parametrize("value", [None, "", "Supplied value"])
def test_delivery_text_fields_preserve_explicit_values(
    field_name: str, value: str | None
) -> None:
    patch = replace(IntegrationDeliveryPatch(), **{field_name: value})

    assert getattr(patch, field_name) is value
    for field in fields(patch):
        if field.name != field_name:
            assert getattr(patch, field.name) is UNSET


def test_delivery_address_distinguishes_omission_clearing_and_partial_change() -> None:
    address = IntegrationAddressPatch(city="Cesena")
    omitted = IntegrationDeliveryPatch()
    cleared = IntegrationDeliveryPatch(address=None)
    changed = IntegrationDeliveryPatch(address=address)

    assert omitted.address is UNSET
    assert cleared.address is None
    assert changed.address is address
    assert address.city == "Cesena"
    assert address.street is UNSET
    assert address.postal_code is UNSET
    assert address.country_code is UNSET
    assert address.region_name is UNSET
    for patch in (omitted, cleared, changed):
        assert patch.business_name is UNSET
        assert patch.contact_name is UNSET
        assert patch.phone is UNSET


def test_empty_nested_patch_does_not_become_null_or_omission() -> None:
    address = IntegrationAddressPatch()
    patch = IntegrationDeliveryPatch(address=address)

    assert patch.address is address
    assert patch.address is not None
    assert patch.address is not UNSET
    for field in fields(address):
        assert getattr(address, field.name) is UNSET


def test_nested_patch_preserves_null_and_omission_in_dictionary_conversion() -> None:
    patch = IntegrationDeliveryPatch(
        address=IntegrationAddressPatch(city="Cesena", postal_code=None)
    )

    assert asdict(patch) == {
        "business_name": UNSET,
        "contact_name": UNSET,
        "phone": UNSET,
        "address": {
            "street": UNSET,
            "city": "Cesena",
            "postal_code": None,
            "country_code": UNSET,
            "region_name": UNSET,
        },
    }


def test_address_patches_import_without_third_party_packages() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-S",
            "-c",
            "import app.application.dtos.customer_integration.address_patch",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
