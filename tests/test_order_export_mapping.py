"""Order mapping is exact and independent of current catalog prices or taxes."""

from copy import deepcopy
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.application.exceptions import InvalidOrderDataException
from app.infrastructure.data_mapper.order_export.order import order_from_rows


def order_row() -> dict[str, object]:
    return {
        "id": 1001,
        "customer_id": 3,
        "resolved_customer_id": 3,
        "order_date": datetime(2026, 11, 6, 10, 30),
        "logistic_state": "CONFIRMED",
        "delivery_cost": Decimal("5.00"),
        "total": Decimal("115.90"),
        "stamp_duty": Decimal("0.00"),
        "invoice_doc_n": 0,
        "invoice_doc_date": None,
        "note": "Deliver in the morning",
        "delivery_address": "Via Roma 10",
        "delivery_city": "Forli",
        "delivery_zip_code": "47121",
        "delivery_region_id": 50,
        "delivery_region_name": "Forli-Cesena",
        "delivery_country_code": "IT",
        "address_street": None,
        "address_city": None,
        "address_zip_code": None,
        "region_id": None,
        "billing_region_name": None,
        "billing_country_code": None,
    }


def order_details() -> list[dict[str, object]]:
    return [
        {
            "id": 5001,
            "product_stock_id": 10001,
            "product_id": 101,
            "isin": "SKU-101",
            "product_description": "Historical product name",
            "qty": 2,
            "price": Decimal("50.00"),
        },
        {
            "id": 5002,
            "product_stock_id": 10002,
            "product_id": 104,
            "isin": "SAVE",
            "product_description": "Box discount",
            "qty": 1,
            "price": Decimal("-10.00"),
        },
    ]


def shipping_products() -> list[dict[str, object]]:
    return [{"id": 124, "isin": "ADMGST"}]


def test_signed_discount_shipping_totals_and_original_values() -> None:
    row, details, shipping = order_row(), order_details(), shipping_products()
    before = deepcopy((row, details, shipping))
    result = order_from_rows(row, details, shipping)
    assert result.order_number == "1001" and result.customer_reference_id == 3
    assert result.status == "CONFIRMED"
    assert result.order_date == datetime(2026, 11, 6, 10, 30, tzinfo=UTC)
    assert result.invoice is None and result.notes == row["note"]
    assert result.shipping_address is not None
    assert result.shipping_address.region_name == "Forli-Cesena"
    assert [
        (line.product_reference_id, line.unit_price, line.line_total)
        for line in result.lines
    ] == [
        (101, Decimal("50.00"), Decimal("100.00")),
        (104, Decimal("10.00"), Decimal("-10.00")),
        (124, Decimal("5.00"), Decimal("5.00")),
    ]
    assert result.lines[2].line_id == "shipping-1001" and result.lines[2].quantity == 1
    assert (result.totals.net, result.totals.tax, result.totals.gross) == (
        Decimal("95.00"),
        Decimal("20.90"),
        Decimal("115.90"),
    )
    assert result.totals.net + result.totals.tax == result.totals.gross
    assert (row, details, shipping) == before


@pytest.mark.parametrize(
    "state", ["CONFIRMED", "DELIVERED", "UNDELIVERABLE", "UNCONFIRMED"]
)
def test_logistic_state_has_no_listing_filter(state: str) -> None:
    row = order_row()
    row["logistic_state"] = state
    assert order_from_rows(row, order_details(), shipping_products()).status == state


def test_no_double_discounts_or_tax2_and_no_current_tax_rate_assumption() -> None:
    row, details = order_row(), order_details()
    row.update(
        delivery_cost=Decimal("0.00"), total=Decimal("112.51"), tax2=Decimal("3.00")
    )
    details[0].update(
        perbox_discount=Decimal("10.00"), row_discount=Decimal("20.00"), qty_box=2
    )
    result = order_from_rows(row, details)
    assert len(result.lines) == 2 and result.totals.net == Decimal("90.00")
    assert result.totals.tax == Decimal("22.51")
    assert result.totals.gross == Decimal("112.51")


def test_utc_conversion_invoice_and_no_fabricated_invoice_url() -> None:
    row = order_row()
    row.update(
        order_date=datetime(2026, 11, 6, 11, 30, tzinfo=timezone(timedelta(hours=1))),
        invoice_doc_n=123,
        invoice_doc_date=date(2026, 11, 6),
    )
    result = order_from_rows(row, order_details(), shipping_products())
    assert result.order_date.hour == 10
    assert result.invoice is not None and result.invoice.number == "123"
    assert result.invoice.date == date(2026, 11, 6) and result.invoice.url is None


def test_absent_address_is_null_billing_snapshot_fallback_is_not_customer_lookup() -> (
    None
):
    row = order_row()
    for key in (
        "delivery_address",
        "delivery_city",
        "delivery_zip_code",
        "delivery_region_id",
    ):
        row[key] = None
    assert (
        order_from_rows(row, order_details(), shipping_products()).shipping_address
        is None
    )
    row.update(
        address_street="Billing snapshot",
        address_city="Forli",
        region_id=50,
        billing_region_name="Forli-Cesena",
        billing_country_code="IT",
    )
    address = order_from_rows(
        row, order_details(), shipping_products()
    ).shipping_address
    assert address is not None and address.street == "Billing snapshot"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("resolved_customer_id", None),
        ("total", None),
        ("total", float("inf")),
        ("total", Decimal("NaN")),
        ("total", Decimal("1.001")),
        ("delivery_cost", Decimal(-1)),
        ("stamp_duty", Decimal(2)),
        ("logistic_state", None),
        ("order_date", None),
        ("delivery_country_code", None),
        ("delivery_region_name", None),
        ("delivery_country_code", "Italy"),
        ("delivery_address", None),
        ("invoice_doc_n", -1),
        ("invoice_doc_n", 123),
        ("invoice_doc_date", date(2026, 1, 1)),
    ],
)
def test_unrepresentable_header_fails(field: str, value: object) -> None:
    row = order_row()
    row[field] = value
    with pytest.raises(InvalidOrderDataException):
        order_from_rows(row, order_details(), shipping_products())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("product_id", None),
        ("isin", None),
        ("qty", 0),
        ("qty", -1),
        ("qty", True),
        ("price", None),
        ("price", 1.1),
        ("product_description", ""),
    ],
)
def test_all_details_must_be_valid_no_silent_inner_join_loss(
    field: str, value: object
) -> None:
    details = order_details()
    details[0][field] = value
    with pytest.raises(InvalidOrderDataException):
        order_from_rows(order_row(), details, shipping_products())


@pytest.mark.parametrize(
    "shipping",
    [
        [],
        [{"id": 124, "isin": "ADMGST"}, {"id": 125, "isin": "ADMGST"}],
        [{"id": 0, "isin": "ADMGST"}],
    ],
)
def test_missing_or_ambiguous_shipping_product_rejected(
    shipping: list[dict[str, object]],
) -> None:
    with pytest.raises(InvalidOrderDataException):
        order_from_rows(order_row(), order_details(), shipping)


def test_empty_order_and_header_stamp_duty_are_not_silently_exported() -> None:
    with pytest.raises(InvalidOrderDataException):
        order_from_rows(order_row(), [], shipping_products())
    row = order_row()
    row["stamp_duty"] = None
    assert order_from_rows(
        row, order_details(), shipping_products()
    ).totals.net == Decimal(95)
