from datetime import datetime, timedelta, timezone

import pytest

from app.application.domain import (
    AuthenticatedUser,
    LoginResult,
    PrincipalIdentity,
    PrincipalType,
    Product,
    Role,
    TokenSession,
    principal_id_to_subject,
    subject_to_principal_id,
)
from app.application.exceptions import AuthenticationException


def test_role_values_are_normalized_runtime_values() -> None:
    assert Role.ADMIN.value == "admin"
    assert Role.BUYER.value == "buyer"
    assert Role.CUSTOMER.value == "customer"


def test_principal_type_values_match_runtime_sources() -> None:
    assert PrincipalType.USER.value == "user"
    assert PrincipalType.CUSTOMER.value == "customer"


def test_auth_domain_objects_can_be_constructed() -> None:
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(days=30)

    user = AuthenticatedUser(
        id=123,
        username="buyer",
        role=Role.BUYER,
        principal_type=PrincipalType.USER,
        token_id="token-id",
    )
    session = TokenSession(
        token_id="token-id",
        principal_id=user.id,
        principal_type=user.principal_type,
        issued_at=issued_at,
        expires_at=expires_at,
    )
    result = LoginResult(
        user=user,
        session=session,
        access_token="opaque-access-token",
    )

    assert result.user == user
    assert result.session == session
    assert result.access_token == "opaque-access-token"
    assert result.session.revoked is False


def test_principal_identity_represents_token_free_identity() -> None:
    identity = PrincipalIdentity(
        id=123,
        username="buyer",
        role=Role.BUYER,
        principal_type=PrincipalType.USER,
    )

    assert identity.id == 123
    assert identity.username == "buyer"
    assert identity.role is Role.BUYER
    assert identity.principal_type is PrincipalType.USER
    assert not hasattr(identity, "token_id")
    assert not hasattr(identity, "access_token")
    assert not hasattr(identity, "session")


def test_product_stays_importable_from_domain_package() -> None:
    product = Product(id=1, vendor_code="vendor", isin="isin")

    assert product.id == 1
    assert product.vendor_code == "vendor"


@pytest.mark.parametrize("source_role", ["ADMIN", "admin", " ADMIN "])
def test_admin_role_normalization(source_role: str) -> None:
    assert Role.from_internal_role(source_role) is Role.ADMIN


@pytest.mark.parametrize("source_role", ["BUYER", "buyer", " BUYER "])
def test_buyer_role_normalization(source_role: str) -> None:
    assert Role.from_internal_role(source_role) is Role.BUYER


@pytest.mark.parametrize("source_role", ["CUSTOMER", "", "unknown"])
def test_unsupported_internal_roles_are_rejected(source_role: str) -> None:
    with pytest.raises(AuthenticationException, match="Invalid credentials"):
        Role.from_internal_role(source_role)


def test_customer_auth_helpers_return_customer_runtime_values() -> None:
    assert Role.from_customer() is Role.CUSTOMER
    assert PrincipalType.from_customer() is PrincipalType.CUSTOMER


def test_internal_user_principal_type_returns_user() -> None:
    assert PrincipalType.from_internal_user() is PrincipalType.USER


def test_principal_id_converts_to_jwt_subject() -> None:
    assert principal_id_to_subject(123) == "123"


def test_jwt_subject_converts_to_runtime_principal_id() -> None:
    assert subject_to_principal_id("123") == 123


@pytest.mark.parametrize("subject", ["", "abc", "0", "-1"])
def test_invalid_jwt_subjects_are_rejected(subject: str) -> None:
    with pytest.raises(AuthenticationException, match="Invalid credentials"):
        subject_to_principal_id(subject)
