"""Serialize exact monetary strings, signed line totals and UTC timestamps."""

from datetime import UTC

from app.application.dtos.order_integration import OrderExportEvent

from .payload import JsonValue


def order_event_payload(event: OrderExportEvent) -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = {
        "schemaVersion": event.schema_version,
        "eventId": str(event.event_id),
        "eventType": event.event_type,
        "occurredAt": event.occurred_at.astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z"),
        "referenceId": event.reference_id,
    }
    if event.data is None:
        return payload
    data = event.data
    invoice, address = data.invoice, data.shipping_address
    payload["data"] = {
        "customerReferenceId": data.customer_reference_id,
        "orderNumber": data.order_number,
        "status": data.status,
        "orderDate": data.order_date.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "invoice": {
            "number": invoice.number,
            "date": invoice.date.isoformat(),
            "url": invoice.url,
        }
        if invoice is not None
        else None,
        "totals": {
            "net": format(data.totals.net, ".2f"),
            "tax": format(data.totals.tax, ".2f"),
            "gross": format(data.totals.gross, ".2f"),
        },
        "shippingAddress": {
            "street": address.street,
            "city": address.city,
            "postalCode": address.postal_code,
            "countryCode": address.country_code,
            "regionName": address.region_name,
        }
        if address is not None
        else None,
        "notes": data.notes,
        "lines": [
            {
                "lineId": line.line_id,
                "productReferenceId": line.product_reference_id,
                "sku": line.sku,
                "description": line.description,
                "quantity": line.quantity,
                "unitPrice": format(line.unit_price, ".2f"),
                "lineTotal": format(line.line_total, ".2f"),
            }
            for line in data.lines
        ],
    }
    return payload
