class DBException(Exception):
    """Raised when a database operation fails."""


class AuthenticationException(Exception):
    """Raised when authentication cannot produce a valid runtime principal."""


class AuthorizationException(Exception):
    """Raised when an authenticated principal cannot perform an action."""


class ExternalIntegrationDisabledException(Exception):
    """Raised when an external operation is unavailable in this environment."""


class CustomerSynchronizationException(Exception):
    """Base error for customer synchronization failures."""


class CustomerNotFoundException(CustomerSynchronizationException):
    """Raised when an update refers to a customer that does not exist."""


class InvalidCustomerReferenceException(CustomerSynchronizationException):
    """Raised when a customer reference is not valid."""


class InvalidCustomerDataException(CustomerSynchronizationException):
    """Raised when event data cannot map to a valid Life365 customer."""


class CustomerSynchronizationConflictException(CustomerSynchronizationException):
    """Raised when an event conflicts with the stored customer state."""


class SalesforceConfigurationException(Exception):
    """Raised when the outbound Salesforce connection is not configured."""


class SalesforceRequestException(Exception):
    """Safe upstream failure details, without remote bodies or credentials."""

    def __init__(self, message: str, *, remote_status: int | None = None) -> None:
        super().__init__(message)
        self.remote_status = remote_status


class SalesforceTimeoutException(SalesforceRequestException):
    """The remote outcome may be unknown; the request is not retried."""


class ProductNotFoundException(Exception):
    """The product does not exist in the selected Life365 database."""


class InvalidProductReferenceException(Exception):
    """The Life365 product reference is not a positive integer."""


class InvalidProductDataException(Exception):
    """Product data or a reference cannot be represented in the export contract."""
