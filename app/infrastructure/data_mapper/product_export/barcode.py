"""Choose one stored EAN without generating or repairing product identifiers."""

import logging

logger = logging.getLogger(__name__)


def _valid_ean(value: str) -> bool:
    if len(value) not in (8, 13) or not value.isascii() or not value.isdigit():
        return False
    if not value.strip("0"):
        return False
    weighted = sum(
        int(digit) * (3 if index % 2 == 0 else 1)
        for index, digit in enumerate(reversed(value[:-1]))
    )
    return (10 - weighted % 10) % 10 == int(value[-1])


def select_ean(value: object, reference_id: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, list):
        logger.warning(
            "product_export reference_id=%s invalid barcode list", reference_id
        )
        return None
    selected = None
    discarded = 0
    for barcode in value:
        if not isinstance(barcode, str) or not _valid_ean(barcode):
            discarded += 1
        elif selected is None:
            selected = barcode
    if discarded:
        logger.warning(
            "product_export reference_id=%s discarded_barcodes=%s",
            reference_id,
            discarded,
        )
    return selected
