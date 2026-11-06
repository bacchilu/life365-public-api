"""Preserve signed stored prices and the actual historical gross total."""

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal, localcontext

from app.application.dtos.customer_integration.address import IntegrationAddress
from app.application.dtos.order_integration import (
    IntegrationOrderData,
    IntegrationOrderInvoice,
    IntegrationOrderLine,
    IntegrationOrderTotals,
)
from app.application.exceptions import InvalidOrderDataException

from .values import identifier, money, text, timestamp


def _address(row: Mapping[str, object]) -> IntegrationAddress | None:
    for street, city, postal, region_id, region_name, country in (
        (
            "delivery_address",
            "delivery_city",
            "delivery_zip_code",
            "delivery_region_id",
            "delivery_region_name",
            "delivery_country_code",
        ),
        (
            "address_street",
            "address_city",
            "address_zip_code",
            "region_id",
            "billing_region_name",
            "billing_country_code",
        ),
    ):
        if all(row[key] is None for key in (street, city, postal, region_id)):
            continue
        code = text(row[country], "shipping country")
        if (
            len(code) != 2
            or not code.isascii()
            or not code.isalpha()
            or code != code.upper()
        ):
            raise InvalidOrderDataException(
                "Order shipping country must be an ISO alpha-2 code"
            )
        zip_code = row[postal]
        if zip_code is not None and not isinstance(zip_code, str):
            raise InvalidOrderDataException(
                "Order shipping postal code must be text or null"
            )
        return IntegrationAddress(
            street=text(row[street], "shipping street"),
            city=text(row[city], "shipping city"),
            postal_code=zip_code,
            country_code=code,
            region_name=text(row[region_name], "shipping region"),
        )
    return None


def _invoice(row: Mapping[str, object]) -> IntegrationOrderInvoice | None:
    number, issued = row["invoice_doc_n"], row["invoice_doc_date"]
    if number is None or number == 0:
        if issued is not None:
            raise InvalidOrderDataException("Order invoice date has no invoice number")
        return None
    identifier(number, "invoice number")
    if not isinstance(issued, date) or isinstance(issued, datetime):
        raise InvalidOrderDataException("Order invoice number requires an invoice date")
    return IntegrationOrderInvoice(number=str(number), date=issued)


def order_from_rows(
    row: Mapping[str, object],
    details: Sequence[Mapping[str, object]],
    shipping_products: Sequence[Mapping[str, object]] = (),
) -> IntegrationOrderData:
    reference_id = identifier(row["id"], "ID")
    customer_id = identifier(row["customer_id"], "customer reference")
    if row["resolved_customer_id"] != customer_id:
        raise InvalidOrderDataException("Order refers to an unknown customer")
    if row["stamp_duty"] is not None and money(row["stamp_duty"], "stamp duty") != 0:
        raise InvalidOrderDataException(
            "Order header stamp duty is not supported; its inclusion in the stored total must be resolved first"
        )
    if not details:
        raise InvalidOrderDataException("Order must have at least one detail line")
    lines: list[IntegrationOrderLine] = []
    with localcontext() as context:
        context.prec = 50
        for detail in details:
            price = money(detail["price"], "line price")
            quantity = identifier(detail["qty"], "line quantity")
            lines.append(
                IntegrationOrderLine(
                    line_id=str(identifier(detail["id"], "line ID")),
                    product_reference_id=identifier(
                        detail["product_id"], "line product reference"
                    ),
                    sku=text(detail["isin"], "line SKU"),
                    description=text(detail["product_description"], "line description"),
                    quantity=quantity,
                    unit_price=abs(price),
                    line_total=price * quantity,
                )
            )
        delivery = money(row["delivery_cost"], "delivery cost")
        if delivery < 0:
            raise InvalidOrderDataException("Order delivery cost cannot be negative")
        if delivery != 0:
            if len(shipping_products) != 1:
                raise InvalidOrderDataException(
                    "Order shipping requires exactly one ADMGST product in the selected database"
                )
            product = shipping_products[0]
            if product["isin"] != "ADMGST":
                raise InvalidOrderDataException("Order shipping product must be ADMGST")
            lines.append(
                IntegrationOrderLine(
                    line_id=f"shipping-{reference_id}",
                    product_reference_id=identifier(
                        product["id"], "shipping product reference"
                    ),
                    sku="ADMGST",
                    description="Spese di spedizione",
                    quantity=1,
                    unit_price=delivery,
                    line_total=delivery,
                )
            )
        net = sum((line.line_total for line in lines), Decimal("0.00"))
        gross = money(row["total"], "gross total")
        # Preserve stored combined taxes, including tax2 and original rounding.
        totals = IntegrationOrderTotals(net=net, tax=gross - net, gross=gross)
    notes = row["note"]
    if notes is not None and not isinstance(notes, str):
        raise InvalidOrderDataException("Order notes must be text or null")
    return IntegrationOrderData(
        customer_reference_id=customer_id,
        order_number=str(reference_id),
        status=text(row["logistic_state"], "logistic state"),
        order_date=timestamp(row["order_date"]),
        invoice=_invoice(row),
        totals=totals,
        shipping_address=_address(row),
        notes=notes,
        lines=tuple(lines),
    )
