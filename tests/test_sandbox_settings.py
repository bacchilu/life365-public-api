"""Sandbox configuration must fail closed without production fallbacks."""

import os

import pytest
from psycopg.conninfo import conninfo_to_dict

from app.api.sandbox import settings as settings_module
from app.api.sandbox.settings import SandboxConfigurationError, SandboxSettings


def _values() -> dict[str, str]:
    return {
        "SANDBOX_DATABASE_HOST": "127.0.0.1",
        "SANDBOX_DATABASE_PORT": "55432",
        "SANDBOX_DB_PASSWORD": "local password:@/'",
        "SANDBOX_JWT_SECRET_KEY": "sandbox-jwt-secret-for-tests-32-bytes",
        "SANDBOX_CUSTOMER_SYNC_FINGERPRINT_SECRET": "sandbox-event-secret-for-tests-32-bytes",
        "DATABASE_URL": "postgresql://production.invalid/business",
        "JWT_SECRET_KEY": "production-jwt-secret-for-tests-32-bytes",
        "CUSTOMER_SYNC_FINGERPRINT_SECRET": "production-event-secret-for-tests-32-bytes",
    }


@pytest.mark.parametrize(
    ("host", "port"),
    [
        ("127.0.0.1", "55432"),
        ("localhost", "55432"),
        ("::1", "55432"),
        ("local-postgres", "5432"),
    ],
)
def test_only_explicit_native_and_docker_sandbox_connections(
    host: str, port: str
) -> None:
    values = {**_values(), "SANDBOX_DATABASE_HOST": host, "SANDBOX_DATABASE_PORT": port}
    settings = SandboxSettings.from_values(values)
    connection = conninfo_to_dict(settings.database_connection)
    assert connection["dbname"] == "life365_sandbox"
    assert connection["user"] == "sandbox_user"
    assert connection["host"] == host and connection["port"] == port
    assert connection["password"] == values["SANDBOX_DB_PASSWORD"]
    assert values["SANDBOX_DB_PASSWORD"] not in repr(settings)
    assert settings.jwt_secret not in repr(settings)


@pytest.mark.parametrize(
    "name",
    [
        "SANDBOX_DATABASE_HOST",
        "SANDBOX_DATABASE_PORT",
        "SANDBOX_DB_PASSWORD",
        "SANDBOX_JWT_SECRET_KEY",
        "SANDBOX_CUSTOMER_SYNC_FINGERPRINT_SECRET",
    ],
)
def test_missing_or_empty_settings_never_use_production(name: str) -> None:
    values = _values()
    for missing in (None, "", " "):
        changed = {**values, name: missing}
        with pytest.raises(SandboxConfigurationError):
            SandboxSettings.from_values(changed)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("SANDBOX_DATABASE_HOST", "production.invalid"),
        ("SANDBOX_DATABASE_HOST", "/tmp"),
        ("SANDBOX_DATABASE_PORT", "5432"),
        ("SANDBOX_JWT_SECRET_KEY", "short"),
        ("SANDBOX_CUSTOMER_SYNC_FINGERPRINT_SECRET", "short"),
    ],
)
def test_invalid_settings_are_rejected(name: str, value: str) -> None:
    with pytest.raises(SandboxConfigurationError):
        SandboxSettings.from_values({**_values(), name: value})


@pytest.mark.parametrize(
    "sandbox_key",
    ["SANDBOX_JWT_SECRET_KEY", "SANDBOX_CUSTOMER_SYNC_FINGERPRINT_SECRET"],
)
@pytest.mark.parametrize(
    "production_key", ["JWT_SECRET_KEY", "CUSTOMER_SYNC_FINGERPRINT_SECRET"]
)
def test_production_keys_cannot_be_reused(
    sandbox_key: str, production_key: str
) -> None:
    values = _values()
    values[sandbox_key] = values[production_key]
    with pytest.raises(SandboxConfigurationError):
        SandboxSettings.from_values(values)


def test_loading_settings_does_not_mutate_process_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _values()
    monkeypatch.setattr(settings_module, "dotenv_values", lambda _path: values)
    for name in values:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://unchanged.invalid/business")
    before = dict(os.environ)
    settings = SandboxSettings.load()
    assert conninfo_to_dict(settings.database_connection)["dbname"] == "life365_sandbox"
    assert dict(os.environ) == before
