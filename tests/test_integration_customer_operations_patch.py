import subprocess
import sys
from dataclasses import FrozenInstanceError, asdict, fields, replace
from datetime import datetime
from pathlib import Path
from typing import get_type_hints

import pytest

from app.application.dtos.customer_integration.operations import (
    IntegrationCustomerExtensions,
    IntegrationCustomerNote,
    IntegrationCustomerNotes,
    IntegrationOperationalSettings,
    IntegrationShop,
    IntegrationShopGroup,
)
from app.application.dtos.customer_integration.operations_patch import (
    IntegrationCustomerExtensionsPatch,
    IntegrationCustomerNotesPatch,
    IntegrationOperationalSettingsPatch,
    IntegrationShopPatch,
)
from app.application.dtos.customer_integration.unset import UNSET, UnsetType

_OperationsPatch = (
    IntegrationCustomerExtensionsPatch
    | IntegrationCustomerNotesPatch
    | IntegrationOperationalSettingsPatch
    | IntegrationShopPatch
)
_PATCH_PAIRS: tuple[tuple[type[object], type[_OperationsPatch]], ...] = (
    (IntegrationShop, IntegrationShopPatch),
    (IntegrationOperationalSettings, IntegrationOperationalSettingsPatch),
    (IntegrationCustomerNotes, IntegrationCustomerNotesPatch),
    (IntegrationCustomerExtensions, IntegrationCustomerExtensionsPatch),
)


@pytest.mark.parametrize(("complete_type", "patch_type"), _PATCH_PAIRS)
def test_operations_patch_covers_complete_dto_fields(
    complete_type: type[object], patch_type: type[_OperationsPatch]
) -> None:
    assert get_type_hints(patch_type) == {
        name: annotation | UnsetType
        for name, annotation in get_type_hints(complete_type).items()
    }


@pytest.mark.parametrize("patch_type", [pair[1] for pair in _PATCH_PAIRS])
def test_operations_patch_fields_default_to_omission(
    patch_type: type[_OperationsPatch],
) -> None:
    patch = patch_type()

    for field in fields(patch):
        assert getattr(patch, field.name) is UNSET


@pytest.mark.parametrize("patch_type", [pair[1] for pair in _PATCH_PAIRS])
def test_operations_patches_are_frozen_and_slotted(
    patch_type: type[_OperationsPatch],
) -> None:
    patch = patch_type()

    assert not hasattr(patch, "__dict__")
    with pytest.raises(FrozenInstanceError):
        setattr(patch, fields(patch)[0].name, UNSET)


@pytest.mark.parametrize(
    ("patch_type", "field_name"),
    [
        (IntegrationShopPatch, "groups"),
        (IntegrationOperationalSettingsPatch, "disable_box_discount"),
        (IntegrationCustomerNotesPatch, "items"),
    ],
)
def test_required_operations_fields_reject_null(
    patch_type: type[_OperationsPatch], field_name: str
) -> None:
    with pytest.raises(ValueError, match="cannot be cleared"):
        replace(patch_type(), **{field_name: None})


@pytest.mark.parametrize("field_name", ["latitude", "longitude"])
@pytest.mark.parametrize("value", [None, 0.0, 12.5])
def test_shop_coordinates_preserve_null_zero_and_values(
    field_name: str, value: float | None
) -> None:
    patch = replace(IntegrationShopPatch(), **{field_name: value})

    assert getattr(patch, field_name) is value
    for field in fields(patch):
        if field.name != field_name:
            assert getattr(patch, field.name) is UNSET


def test_shop_groups_distinguish_omission_clearing_and_replacement() -> None:
    groups = (
        IntegrationShopGroup("professional-group", "Professional Group"),
        IntegrationShopGroup("rei-la-rete", "R.E.I. - LA RETE"),
    )
    omitted = IntegrationShopPatch()
    cleared = IntegrationShopPatch(groups=())
    replacement = IntegrationShopPatch(groups=groups)

    assert omitted.groups is UNSET
    assert cleared.groups == ()
    assert replacement.groups is groups
    assert replacement.latitude is UNSET
    assert replacement.longitude is UNSET


@pytest.mark.parametrize("value", [True, False])
def test_required_operational_boolean_preserves_explicit_value(value: bool) -> None:
    patch = IntegrationOperationalSettingsPatch(disable_box_discount=value)

    assert patch.disable_box_discount is value
    assert patch.disable_quantity_delivery is UNSET
    assert patch.prepaid_returns is UNSET
    assert patch.disable_sale_limit is UNSET


