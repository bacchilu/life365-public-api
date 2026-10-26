"""Explicit, local-only sandbox configuration; never a production DSN fallback."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values
from psycopg.conninfo import make_conninfo

_ROOT = Path(__file__).resolve().parents[3]


class SandboxConfigurationError(Exception):
    """Configuration errors name fields, never their secret values."""


def _required(values: Mapping[str, str | None], name: str) -> str:
    value = values.get(name)
    if value is None or not value.strip():
        raise SandboxConfigurationError(f"{name} must be configured")
    return value


@dataclass(frozen=True, slots=True)
class SandboxSettings:
    database_connection: str = field(repr=False)
    jwt_secret: str = field(repr=False)
    fingerprint_secret: bytes = field(repr=False)

    @classmethod
    def load(cls) -> "SandboxSettings":
        return cls.from_values({**dotenv_values(_ROOT / ".env"), **os.environ})

    @classmethod
    def from_values(cls, values: Mapping[str, str | None]) -> "SandboxSettings":
        host = _required(values, "SANDBOX_DATABASE_HOST")
        port = _required(values, "SANDBOX_DATABASE_PORT")
        expected_port = "5432" if host == "local-postgres" else "55432"
        if (
            host not in {"localhost", "127.0.0.1", "::1", "local-postgres"}
            or port != expected_port
        ):
            raise SandboxConfigurationError(
                "Sandbox must use the local PostgreSQL service and its local port"
            )
        password = _required(values, "SANDBOX_DB_PASSWORD")
        jwt_secret = _required(values, "SANDBOX_JWT_SECRET_KEY")
        fingerprint = _required(values, "SANDBOX_CUSTOMER_SYNC_FINGERPRINT_SECRET")
        if len(jwt_secret.encode()) < 32 or len(fingerprint.encode()) < 32:
            raise SandboxConfigurationError(
                "Sandbox JWT and fingerprint secrets must each contain at least 32 bytes"
            )
        production_secrets = {
            values.get("JWT_SECRET_KEY"),
            values.get("CUSTOMER_SYNC_FINGERPRINT_SECRET"),
        }
        if (
            jwt_secret in production_secrets
            or fingerprint in production_secrets
            or jwt_secret == fingerprint
        ):
            raise SandboxConfigurationError(
                "Sandbox secrets must be separate from production and from each other"
            )
        return cls(
            database_connection=make_conninfo(
                host=host,
                port=port,
                dbname="life365_sandbox",
                user="sandbox_user",
                password=password,
                connect_timeout=5,
            ),
            jwt_secret=jwt_secret,
            fingerprint_secret=fingerprint.encode(),
        )
