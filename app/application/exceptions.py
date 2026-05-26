class DBException(Exception):
    """Raised when a database operation fails."""


class AuthenticationException(Exception):
    """Raised when authentication cannot produce a valid runtime principal."""


class AuthorizationException(Exception):
    """Raised when an authenticated principal cannot perform an action."""
