class DBException(Exception):
    """Raised when a database operation fails."""


class AuthenticationException(Exception):
    """Raised when authentication cannot produce a valid runtime principal."""


class AuthorizationException(Exception):
    """Raised when an authenticated principal cannot perform an action."""


class CustomerSynchronizationException(Exception):
    """Base error for customer synchronization failures."""


class CustomerNotFoundException(CustomerSynchronizationException):
    """Raised when an update refers to a customer that does not exist."""


class InvalidCustomerReferenceException(CustomerSynchronizationException):
    """Raised when a customer reference is not valid."""


class StaleCustomerVersionException(CustomerSynchronizationException):
    """Raised when an event version is older than the stored version."""


class CustomerVersionGapException(CustomerSynchronizationException):
    """Raised when one or more customer event versions are missing."""


class CustomerSynchronizationConflictException(CustomerSynchronizationException):
    """Raised when an event conflicts with the stored customer state."""
