"""Apply JSON Merge Patch to customer extension columns."""

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from app.application.dtos.customer_integration.customer_patch import CustomerUpdatedData
from app.application.dtos.customer_integration.unset import UNSET
from app.application.exceptions import InvalidCustomerDataException

from .json_values import extension_jsonb


def _merge_json(existing: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(existing)
    for key, value in patch.items():
        if value is None:
            merged.pop(key, None)
        elif isinstance(value, dict):
            old_value = merged.get(key)
            merged[key] = _merge_json(
                old_value if isinstance(old_value, dict) else {}, value
            )
        else:
            merged[key] = deepcopy(value)
    return merged


def customer_json_update_values(
    data: CustomerUpdatedData, current: Mapping[str, Any]
) -> dict[str, object]:
    values: dict[str, object] = {}
    if data.extensions is UNSET:
        return values

    for name, column in (("parameters", "parameters"), ("extra_data", "extra_data")):
        patch_value = getattr(data.extensions, name)
        if patch_value is UNSET:
            continue
        if patch_value is None:
            values[column] = None
            continue
        stored_value = current[column]
        if stored_value is not None and not isinstance(stored_value, dict):
            raise InvalidCustomerDataException(f"{name} is not a JSON object")
        values[column] = extension_jsonb(_merge_json(stored_value or {}, patch_value))
    return values