@pytest.mark.parametrize(
    "field_name",
    ["disable_quantity_delivery", "prepaid_returns", "disable_sale_limit"],
)
@pytest.mark.parametrize("value", [True, False, None])
def test_nullable_operational_booleans_preserve_explicit_values(
    field_name: str, value: bool | None
) -> None:
    patch = replace(IntegrationOperationalSettingsPatch(), **{field_name: value})

    assert getattr(patch, field_name) is value
    for field in fields(patch):
        if field.name != field_name:
            assert getattr(patch, field.name) is UNSET


def test_note_items_distinguish_omission_clearing_and_replacement() -> None:
    timestamp = datetime.fromisoformat("2026-09-15T10:15:30+02:00")
    notes = (
        IntegrationCustomerNote(timestamp, "", False),
        IntegrationCustomerNote(timestamp, "Follow up", True),
    )
    omitted = IntegrationCustomerNotesPatch()
    cleared = IntegrationCustomerNotesPatch(items=())
    replacement = IntegrationCustomerNotesPatch(items=notes)

    assert omitted.items is UNSET
    assert cleared.items == ()
    assert replacement.items is notes
    assert isinstance(replacement.items, tuple)
    assert replacement.items[0].text == ""
    assert replacement.items[0].open is False
    assert replacement.administrative_note is UNSET


@pytest.mark.parametrize("value", [None, "", "Administrative note"])
def test_administrative_note_preserves_explicit_values(value: str | None) -> None:
    patch = IntegrationCustomerNotesPatch(administrative_note=value)

    assert patch.administrative_note is value
    assert patch.items is UNSET


@pytest.mark.parametrize("field_name", ["parameters", "extra_data"])
def test_extension_objects_distinguish_omission_null_and_empty_object(
    field_name: str,
) -> None:
    omitted = IntegrationCustomerExtensionsPatch()
    cleared = replace(omitted, **{field_name: None})
    empty_patch = replace(omitted, **{field_name: {}})

    assert getattr(omitted, field_name) is UNSET
    assert getattr(cleared, field_name) is None
    assert getattr(empty_patch, field_name) == {}


def test_extension_objects_preserve_recursive_merge_patch_intent() -> None:
    parameters = {
        "existing": {
            "remove": None,
            "enabled": False,
            "count": 0,
            "label": "",
            "items": [],
        }
    }
    extra_data = {"replaceArray": [{"value": 1}], "clearArray": []}
    patch = IntegrationCustomerExtensionsPatch(
        parameters=parameters,
        extra_data=extra_data,
    )

    assert patch.parameters is parameters
    assert patch.extra_data is extra_data
    assert isinstance(patch.parameters, dict)
    assert patch.parameters["existing"] == {
        "remove": None,
        "enabled": False,
        "count": 0,
        "label": "",
        "items": [],
    }


def test_dictionary_conversion_preserves_mixed_operations_update_intent() -> None:
    timestamp = datetime.fromisoformat("2026-09-15T10:15:30+02:00")
    patch_values = {
        "shop": IntegrationShopPatch(latitude=0.0, groups=()),
        "settings": IntegrationOperationalSettingsPatch(
            disable_box_discount=False,
            prepaid_returns=None,
        ),
        "notes": IntegrationCustomerNotesPatch(
            items=(IntegrationCustomerNote(timestamp, "", False),),
            administrative_note="",
        ),
        "extensions": IntegrationCustomerExtensionsPatch(
            parameters={"remove": None, "count": 0, "items": []},
            extra_data=None,
        ),
    }

    assert asdict(patch_values["shop"]) == {
        "latitude": 0.0,
        "longitude": UNSET,
        "groups": (),
    }
    assert asdict(patch_values["settings"]) == {
        "disable_box_discount": False,
        "disable_quantity_delivery": UNSET,
        "prepaid_returns": None,
        "disable_sale_limit": UNSET,
    }
    assert asdict(patch_values["notes"]) == {
        "items": ({"occurred_at": timestamp, "text": "", "open": False},),
        "administrative_note": "",
    }
    assert asdict(patch_values["extensions"]) == {
        "parameters": {"remove": None, "count": 0, "items": []},
        "extra_data": None,
    }


def test_operations_patches_import_without_third_party_packages() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-S",
            "-c",
            "import app.application.dtos.customer_integration.operations_patch",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
