"""PostgreSQL customer writes for Salesforce synchronization."""

from ipaddress import IPv4Address

import psycopg
from psycopg import sql
from psycopg.rows import TupleRow

from app.application.dtos.customer_integration.customer import IntegrationCustomerData
from app.application.dtos.customer_integration.customer_patch import CustomerUpdatedData
from app.application.exceptions import (
    CustomerSynchronizationConflictException,
    InvalidCustomerDataException,
)
from app.application.ports import CustomerSynchronizationGateway

from .create_values import create_customer_direct_values
from .insert import insert_customer_row
from .logins import reserve_customer_login
from .reference_values import resolve_customer_reference_values
from .update import update_customer_row

_CUSTOMER_EXISTS = sql.SQL("SELECT 1 FROM public.customers WHERE id = %s")


class PostgreSQLCustomerDataMapper(CustomerSynchronizationGateway):
    def __init__(
        self, cur: psycopg.AsyncCursor[TupleRow], registration_ip: str | None = None
    ) -> None:
        self._cur = cur
        self._registration_ip = registration_ip

    async def customer_exists(self, reference_id: int) -> bool:
        await self._cur.execute(_CUSTOMER_EXISTS, (reference_id,))
        return await self._cur.fetchone() is not None

    async def get_customer(self, reference_id: int) -> IntegrationCustomerData | None:
        raise NotImplementedError("Full PostgreSQL customer reads are not supported")

    async def create_customer(self, data: IntegrationCustomerData) -> int:
        if self._registration_ip is None:
            raise InvalidCustomerDataException("Client IPv4 address is unavailable")
        try:
            registration_ip = str(IPv4Address(self._registration_ip))
        except ValueError:
            raise InvalidCustomerDataException(
                "Customer registration IP must be IPv4"
            ) from None

        password = data.credentials.password
        if not password or len(password) > 50:
            raise InvalidCustomerDataException(
                "Customer password must contain 1 to 50 characters"
            )
        tax = data.tax_profile
        if not (tax.fiscal_code and tax.fiscal_code.strip()) and not (
            tax.vat_number and tax.vat_number.strip()
        ):
            raise InvalidCustomerDataException(
                "Customer needs a fiscal code or VAT number"
            )

        login = await reserve_customer_login(self._cur, data.credentials.login)
        values = create_customer_direct_values(data)
        values.update(await resolve_customer_reference_values(self._cur, data))
        values["login"] = login
        values["registration_ip"] = registration_ip
        try:
            return await insert_customer_row(self._cur, values)
        except psycopg.errors.UniqueViolation:
            raise CustomerSynchronizationConflictException(
                "Customer create violates a unique constraint"
            ) from None

    async def update_customer(
        self, reference_id: int, data: CustomerUpdatedData
    ) -> None:
        try:
            await update_customer_row(self._cur, reference_id, data)
        except psycopg.errors.UniqueViolation:
            raise CustomerSynchronizationConflictException(
                "Customer update violates a unique constraint"
            ) from None
