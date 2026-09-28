"""Offline tests for Life365 customer value conversion."""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.application.exceptions import InvalidCustomerDataException
from app.infrastructure.data_mapper.customer_sync.conversions import (
    to_database_coordinate,
    to_database_decimal,
    to_database_iban,
    to_utc_naive_timestamp,
)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("10000.00", "10000.00"),
        ("1.000", "1.00"),
        ("-99999999.99", "-99999999.99"),
    ],
)
def test_decimal_values_fit_numeric_10_2_without_loss(
    source: str, expected: str
) -> None:
    converted = to_database_decimal(
        Decimal(source), precision=10, scale=2, field_name="creditGranted"
    )

    assert converted is not None
    assert str(converted) == expected


def test_tax_decimal_fits_numeric_18_2_limit() -> None:
    converted = to_database_decimal(
        Decimal("9999999999999999.99"),
        precision=18,
        scale=2,
        field_name="secondaryTaxValue",
    )

    assert converted == Decimal("9999999999999999.99")


@pytest.mark.parametrize(
    "source", ["100000000.00", "-100000000.00", "NaN", "Infinity"]
)
def test_out_of_range_or_non_finite_decimal_is_rejected(source: str) -> None:
    with pytest.raises(InvalidCustomerDataException, match="outside numeric range"):
        to_database_decimal(
            Decimal(source), precision=10, scale=2, field_name="creditGranted"
        )


def test_extra_decimal_places_are_not_rounded() -> None:
    with pytest.raises(InvalidCustomerDataException, match="more than 2"):
        to_database_decimal(
            Decimal("1.001"), precision=10, scale=2, field_name="creditGranted"
        )


def test_decimal_with_ten_places_keeps_coordinate_precision() -> None:
    converted = to_database_decimal(
        Decimal("44.2227391234"),
        precision=18,
        scale=10,
        field_name="latitude",
    )

    assert converted == Decimal("44.2227391234")


@pytest.mark.parametrize(
    ("field_name", "source", "expected"),
    [
        ("latitude", 44.2227391234, "44.2227391234"),
        ("longitude", -12.040731, "-12.0407310000"),
        ("latitude", 90.0, "90.0000000000"),
        ("latitude", -90.0, "-90.0000000000"),
        ("longitude", 180.0, "180.0000000000"),
        ("longitude", -180.0, "-180.0000000000"),
    ],
)
def test_coordinates_keep_precision_and_accept_range_limits(
    field_name: str, source: float, expected: str
) -> None:
    converted = to_database_coordinate(source, field_name=field_name)

    assert converted == Decimal(expected)
    assert converted is not None and str(converted) == expected


@pytest.mark.parametrize("field_name", ["latitude", "longitude"])
def test_nullable_coordinate_remains_null(field_name: str) -> None:
    assert to_database_coordinate(None, field_name=field_name) is None


@pytest.mark.parametrize(
    ("field_name", "source"),
    [
        ("latitude", 90.0000000001),
        ("latitude", -90.0000000001),
        ("longitude", 180.0000000001),
        ("longitude", -180.0000000001),
        ("latitude", float("nan")),
        ("longitude", float("inf")),
    ],
)
def test_out_of_range_or_non_finite_coordinate_is_rejected(
    field_name: str, source: float
) -> None:
    with pytest.raises(InvalidCustomerDataException, match="outside its range"):
        to_database_coordinate(source, field_name=field_name)


def test_coordinate_with_more_than_ten_places_is_not_rounded() -> None:
    with pytest.raises(InvalidCustomerDataException, match="more than 10"):
        to_database_coordinate(1.00000000001, field_name="latitude")


def test_unknown_coordinate_field_is_rejected() -> None:
    with pytest.raises(ValueError, match="latitude or longitude"):
        to_database_coordinate(1.0, field_name="altitude")


def test_iban_is_validated_and_compacted() -> None:
    assert to_database_iban("IT60 X054 2811 1010 0000 0123 456") == (
        "IT60X0542811101000000123456"
    )
    assert to_database_iban(None) is None


@pytest.mark.parametrize("value", ["", "NOT-AN-IBAN", "IT60X0542811101000000123457"])
def test_invalid_iban_is_rejected_without_echoing_it(value: str) -> None:
    with pytest.raises(InvalidCustomerDataException) as error:
        to_database_iban(value)

    assert str(error.value) == "banking.iban is invalid"


def test_nullable_values_remain_null() -> None:
    assert (
        to_database_decimal(None, precision=10, scale=2, field_name="creditGranted")
        is None
    )
    assert to_utc_naive_timestamp(None, field_name="registeredAt") is None


def test_timestamp_is_converted_to_utc_without_timezone() -> None:
    local = datetime(2026, 9, 3, 12, 30, tzinfo=timezone(timedelta(hours=2)))

    converted = to_utc_naive_timestamp(local, field_name="registeredAt")

    assert converted == datetime(2026, 9, 3, 10, 30)
    assert converted is not None and converted.tzinfo is None


def test_utc_timestamp_keeps_its_wall_time() -> None:
    utc_value = datetime(2026, 9, 3, 10, 30, tzinfo=UTC)

    assert to_utc_naive_timestamp(
        utc_value, field_name="lastLoginAt"
    ) == datetime(2026, 9, 3, 10, 30)


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(InvalidCustomerDataException, match="UTC offset"):
        to_utc_naive_timestamp(
            datetime(2026, 9, 3, 10, 30), field_name="registeredAt"
        )
