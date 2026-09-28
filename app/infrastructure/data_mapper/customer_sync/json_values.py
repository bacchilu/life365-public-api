"""Build JSONB values for synchronized customer fields."""

from typing import Any

from psycopg.types.json import Jsonb

from app.application.dtos.customer_integration.profile import (
    IntegrationAdditionalEmail,
)


def additional_emails_jsonb(
    emails: tuple[IntegrationAdditionalEmail, ...],
) -> Jsonb:
    """Keep every contract key, including false and null values."""
    return Jsonb(
        [
            {
                "email": email.email,
                "commercial": email.commercial,
                "marketing": email.marketing,
                "skype": email.skype,
            }
            for email in emails
        ]
    )


def extension_jsonb(value: dict[str, Any] | None) -> Jsonb | None:
    """Keep SQL NULL separate from an empty JSON object."""
    return Jsonb(value) if value is not None else None
