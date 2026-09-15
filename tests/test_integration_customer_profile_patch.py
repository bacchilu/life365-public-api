import subprocess
import sys
from dataclasses import FrozenInstanceError, fields, replace
from datetime import datetime
from pathlib import Path
from typing import get_args, get_type_hints

import pytest

from app.application.dtos.customer_integration import profile
from app.application.dtos.customer_integration.profile_patch import (
    IntegrationCommunicationPreferencesPatch,
    IntegrationCompanyPatch,
    IntegrationCustomerCredentialsPatch,
    IntegrationPrimaryContactPatch,
    IntegrationRegistrationPatch,
)
from app.application.dtos.customer_integration.unset import UNSET, UnsetType

_ProfilePatch = (
    IntegrationCompanyPatch
    | IntegrationCommunicationPreferencesPatch
    | IntegrationCustomerCredentialsPatch
    | IntegrationPrimaryContactPatch
    | IntegrationRegistrationPatch
)
_PATCH_TYPES: tuple[type[_ProfilePatch], ...] = (
    IntegrationCompanyPatch,
    IntegrationCommunicationPreferencesPatch,
    IntegrationCustomerCredentialsPatch,
    IntegrationPrimaryContactPatch,
    IntegrationRegistrationPatch,
)


@pytest.mark.parametrize("patch_type", _PATCH_TYPES)
def test_profile_patch_covers_complete_dto_fields(
    patch_type: type[_ProfilePatch],
) -> None:
    complete_type = getattr(profile, patch_type.__name__.removesuffix("Patch"))
    complete_hints = get_type_hints(complete_type)
    patch_hints = get_type_hints(patch_type)

    assert patch_hints == {
        name: annotation | UnsetType for name, annotation in complete_hints.items()
    }


@pytest.mark.parametrize("patch_type", _PATCH_TYPES)
def test_profile_patch_defaults_to_omitted_fields(
    patch_type: type[_ProfilePatch],
) -> None:
    patch = patch_type()

    for field in fields(patch):
        assert getattr(patch, field.name) is UNSET


@pytest.mark.parametrize("patch_type", _PATCH_TYPES)
def test_profile_patch_is_frozen_and_slotted(
    patch_type: type[_ProfilePatch],
) -> None:
    patch = patch_type()

    assert not hasattr(patch, "__dict__")
    with pytest.raises(FrozenInstanceError):
        setattr(patch, fields(patch)[0].name, UNSET)


@pytest.mark.parametrize(
    ("patch_type", "field_name"),
    [
        (IntegrationCustomerCredentialsPatch, "login"),
        (IntegrationCustomerCredentialsPatch, "password"),
        (IntegrationCompanyPatch, "name"),
        (IntegrationPrimaryContactPatch, "full_name"),
        (IntegrationPrimaryContactPatch, "email"),
        (IntegrationPrimaryContactPatch, "additional_emails"),
    ],
)
def test_required_profile_fields_reject_explicit_null(
    patch_type: type[_ProfilePatch], field_name: str
) -> None:
    with pytest.raises(ValueError, match="cannot be cleared"):
        replace(patch_type(), **{field_name: None})


@pytest.mark.parametrize(
    "patch_type",
    [
        IntegrationCompanyPatch,
        IntegrationPrimaryContactPatch,
        IntegrationCommunicationPreferencesPatch,
        IntegrationRegistrationPatch,
    ],
)
def test_nullable_profile_fields_preserve_explicit_null(
    patch_type: type[_ProfilePatch],
) -> None:
    for field_name, annotation in get_type_hints(patch_type).items():
        if type(None) in get_args(annotation):
            patch = replace(patch_type(), **{field_name: None})
            assert getattr(patch, field_name) is None
            for field in fields(patch):
                if field.name != field_name:
                    assert getattr(patch, field.name) is UNSET


@pytest.mark.parametrize("value", [True, False, None])
def test_boolean_profile_fields_preserve_explicit_values(value: bool | None) -> None:
    preferences = IntegrationCommunicationPreferencesPatch(
        newsletter=value, privacy_registered=value, rules_registered=value
    )
    registration = IntegrationRegistrationPatch(verified=value)

    assert preferences.newsletter is value
    assert preferences.privacy_registered is value
    assert preferences.rules_registered is value
    assert registration.verified is value
    assert registration.registered_at is UNSET
    assert registration.last_login_at is UNSET


@pytest.mark.parametrize(
    ("patch_type", "field_names"),
    [
        (IntegrationCustomerCredentialsPatch, ("login", "password")),
        (
            IntegrationCompanyPatch,
            ("name", "website", "primary_phone", "secondary_phone"),
        ),
        (
            IntegrationPrimaryContactPatch,
            ("full_name", "email", "certified_email", "preferred_language"),
        ),
    ],
)
def test_empty_strings_are_not_converted_to_null_or_omission(
    patch_type: type[_ProfilePatch], field_names: tuple[str, ...]
) -> None:
    patch = replace(patch_type(), **{name: "" for name in field_names})

    for name in field_names:
        assert getattr(patch, name) == ""


def test_partial_company_patch_preserves_other_fields_as_omitted() -> None:
    patch = IntegrationCompanyPatch(website="https://new.example")

    assert patch.website == "https://new.example"
    assert patch.name is UNSET
    assert patch.primary_phone is UNSET
    assert patch.secondary_phone is UNSET


def test_additional_emails_distinguish_omission_clearing_and_replacement() -> None:
    emails = (
        profile.IntegrationAdditionalEmail("sales@example.com", True, False, None),
        profile.IntegrationAdditionalEmail("news@example.com", False, True, "contact"),
    )
    omitted = IntegrationPrimaryContactPatch()
    cleared = IntegrationPrimaryContactPatch(additional_emails=())
    replacement = IntegrationPrimaryContactPatch(additional_emails=emails)

    assert omitted.additional_emails is UNSET
    assert cleared.additional_emails == ()
    assert replacement.additional_emails is emails
    assert replacement.full_name is UNSET
    assert replacement.email is UNSET


@pytest.mark.parametrize("field_name", ["registered_at", "last_login_at"])
def test_registration_patch_preserves_timestamp_and_omitted_fields(
    field_name: str,
) -> None:
    timestamp = datetime.fromisoformat("2026-09-15T10:15:30.123456+02:00")
    patch = replace(IntegrationRegistrationPatch(), **{field_name: timestamp})

    assert getattr(patch, field_name) is timestamp
    for field in fields(patch):
        if field.name != field_name:
            assert getattr(patch, field.name) is UNSET


def test_password_patch_preserves_value_without_exposing_it() -> None:
    password = "synthetic-update-password"
    patch = IntegrationCustomerCredentialsPatch(password=password)

    assert patch.password == password
    assert patch.login is UNSET
    assert password not in repr(patch)
    assert password not in str(patch)


def test_profile_patches_import_without_third_party_packages() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-S",
            "-c",
            "import app.application.dtos.customer_integration.profile_patch",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
