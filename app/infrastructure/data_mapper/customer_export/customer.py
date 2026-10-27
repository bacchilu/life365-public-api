"""Map every shared customer section from a complete PostgreSQL row."""

from collections.abc import Mapping
from typing import Any

from app.application.dtos.customer_integration import (
    IntegrationBanking,
    IntegrationCommercial,
    IntegrationCommunicationPreferences,
    IntegrationCompany,
    IntegrationCustomerCredentials,
    IntegrationCustomerData,
    IntegrationCustomerExtensions,
    IntegrationCustomerNotes,
    IntegrationDelivery,
    IntegrationOperationalSettings,
    IntegrationPrimaryContact,
    IntegrationRegistration,
    IntegrationShop,
    IntegrationTaxProfile,
)
from app.application.exceptions import InvalidCustomerDataException

from .references import address, agent, categories, groups, sales_channel
from .values import additional_emails, notes, required_bool, required_string, timestamp


def customer_from_row(row: Mapping[str, Any]) -> IntegrationCustomerData:
    for name in ("parameters", "extra_data"):
        if row[name] is not None and not isinstance(row[name], dict):
            raise InvalidCustomerDataException(
                f"Customer export requires an object for {name}"
            )
    if row["delivery_address"] is None and any(
        row[name] is not None for name in ("delivery_city", "delivery_zip_code")
    ):
        raise InvalidCustomerDataException(
            "Customer export has an incomplete delivery address"
        )
    return IntegrationCustomerData(
        credentials=IntegrationCustomerCredentials(
            required_string(row["login"], "credentials.login"),
            required_string(row["pass"], "credentials.password"),
        ),
        company=IntegrationCompany(
            required_string(row["business_name"], "company.name"),
            row["website"],
            row["phone"],
            row["phone2"],
        ),
        primary_contact=IntegrationPrimaryContact(
            full_name=required_string(
                row["business_contact_name"], "primaryContact.fullName"
            ),
            email=required_string(row["email"], "primaryContact.email"),
            additional_emails=additional_emails(row["additional_emails"]),
            certified_email=row["pec"],
            preferred_language=row["preferred_language"],
        ),
        billing_address=address(row),
        delivery=IntegrationDelivery(
            row["delivery_business_name"],
            row["delivery_contact_name"],
            row["delivery_phone"],
            address(row, delivery=True)
            if row["delivery_address"] is not None
            else None,
        ),
        tax_profile=IntegrationTaxProfile(
            fiscal_code=row["fiscal_code"],
            vat_country_code=row["vat_country"],
            vat_number=row["vat_number"],
            vies_validated=required_bool(row["vies"], "taxProfile.viesValidated"),
            fiscal_agent_code=row["fiscal_agent_code"],
            secondary_tax_value=row["tax2"],
        ),
        communication_preferences=IntegrationCommunicationPreferences(
            row["newsletter"], row["reg_privacy"], row["reg_rules"]
        ),
        registration=IntegrationRegistration(
            timestamp(row["registration_date"], "registration.registeredAt"),
            row["verified"],
            timestamp(row["last_login_date"], "registration.lastLoginAt"),
        ),
        commercial=IntegrationCommercial(
            preferred_categories=categories(row["export_categories"]),
            sales_channel=sales_channel(row),
            assigned_agent=agent(row),
            payment_agreement=row["payment_agreement"],
            preferred_payment_type_code=row["preferred_payment_type"],
            payment_days=row["payment_days"],
            payment_days_end_of_month=row["payment_days_eom"],
            credit_granted=row["fido_granted"],
            credit_value=row["fido"],
        ),
        banking=IntegrationBanking(
            row["payment_abi"], row["payment_cab"], row["payment_iban"]
        ),
        shop=IntegrationShop(
            float(row["shop_location_lat"])
            if row["shop_location_lat"] is not None
            else None,
            float(row["shop_location_lng"])
            if row["shop_location_lng"] is not None
            else None,
            groups(row["export_groups"]),
        ),
        operational_settings=IntegrationOperationalSettings(
            required_bool(
                row["disable_box_discount"], "operationalSettings.disableBoxDiscount"
            ),
            row["disable_qty_delivery"],
            row["rma_prepaid"],
            row["disable_limit_sale"],
        ),
        notes=IntegrationCustomerNotes(notes(row["_notes"]), row["admin_note"]),
        extensions=IntegrationCustomerExtensions(row["parameters"], row["extra_data"]),
    )
