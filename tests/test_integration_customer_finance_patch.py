import subprocess
import sys
from dataclasses import FrozenInstanceError, asdict, fields, replace
from decimal import Decimal
from pathlib import Path
from typing import get_type_hints

import pytest

from app.application.dtos.customer_integration.finance import (
    IntegrationBanking,
    IntegrationTaxProfile,
)
from app.application.dtos.customer_integration.finance_patch import (
    IntegrationBankingPatch,
    IntegrationTaxProfilePatch,
)
from app.application.dtos.customer_integration.unset import UNSET, UnsetType


def test_tax_patch_covers_complete_tax_profile_fields() -> None:
    assert get_type_hints(IntegrationTaxProfilePatch) == {
        name: annotation | UnsetType
        for name, annotation in get_type_hints(IntegrationTaxProfile).items()
    }


def test_banking_patch_covers_complete_banking_fields() -> None:
    assert get_type_hints(IntegrationBankingPatch) == {
        name: annotation | UnsetType
        for name, annotation in get_type_hints(IntegrationBanking).items()
    }


@pytest.mark.parametrize(
    "patch_type", [IntegrationTaxProfilePatch, IntegrationBankingPatch]
)
def test_financial_patch_fields_default_to_omission(
    patch_type: type[IntegrationTaxProfilePatch | IntegrationBankingPatch],
) -> None:
    patch = patch_type()

    for field in fields(patch):
        assert getattr(patch, field.name) is UNSET


@pytest.mark.parametrize(
    "patch_type", [IntegrationTaxProfilePatch, IntegrationBankingPatch]
)
def test_financial_patches_are_frozen_and_slotted(
    patch_type: type[IntegrationTaxProfilePatch | IntegrationBankingPatch],
) -> None:
    patch = patch_type()

    assert not hasattr(patch, "__dict__")
    with pytest.raises(FrozenInstanceError):
        setattr(patch, fields(patch)[0].name, UNSET)


def test_vies_status_rejects_explicit_null() -> None:
    with pytest.raises(ValueError, match="viesValidated cannot be cleared"):
        replace(IntegrationTaxProfilePatch(), vies_validated=None)


@pytest.mark.parametrize("value", [True, False])
def test_vies_status_preserves_explicit_boolean_values(value: bool) -> None:
    patch = IntegrationTaxProfilePatch(vies_validated=value)

    assert patch.vies_validated is value
    for field in fields(patch):
        if field.name != "vies_validated":
            assert getattr(patch, field.name) is UNSET


@pytest.mark.parametrize(
    ("patch_type", "field_name"),
    [
        (IntegrationTaxProfilePatch, "fiscal_code"),
        (IntegrationTaxProfilePatch, "vat_country_code"),
        (IntegrationTaxProfilePatch, "vat_number"),
        (IntegrationTaxProfilePatch, "fiscal_agent_code"),
        (IntegrationTaxProfilePatch, "secondary_tax_value"),
        (IntegrationBankingPatch, "abi"),
        (IntegrationBankingPatch, "cab"),
        (IntegrationBankingPatch, "iban"),
    ],
)
def test_nullable_financial_fields_preserve_explicit_clearing(
    patch_type: type[IntegrationTaxProfilePatch | IntegrationBankingPatch],
    field_name: str,
) -> None:
    patch = replace(patch_type(), **{field_name: None})

    assert getattr(patch, field_name) is None
    for field in fields(patch):
        if field.name != field_name:
            assert getattr(patch, field.name) is UNSET


@pytest.mark.parametrize(
    "decimal_text",
    ["0", "0.00", "0.10", "12345678901234567890.12345678901234567890"],
)
def test_secondary_tax_preserves_decimal_zero_scale_and_precision(
    decimal_text: str,
) -> None:
    value = Decimal(decimal_text)
    patch = IntegrationTaxProfilePatch(secondary_tax_value=value)

    assert patch.secondary_tax_value is value
    assert str(patch.secondary_tax_value) == decimal_text
    for field in fields(patch):
        if field.name != "secondary_tax_value":
            assert getattr(patch, field.name) is UNSET


@pytest.mark.parametrize(
    ("patch_type", "field_name"),
    [
        (IntegrationTaxProfilePatch, "fiscal_code"),
        (IntegrationTaxProfilePatch, "vat_country_code"),
        (IntegrationTaxProfilePatch, "vat_number"),
        (IntegrationTaxProfilePatch, "fiscal_agent_code"),
        (IntegrationBankingPatch, "abi"),
        (IntegrationBankingPatch, "cab"),
        (IntegrationBankingPatch, "iban"),
    ],
)
def test_empty_financial_strings_remain_explicit_values(
    patch_type: type[IntegrationTaxProfilePatch | IntegrationBankingPatch],
    field_name: str,
) -> None:
    patch = replace(patch_type(), **{field_name: ""})

    assert getattr(patch, field_name) == ""
    for field in fields(patch):
        if field.name != field_name:
            assert getattr(patch, field.name) is UNSET


def test_bank_codes_preserve_leading_zeros() -> None:
    patch = IntegrationBankingPatch(abi="03069", cab="09606")

    assert patch.abi == "03069"
    assert patch.cab == "09606"
    assert patch.iban is UNSET


def test_dictionary_conversion_preserves_mixed_update_intent() -> None:
    tax = IntegrationTaxProfilePatch(
        fiscal_code=None, vies_validated=False, secondary_tax_value=Decimal("0.00")
    )
    banking = IntegrationBankingPatch(abi="", iban=None)

    assert asdict(tax) == {
        "fiscal_code": None,
        "vat_country_code": UNSET,
        "vat_number": UNSET,
        "vies_validated": False,
        "fiscal_agent_code": UNSET,
        "secondary_tax_value": Decimal("0.00"),
    }
    assert asdict(banking) == {"abi": "", "cab": UNSET, "iban": None}


def test_financial_patches_import_without_third_party_packages() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-S",
            "-c",
            "import app.application.dtos.customer_integration.finance_patch",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
