"""Decode legacy JSON and timestamps without inventing missing required data."""

from datetime import UTC, datetime

from app.application.dtos.customer_integration.operations import IntegrationCustomerNote
from app.application.dtos.customer_integration.profile import IntegrationAdditionalEmail
from app.application.exceptions import InvalidCustomerDataException


def required_string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise InvalidCustomerDataException(
            f"Customer export requires a string for {field_name}"
        )
    return value


def required_bool(value: object, field_name: str) -> bool:
    if type(value) is not bool:
        raise InvalidCustomerDataException(
            f"Customer export requires a boolean for {field_name}"
        )
    return value


def objects(value: object, field_name: str) -> list[dict[str, object]]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise InvalidCustomerDataException(
            f"Customer export requires an object array for {field_name}"
        )
    return value


def timestamp(value: object, field_name: str) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            raise InvalidCustomerDataException(
                f"Customer export has an invalid {field_name} timestamp"
            ) from None
    if not isinstance(value, datetime):
        raise InvalidCustomerDataException(
            f"Customer export has an invalid {field_name} timestamp"
        )
    # Incoming synchronization stores UTC wall times in timestamp-without-zone columns.
    return (
        value.replace(tzinfo=UTC)
        if value.utcoffset() is None
        else value.astimezone(UTC)
    )


def additional_emails(value: object) -> tuple[IntegrationAdditionalEmail, ...]:
    result: list[IntegrationAdditionalEmail] = []
    for item in objects(value, "additionalEmails"):
        skype = item.get("skype")
        if skype is not None:
            skype = required_string(skype, "additionalEmails.skype")
        result.append(
            IntegrationAdditionalEmail(
                email=required_string(item.get("email"), "additionalEmails.email"),
                commercial=required_bool(
                    item.get("commercial"), "additionalEmails.commercial"
                ),
                marketing=required_bool(
                    item.get("marketing"), "additionalEmails.marketing"
                ),
                skype=skype,
            )
        )
    return tuple(result)


def notes(value: object) -> tuple[IntegrationCustomerNote, ...]:
    result: list[IntegrationCustomerNote] = []
    for item in objects(value, "notes.items"):
        occurred_at = timestamp(item.get("date"), "notes.items.date")
        if occurred_at is None:
            raise InvalidCustomerDataException(
                "Customer export notes require a timestamp"
            )
        result.append(
            IntegrationCustomerNote(
                occurred_at=occurred_at,
                text=required_string(item.get("note"), "notes.items.text"),
                open=required_bool(item.get("open"), "notes.items.open"),
            )
        )
    return tuple(result)
