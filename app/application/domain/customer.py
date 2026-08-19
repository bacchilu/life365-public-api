from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class Customer:
    """Customer account used by the application layer."""

    id: int
    login: str
    email: str
    business_name: str | None = None
    business_contact_name: str | None = None
    preferred_language: str | None = None
    extra_data: dict[str, Any] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)
    last_login_date: datetime | None = None
