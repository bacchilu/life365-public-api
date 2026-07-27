from collections.abc import Mapping
from typing import Protocol

from app.application.domain import PrincipalIdentity, Product, TokenSession


class CheckGateway(Protocol):
    async def check_db(self) -> bool: ...


class ProductsGateway(Protocol):
    async def get_products(
        self, limit: int = 100, offset: int = 0
    ) -> list[Product]: ...

    async def get_product(self, product_id: int) -> Product: ...


class CredentialsGateway(Protocol):
    async def authenticate_internal_user(
        self, username: str, password: str
    ) -> PrincipalIdentity: ...

    async def authenticate_customer(
        self, username: str, password: str
    ) -> PrincipalIdentity: ...


class TokenSessionGateway(Protocol):
    async def register_token_session(self, session: TokenSession) -> None: ...

    async def get_token_session(self, token_id: str) -> TokenSession | None: ...

    async def is_token_known(self, token_id: str) -> bool: ...

    async def is_token_revoked(self, token_id: str) -> bool: ...

    async def revoke_token(self, token_id: str) -> None: ...


class TokenCodec(Protocol):
    def encode(self, claims: Mapping[str, object]) -> str: ...

    def decode(self, token: str) -> Mapping[str, object]: ...
