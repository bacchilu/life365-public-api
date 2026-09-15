import subprocess
import sys
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path
from typing import get_args, get_type_hints

import pytest

import app.application.dtos as dtos
from app.application.dtos.customer_integration.customer import IntegrationCustomerData
from app.application.dtos.customer_integration.customer_patch import CustomerUpdatedData
from app.application.dtos.customer_integration.profile_patch import (
    IntegrationCompanyPatch,
)
from app.application.dtos.customer_integration.unset import UNSET, UnsetType


def test_customer_updated_data_covers_complete_customer_fields() -> None:
    complete_fields = get_type_hints(IntegrationCustomerData)
    patch_fields = get_type_hints(CustomerUpdatedData)

    assert tuple(patch_fields) == tuple(complete_fields)
    assert all(
        UnsetType in get_args(annotation) for annotation in patch_fields.values()
    )


def test_customer_updated_data_defaults_every_section_to_omitted() -> None:
    patch = CustomerUpdatedData()

    for patch_field in fields(patch):
        assert getattr(patch, patch_field.name) is UNSET


def test_customer_updated_data_is_frozen_and_slotted() -> None:
    patch = CustomerUpdatedData()

    assert not hasattr(patch, "__dict__")
    with pytest.raises(FrozenInstanceError):
        setattr(patch, "company", UNSET)


@pytest.mark.parametrize(
    "field_name", [patch_field.name for patch_field in fields(CustomerUpdatedData)]
)
def test_customer_updated_data_rejects_null_section(field_name: str) -> None:
    with pytest.raises(ValueError, match=f"{field_name} cannot be cleared"):
        replace(CustomerUpdatedData(), **{field_name: None})


def test_customer_updated_data_preserves_nested_partial_patch() -> None:
    patch = CustomerUpdatedData(
        company=IntegrationCompanyPatch(
            website="",
            primary_phone=None,
        )
    )

    assert isinstance(patch.company, IntegrationCompanyPatch)
    assert patch.company.website == ""
    assert patch.company.primary_phone is None
    assert patch.company.name is UNSET
    assert patch.company.secondary_phone is UNSET
    assert patch.credentials is UNSET
    assert patch.extensions is UNSET


def test_customer_patch_imports_without_third_party_packages() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-S",
            "-c",
            "from app.application.dtos.customer_integration.customer_patch import CustomerUpdatedData",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_customer_patch_types_are_exported_from_application_dtos() -> None:
    assert dtos.CustomerUpdatedData is CustomerUpdatedData
    assert dtos.IntegrationCompanyPatch is IntegrationCompanyPatch
    assert dtos.UNSET is UNSET
