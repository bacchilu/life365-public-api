"""Serialize the product contract; remote deactivation carries no data object."""

from datetime import UTC

from app.application.dtos.product_integration import ProductExportEvent

from .payload import JsonValue


def product_event_payload(event: ProductExportEvent) -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = {
        "schemaVersion": event.schema_version,
        "eventId": str(event.event_id),
        "eventType": event.event_type,
        "occurredAt": event.occurred_at.astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z"),
        "referenceId": event.reference_id,
    }
    if event.data is not None:
        data = event.data
        payload["data"] = {
            "sku": data.sku,
            "name": data.name,
            "description": data.description,
            "brand": data.brand,
            "ean": data.ean,
            "category": {"code": data.category.code, "name": data.category.name}
            if data.category is not None
            else None,
            "productUrl": data.product_url,
            "imageUrl": data.image_url,
            "active": data.active,
        }
    return payload
