"""Convert integration values for Life365 customer columns."""

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from schwifty import IBAN
from schwifty.exceptions import SchwiftyException

from app.application.exceptions import InvalidCustomerDataException


def to_database_decimal(
    value: Decimal | None,
    *,
    precision: int,
    scale: int,
    field_name: str,
) -> Decimal | None:
    """Fit an exact decimal into a PostgreSQL numeric column."""
    if value is None:
        return None

    quantum = Decimal(1).scaleb(-scale)
    maximum = Decimal(10) ** (precision - scale) - quantum
    if not value.is_finite() or value.copy_abs() > maximum:
        raise InvalidCustomerDataException(f"{field_name} is outside numeric range")

    try:
        converted = value.quantize(quantum)
    except InvalidOperation as exc:
        raise InvalidCustomerDataException(
            f"{field_name} cannot fit numeric({precision},{scale})"
        ) from exc
    if converted != value:
        raise InvalidCustomerDataException(
            f"{field_name} has more than {scale} decimal places"
        )
    return converted


def to_utc_naive_timestamp(
    value: datetime | None, *, field_name: str
) -> datetime | None:
    """Store a timezone-aware instant as a UTC wall time."""
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidCustomerDataException(f"{field_name} needs a UTC offset")
    return value.astimezone(UTC).replace(tzinfo=None)


def to_database_coordinate(
    value: float | None, *, field_name: str
) -> Decimal | None:
    """Fit a latitude or longitude into numeric(18,10) without rounding."""
    if value is None:
        return None
    if field_name not in ("latitude", "longitude"):
        raise ValueError("Coordinate field must be latitude or longitude")

    try:
        coordinate = Decimal(str(value))
    except InvalidOperation as exc:
        raise InvalidCustomerDataException(f"{field_name} is not numeric") from exc

    maximum = 90 if field_name == "latitude" else 180
    if not coordinate.is_finite() or coordinate.copy_abs() > maximum:
        raise InvalidCustomerDataException(f"{field_name} is outside its range")
    return to_database_decimal(
        coordinate, precision=18, scale=10, field_name=field_name
    )


def to_database_iban(value: str | None) -> str | None:
    """Validate and compact an IBAN using the existing Life365 rule."""
    if value is None:
        return None
    try:
        compact = IBAN(value).compact
    except SchwiftyException:
        raise InvalidCustomerDataException("banking.iban is invalid") from None
    if len(compact) > 34:
        raise InvalidCustomerDataException("banking.iban exceeds 34 characters")
    return compact
