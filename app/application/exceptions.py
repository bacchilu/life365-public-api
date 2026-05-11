class DBException(Exception):
    """Raised when a database operation fails."""


class AuthenticationException(Exception):
    """Raised when authentication cannot produce a valid runtime principal."""
