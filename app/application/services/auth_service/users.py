from app.application.domain import (
    AuthenticatedUser,
    PrincipalType,
    Role,
    resolve_permissions,
    resolve_product_access_policy,
)


def build_authenticated_user(
    principal_id: int,
    username: str,
    role: Role,
    principal_type: PrincipalType,
    token_id: str,
) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=principal_id,
        username=username,
        role=role,
        principal_type=principal_type,
        token_id=token_id,
        permissions=resolve_permissions(role),
        product_access=resolve_product_access_policy(role, user_id=principal_id),
    )
