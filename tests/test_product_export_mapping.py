"""Product mapping is deterministic and never repairs or invents identifiers."""

import logging

import pytest

from app.application.exceptions import InvalidProductDataException
from app.infrastructure.data_mapper.product_export.barcode import select_ean
from app.infrastructure.data_mapper.product_export.product import product_from_row


def product_row() -> dict[str, object]:
    return {
        "id": 101,
        "isin": "SAMLTD116L",
        "titles": {"it": "Toner", "en": "English toner"},
        "descriptions": {"it": "Descrizione", "en": "Description"},
        "enabled": True,
        "barcodes": ["0700443238779"],
        "brand_id": 1,
        "resolved_brand_id": 1,
        "brand_name": "Sample Brand",
        "selected_category_id": 1005,
        "resolved_category_id": 1005,
        "category_names": {"it": "Samsung Laserjet"},
        "image_url": "https://example.com/products/101.png",
    }


def test_complete_minimal_mapping() -> None:
    data = product_from_row(product_row())
    assert data.sku == "SAMLTD116L" and data.name == "Toner"
    assert data.description == "Descrizione" and data.brand == "Sample Brand"
    assert data.ean == "0700443238779"
    assert data.category is not None
    assert (data.category.code, data.category.name) == ("1005", "Samsung Laserjet")
    assert data.product_url == "https://b2b.life365.eu/p/-101"
    assert data.image_url == "https://example.com/products/101.png"
    assert data.active is True


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (["0700443238779", "0700443238953"], "0700443238779"),
        (["", "0000000000000", "0700443238778", "0700443238779"], "0700443238779"),
        (["96385074", "0700443238779"], "96385074"),
        (["00000000", "0000000000000"], None),
        (["１２３４５６７８", "letters", "0700 443238779", " 0700443238779 "], None),
        ([700443238779, None, False], None),
        ([], None),
        (None, None),
        ({"barcode": "0700443238779"}, None),
        (["036000291452", "10012345000017"], None),
    ],
)
def test_first_valid_stored_ean_preserves_order_and_leading_zeroes(
    value: object, expected: str | None
) -> None:
    assert select_ean(value, 101) == expected


def test_invalid_barcodes_are_logged_without_blocking_export(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        assert select_ean(["invalid", "0700443238779"], 101) == "0700443238779"
    assert "reference_id=101" in caplog.text and "discarded_barcodes=1" in caplog.text


def test_language_fallback_and_nullable_metadata() -> None:
    row = product_row()
    row.update(
        titles={"it": " ", "en": "English"},
        descriptions=None,
        enabled=None,
        brand_id=None,
        resolved_brand_id=None,
        brand_name=None,
        selected_category_id=None,
        resolved_category_id=None,
        category_names=None,
        image_url=None,
        barcodes=[],
    )
    data = product_from_row(row)
    assert data.name == "English" and data.active is False
    assert (
        data.description
        is data.brand
        is data.ean
        is data.category
        is data.image_url
        is None
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"titles": {"pt": "Only Portuguese"}},
        {"isin": " "},
        {"titles": {"it": "x" * 256}},
        {"descriptions": {"it": "x" * 4001}},
        {"resolved_brand_id": None},
        {"brand_name": ""},
        {"resolved_category_id": None},
        {"selected_category_id": 0},
        {"category_names": {"pt": "Missing selected language"}},
        {"titles": []},
        {"titles": {"it": 5}},
        {"enabled": "true"},
    ],
)
def test_invalid_metadata_is_not_silently_discarded(changes: dict[str, object]) -> None:
    with pytest.raises(InvalidProductDataException):
        product_from_row({**product_row(), **changes})
