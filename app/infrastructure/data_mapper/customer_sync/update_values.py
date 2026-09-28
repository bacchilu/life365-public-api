"""Convert supplied customer patch fields to PostgreSQL column values."""

from typing import Any

from app.application.dtos.customer_integration.customer_patch import CustomerUpdatedData
from app.application.dtos.customer_integration.unset import UNSET
from app.application.exceptions import InvalidCustomerDataException

from .conversions import (
    to_database_coordinate,
    to_database_decimal,
    to_database_iban,
    to_utc_naive_timestamp,
)
from .json_values import additional_emails_jsonb
from .notes import notes_jsonb, open_notes_count

_DIRECT_FIELDS = {
    "credentials": {"password": "pass"},
    "company": {
        "name": "business_name",
        "website": "website",
        "primary_phone": "phone",
        "secondary_phone": "phone2",
    },
    "primary_contact": {
        "full_name": "business_contact_name",
        "email": "email",
        "additional_emails": "additional_emails",
        "certified_email": "pec",
        "preferred_language": "preferred_language",
    },
    "billing_address": {
        "street": "address_street",
        "city": "address_city",
        "postal_code": "address_zip_code",
    },
    "delivery": {
        "business_name": "delivery_business_name",
        "contact_name": "delivery_contact_name",
        "phone": "delivery_phone",
    },
    "tax_profile": {
        "fiscal_code": "fiscal_code",
        "vat_country_code": "vat_country",
        "vat_number": "vat_number",
        "vies_validated": "vies",
        "fiscal_agent_code": "fiscal_agent_code",
        "secondary_tax_value": "tax2",
    },
    "communication_preferences": {
        "newsletter": "newsletter",
        "privacy_registered": "reg_privacy",
        "rules_registered": "reg_rules",
    },
    "registration": {
        "registered_at": "registration_date",
        "verified": "verified",
        "last_login_at": "last_login_date",
    },
    "commercial": {
        "payment_agreement": "payment_agreement",
        "payment_days": "payment_days",
        "payment_days_end_of_month": "payment_days_eom",
        "credit_granted": "fido_granted",
        "credit_value": "fido",
    },
    "banking": {
        "abi": "payment_abi",
        "cab": "payment_cab",
        "iban": "payment_iban",
    },
    "shop": {"latitude": "shop_location_lat", "longitude": "shop_location_lng"},
    "operational_settings": {
        "disable_box_discount": "disable_box_discount",
        "disable_quantity_delivery": "disable_qty_delivery",
        "prepaid_returns": "rma_prepaid",
        "disable_sale_limit": "disable_limit_sale",
    },
    "notes": {"administrative_note": "admin_note"},
}


def _convert_value(section: str, name: str, value: Any) -> object:
    key = section, name
    if key == ("credentials", "password"):
        if not value or len(value) > 50:
            raise InvalidCustomerDataException(
                "Customer password must contain 1 to 50 characters"
            )
    elif key == ("primary_contact", "additional_emails"):
        return additional_emails_jsonb(value)
    elif key == ("tax_profile", "vat_country_code"):
        return value.upper() if value is not None else None
    elif key == ("tax_profile", "secondary_tax_value"):
        return to_database_decimal(
            value, precision=18, scale=2, field_name="secondaryTaxValue"
        )
    elif key in (("registration", "registered_at"), ("registration", "last_login_at")):
        field_name = "registeredAt" if name == "registered_at" else "lastLoginAt"
        return to_utc_naive_timestamp(value, field_name=field_name)
    elif key in (("commercial", "credit_granted"), ("commercial", "credit_value")):
        field_name = "creditGranted" if name == "credit_granted" else "creditValue"
        return to_database_decimal(
            value, precision=10, scale=2, field_name=field_name
        )
    elif key == ("banking", "iban"):
        return to_database_iban(value)
    elif key in (("shop", "latitude"), ("shop", "longitude")):
        return to_database_coordinate(value, field_name=name)
    return value


def customer_direct_update_values(data: CustomerUpdatedData) -> dict[str, object]:
    values: dict[str, object] = {}
    for section_name, columns in _DIRECT_FIELDS.items():
        section = getattr(data, section_name)
        if section is UNSET:
            continue
        for field_name, column in columns.items():
            value = getattr(section, field_name)
            if value is not UNSET:
                values[column] = _convert_value(section_name, field_name, value)

    if data.notes is not UNSET and data.notes.items is not UNSET:
        values["_notes"] = notes_jsonb(data.notes.items)
        values["notes_open"] = open_notes_count(data.notes.items)
    return values
