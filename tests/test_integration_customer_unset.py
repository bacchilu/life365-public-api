import pickle
import subprocess
import sys
from copy import copy, deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path

import pytest

from app.application.dtos.customer_integration.unset import UNSET, UnsetType


@dataclass(frozen=True, slots=True)
class _PatchExample:
    value: object = UNSET


def test_omitted_patch_field_uses_unset() -> None:
    patch = _PatchExample()

    assert patch.value is UNSET
    assert isinstance(patch.value, UnsetType)


@pytest.mark.parametrize(
    "value",
    [None, False, 0, "", [], (), "UNSET"],
    ids=["null", "false", "zero", "empty-string", "empty-list", "empty-tuple", "text"],
)
def test_explicit_values_remain_distinct_from_omission(value: object) -> None:
    patch = _PatchExample(value=value)

    assert patch.value is value
    assert patch.value is not UNSET
    assert patch.value != UNSET


def test_copying_preserves_unset_identity() -> None:
    patch = _PatchExample()

    assert copy(UNSET) is UNSET
    assert deepcopy(UNSET) is UNSET
    assert copy(patch).value is UNSET
    assert deepcopy(patch).value is UNSET


def test_dataclass_dictionary_conversion_preserves_omission_and_null() -> None:
    assert asdict(_PatchExample())["value"] is UNSET
    assert asdict(_PatchExample(value=None))["value"] is None


def test_pickle_round_trip_preserves_unset_identity() -> None:
    assert pickle.loads(pickle.dumps(UNSET)) is UNSET


def test_boolean_checks_require_explicit_identity_comparison() -> None:
    with pytest.raises(TypeError, match="Use 'is UNSET' or 'is not UNSET'"):
        bool(UNSET)


def test_patch_representation_identifies_omitted_fields() -> None:
    assert repr(UNSET) == "UNSET"
    assert repr(_PatchExample()) == "_PatchExample(value=UNSET)"


def test_unset_imports_without_third_party_packages() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-S",
            "-c",
            "from app.application.dtos.customer_integration.unset import UNSET",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
