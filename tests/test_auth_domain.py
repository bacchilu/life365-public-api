from datetime import datetime, timedelta, timezone

from app.application.domain import (
    AuthenticatedUser,
    LoginResult,
    PrincipalType,
    Product,
    Role,
    TokenSession,
)


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


def test_product_stays_importable_from_domain_package() -> None:
    product = Product(id=1, vendor_code="vendor", isin="isin")

    assert product.id == 1
    assert product.vendor_code == "vendor"
