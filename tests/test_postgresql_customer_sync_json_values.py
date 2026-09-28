"""Offline tests for customer JSONB values."""

from psycopg.types.json import Jsonb

from app.application.dtos.customer_integration.profile import (
    IntegrationAdditionalEmail,
)
from app.infrastructure.data_mapper.customer_sync.json_values import (
    additional_emails_jsonb,
    extension_jsonb,
)


def test_empty_additional_emails_remain_an_empty_json_array() -> None:
    value = additional_emails_jsonb(())

    assert isinstance(value, Jsonb)
    assert value.obj == []


def test_additional_emails_keep_all_keys_and_false_and_null() -> None:
    emails = (
        IntegrationAdditionalEmail(
            email="sales@example.com",
            commercial=True,
            marketing=False,
            skype=None,
        ),
        IntegrationAdditionalEmail(
            email="news@example.com",
            commercial=False,
            marketing=True,
            skype="news-contact",
        ),
    )

    value = additional_emails_jsonb(emails)

    assert value.obj == [
        {
            "email": "sales@example.com",
            "commercial": True,
            "marketing": False,
            "skype": None,
        },
        {
            "email": "news@example.com",
            "commercial": False,
            "marketing": True,
            "skype": "news-contact",
        },
    ]


def test_extension_sql_null_differs_from_empty_json_object() -> None:
    empty = extension_jsonb({})

    assert extension_jsonb(None) is None
    assert isinstance(empty, Jsonb)
    assert empty.obj == {}


def test_extension_keeps_nested_json_values() -> None:
    source = {"flag": False, "nested": {"cleared": None, "items": []}}

    value = extension_jsonb(source)

    assert isinstance(value, Jsonb)
    assert value.obj == source
