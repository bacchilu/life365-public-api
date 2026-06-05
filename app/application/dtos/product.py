from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.application.domain import Product


@dataclass(slots=True)
class ProductDTO:
    id: int
    vendor_code: str
    isin: str
    titles: dict[str, str] = field(default_factory=dict)
    descriptions: dict[str, str] = field(default_factory=dict)
    brand_id: int | None = None
    owner_id: int | None = None
    level_1: int | None = None
    level_2: int | None = None
    level_3: int | None = None
    enabled: bool = False
    featured: bool = False
    qty_box: int = 1
    weight_gr: int = 0
    dim_length_mm: int | None = None
    dim_width_mm: int | None = None
    dim_height_mm: int | None = None
    color: str | None = None
    certificate: str | None = None
    type1: str | None = None
    type2: str | None = None
    barcodes: tuple[str, ...] = ()
    extra_specs: dict[str, Any] = field(default_factory=dict)
    keywords: dict[str, Any] = field(default_factory=dict)
    excluded_countries: tuple[int, ...] = ()
    creation_date: datetime | None = None
    last_update: int = 0


def product_to_dto(product: Product) -> ProductDTO:
    return ProductDTO(
        id=product.id,
        vendor_code=product.vendor_code,
        isin=product.isin,
        titles=product.titles,
        descriptions=product.descriptions,
        brand_id=product.brand_id,
        owner_id=product.owner_id,
        level_1=product.level_1,
        level_2=product.level_2,
        level_3=product.level_3,
        enabled=product.enabled,
        featured=product.featured,
        qty_box=product.qty_box,
        weight_gr=product.weight_gr,
        dim_length_mm=product.dim_length_mm,
        dim_width_mm=product.dim_width_mm,
        dim_height_mm=product.dim_height_mm,
        color=product.color,
        certificate=product.certificate,
        type1=product.type1,
        type2=product.type2,
        barcodes=product.barcodes,
        extra_specs=product.extra_specs,
        keywords=product.keywords,
        excluded_countries=product.excluded_countries,
        creation_date=product.creation_date,
        last_update=product.last_update,
    )
