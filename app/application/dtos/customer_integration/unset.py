"""Represent omitted application patch fields independently of their values."""

from enum import Enum
from typing import Final, NoReturn


class UnsetType(Enum):
    """An omission marker whose identity is preserved when copied."""

    UNSET = "UNSET"

    def __repr__(self) -> str:
        return "UNSET"

    def __bool__(self) -> NoReturn:
        raise TypeError("Use 'is UNSET' or 'is not UNSET' to check patch presence")


UNSET: Final[UnsetType] = UnsetType.UNSET
