"""Translate existing catalog data to the shared minimal product contract."""

from collections.abc import Mapping

from app.application.dtos.product_integration import (
    IntegrationProductCategory,
    IntegrationProductData,
)
from app.application.exceptions import InvalidProductDataException

from .barcode import select_ean

PRODUCT_PAGE_BASE_URL = "https://b2b.life365.eu"


def _text(value: object, field: str, *, limit: int | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidProductDataException(f"Product {field} must contain text")
    if limit is not None and len(value) > limit:
        raise InvalidProductDataException(f"Product {field} exceeds {limit} characters")
    return value


def _localized(value: object, field: str, *, required: bool = False) -> str | None:
    if value is not None and not isinstance(value, dict):
        raise InvalidProductDataException(f"Product {field} must be a language map")
    for language in ("it", "en"):
        candidate = value.get(language) if isinstance(value, dict) else None
        if candidate is not None and not isinstance(candidate, str):
            raise InvalidProductDataException(
                f"Product {field}.{language} must be text"
            )
        if isinstance(candidate, str) and candidate.strip():
            return candidate
    if required:
        raise InvalidProductDataException(
            f"Product {field} has no Italian or English text"
        )
    return None


def product_from_row(row: Mapping[str, object]) -> IntegrationProductData:
    reference_id = row["id"]
    if type(reference_id) is not int or reference_id <= 0:
        raise InvalidProductDataException("Invalid stored product ID")
    name = _text(_localized(row["titles"], "titles", required=True), "name", limit=255)
    description = _localized(row["descriptions"], "descriptions")
    if description is not None:
        description = _text(description, "description", limit=4000)
    brand = None
    brand_id = row["brand_id"]
    if brand_id is not None:
        if (
            type(brand_id) is not int
            or brand_id <= 0
            or brand_id != row["resolved_brand_id"]
        ):
            raise InvalidProductDataException("Product refers to an unknown brand")
        brand = _text(row["brand_name"], "brand")
    category = None
    category_id = row["selected_category_id"]
    if category_id is not None:
        if (
            type(category_id) is not int
            or category_id <= 0
            or category_id != row["resolved_category_id"]
        ):
            raise InvalidProductDataException("Product refers to an unknown category")
        category = IntegrationProductCategory(
            code=str(category_id),
            name=_text(
                _localized(row["category_names"], "category", required=True),
                "category name",
            ),
        )
    enabled = row["enabled"]
    if enabled is not None and type(enabled) is not bool:
        raise InvalidProductDataException("Product enabled must be a boolean or null")
    image = row["image_url"]
    return IntegrationProductData(
        sku=_text(row["isin"], "sku", limit=255),
        name=name,
        description=description,
        brand=brand,
        ean=select_ean(row["barcodes"], reference_id),
        category=category,
        product_url=f"{PRODUCT_PAGE_BASE_URL}/p/-{reference_id}",
        image_url=_text(image, "image URL") if image is not None else None,
        active=enabled if enabled is not None else False,
    )
