"""Convert API profile schemas to application DTOs."""

from app.api.integrations.schemas import profile as api_profile
from app.api.integrations.schemas import profile_patch as api_patch
from app.application.dtos.customer_integration import profile as application_profile
from app.application.dtos.customer_integration import (
    profile_patch as application_patch,
)
from app.application.dtos.customer_integration.unset import UNSET, UnsetType


def convert_additional_email(
    source: api_profile.IntegrationAdditionalEmail,
) -> application_profile.IntegrationAdditionalEmail:
    return application_profile.IntegrationAdditionalEmail(
        email=source.email,
        commercial=source.commercial,
        marketing=source.marketing,
        skype=source.skype,
    )


def convert_credentials(
    source: api_profile.IntegrationCustomerCredentials,
) -> application_profile.IntegrationCustomerCredentials:
    return application_profile.IntegrationCustomerCredentials(
        login=source.login,
        password=source.password,
    )


def convert_company(
    source: api_profile.IntegrationCompany,
) -> application_profile.IntegrationCompany:
    return application_profile.IntegrationCompany(
        name=source.name,
        website=source.website,
        primary_phone=source.primary_phone,
        secondary_phone=source.secondary_phone,
    )


def convert_primary_contact(
    source: api_profile.IntegrationPrimaryContact,
) -> application_profile.IntegrationPrimaryContact:
    return application_profile.IntegrationPrimaryContact(
        full_name=source.full_name,
        email=source.email,
        additional_emails=tuple(
            convert_additional_email(email) for email in source.additional_emails
        ),
        certified_email=source.certified_email,
        preferred_language=source.preferred_language,
    )


def convert_communication_preferences(
    source: api_profile.IntegrationCommunicationPreferences,
) -> application_profile.IntegrationCommunicationPreferences:
    return application_profile.IntegrationCommunicationPreferences(
        newsletter=source.newsletter,
        privacy_registered=source.privacy_registered,
        rules_registered=source.rules_registered,
    )


def convert_registration(
    source: api_profile.IntegrationRegistration,
) -> application_profile.IntegrationRegistration:
    return application_profile.IntegrationRegistration(
        registered_at=source.registered_at,
        verified=source.verified,
        last_login_at=source.last_login_at,
    )


def convert_credentials_patch(
    source: api_patch.IntegrationCustomerCredentialsPatch,
) -> application_patch.IntegrationCustomerCredentialsPatch:
    return application_patch.IntegrationCustomerCredentialsPatch(
        login=source.login,
        password=source.password,
    )


def convert_company_patch(
    source: api_patch.IntegrationCompanyPatch,
) -> application_patch.IntegrationCompanyPatch:
    return application_patch.IntegrationCompanyPatch(
        name=source.name,
        website=source.website,
        primary_phone=source.primary_phone,
        secondary_phone=source.secondary_phone,
    )


def convert_primary_contact_patch(
    source: api_patch.IntegrationPrimaryContactPatch,
) -> application_patch.IntegrationPrimaryContactPatch:
    additional_emails: (
        tuple[application_profile.IntegrationAdditionalEmail, ...] | UnsetType
    )
    if isinstance(source.additional_emails, UnsetType):
        additional_emails = UNSET
    else:
        additional_emails = tuple(
            convert_additional_email(email) for email in source.additional_emails
        )

    return application_patch.IntegrationPrimaryContactPatch(
        full_name=source.full_name,
        email=source.email,
        additional_emails=additional_emails,
        certified_email=source.certified_email,
        preferred_language=source.preferred_language,
    )


def convert_communication_preferences_patch(
    source: api_patch.IntegrationCommunicationPreferencesPatch,
) -> application_patch.IntegrationCommunicationPreferencesPatch:
    return application_patch.IntegrationCommunicationPreferencesPatch(
        newsletter=source.newsletter,
        privacy_registered=source.privacy_registered,
        rules_registered=source.rules_registered,
    )


def convert_registration_patch(
    source: api_patch.IntegrationRegistrationPatch,
) -> application_patch.IntegrationRegistrationPatch:
    return application_patch.IntegrationRegistrationPatch(
        registered_at=source.registered_at,
        verified=source.verified,
        last_login_at=source.last_login_at,
    )
