"""Prepare direct customer columns for a synchronization create."""

from app.application.dtos.customer_integration.customer import IntegrationCustomerData

from .conversions import (
    to_database_coordinate,
    to_database_decimal,
    to_database_iban,
    to_utc_naive_timestamp,
)
from .json_values import additional_emails_jsonb, extension_jsonb
from .notes import notes_jsonb, open_notes_count


def create_customer_direct_values(data: IntegrationCustomerData) -> dict[str, object]:
    """Build columns that need no reference lookup or undecided business rule."""
    delivery_address = data.delivery.address

    return {
        "login": data.credentials.login.strip(),
        "pass": data.credentials.password,
        "business_name": data.company.name,
        "website": data.company.website,
        "phone": data.company.primary_phone,
        "phone2": data.company.secondary_phone,
        "business_contact_name": data.primary_contact.full_name,
        "email": data.primary_contact.email,
        "additional_emails": additional_emails_jsonb(
            data.primary_contact.additional_emails
        ),
        "pec": data.primary_contact.certified_email,
        "preferred_language": data.primary_contact.preferred_language,
        "address_street": data.billing_address.street,
        "address_city": data.billing_address.city,
        "address_zip_code": data.billing_address.postal_code,
        "delivery_business_name": data.delivery.business_name,
        "delivery_contact_name": data.delivery.contact_name,
        "delivery_phone": data.delivery.phone,
        "delivery_address": delivery_address.street if delivery_address else None,
        "delivery_city": delivery_address.city if delivery_address else None,
        "delivery_zip_code": (
            delivery_address.postal_code if delivery_address else None
        ),
        "fiscal_code": data.tax_profile.fiscal_code,
        "vat_country": (
            data.tax_profile.vat_country_code.upper()
            if data.tax_profile.vat_country_code is not None
            else None
        ),
        "vat_number": data.tax_profile.vat_number,
        "vies": data.tax_profile.vies_validated,
        "fiscal_agent_code": data.tax_profile.fiscal_agent_code,
        "tax2": to_database_decimal(
            data.tax_profile.secondary_tax_value,
            precision=18,
            scale=2,
            field_name="secondaryTaxValue",
        ),
        "newsletter": data.communication_preferences.newsletter,
        "reg_privacy": data.communication_preferences.privacy_registered,
        "reg_rules": data.communication_preferences.rules_registered,
        "registration_date": to_utc_naive_timestamp(
            data.registration.registered_at, field_name="registeredAt"
        ),
        "verified": data.registration.verified,
        "last_login_date": to_utc_naive_timestamp(
            data.registration.last_login_at, field_name="lastLoginAt"
        ),
        "payment_agreement": data.commercial.payment_agreement,
        "payment_days": data.commercial.payment_days,
        "payment_days_eom": data.commercial.payment_days_end_of_month,
        "fido_granted": to_database_decimal(
            data.commercial.credit_granted,
            precision=10,
            scale=2,
            field_name="creditGranted",
        ),
        "fido": to_database_decimal(
            data.commercial.credit_value,
            precision=10,
            scale=2,
            field_name="creditValue",
        ),
        "payment_abi": data.banking.abi,
        "payment_cab": data.banking.cab,
        "payment_iban": to_database_iban(data.banking.iban),
        "shop_location_lat": to_database_coordinate(
            data.shop.latitude, field_name="latitude"
        ),
        "shop_location_lng": to_database_coordinate(
            data.shop.longitude, field_name="longitude"
        ),
        "disable_box_discount": data.operational_settings.disable_box_discount,
        "disable_qty_delivery": data.operational_settings.disable_quantity_delivery,
        "rma_prepaid": data.operational_settings.prepaid_returns,
        "disable_limit_sale": data.operational_settings.disable_sale_limit,
        "_notes": notes_jsonb(data.notes.items),
        "notes_open": open_notes_count(data.notes.items),
        "admin_note": data.notes.administrative_note,
        "parameters": extension_jsonb(data.extensions.parameters),
        "extra_data": extension_jsonb(data.extensions.extra_data),
    }
