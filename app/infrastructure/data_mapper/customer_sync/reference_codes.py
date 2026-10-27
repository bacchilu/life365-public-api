"""One code catalog for both incoming references and outgoing customer reads."""

from collections.abc import Mapping

from app.application.exceptions import InvalidCustomerDataException

CATEGORY_IDS_BY_CODE: dict[str, int] = {
    "cartridge-toner": 1,
    "smart-solutions": 2,
    "networking": 14,
    "myphone": 23,
    "solar-energy": 25,
    "lighting": 27,
    "electric-parts": 28,
    "special-business": 29,
    "power-tools": 30,
}
SALES_CHANNEL_IDS_BY_CODE: dict[str, int] = {
    f"N{number}": number for number in (*range(1, 16), 18, 19, 20, 21, 22)
}
SHOP_GROUP_IDS_BY_CODE: dict[str, int] = {
    "rei-la-rete": 1,
    "geser-prodigix": 2,
    "professional-group": 3,
    "closed-activity": 36,
}


def code_for_id(catalog: Mapping[str, int], reference_id: int, field_name: str) -> str:
    for code, local_id in catalog.items():
        if reference_id == local_id:
            return code
    raise InvalidCustomerDataException(
        f"Customer export has an unsupported {field_name} reference"
    )
