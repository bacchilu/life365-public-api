"""Offline checks for the local PostgreSQL lifecycle and seed safeguards."""

import json
from copy import deepcopy
from unittest.mock import Mock

import pytest

import scripts.local_postgres.config as config
import scripts.local_postgres.docker as docker
from scripts.local_postgres.config import LocalDatabaseError, operation_lock


def _info(*, running: bool = True, healthy: bool = True) -> dict:
    return {
        "Config": {
            "Image": "postgres:18.6",
            "Labels": {
                "com.docker.compose.project": "test-project",
                "com.docker.compose.service": "local-postgres",
            },
            "Env": [
                "POSTGRES_USER=life365_local_admin",
                "CUSTOMER_SYNC_TEST_PASSWORD=example",
            ],
        },
        "HostConfig": {
            "Tmpfs": {"/var/lib/postgresql": "size=512m"},
            "PortBindings": {
                "5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "55432"}]
            },
        },
        "State": {
            "Running": running,
            "Health": {"Status": "healthy" if healthy else "starting"},
        },
    }


def _postgres(monkeypatch: pytest.MonkeyPatch) -> tuple[docker.LocalPostgres, Mock]:
    run = Mock(
        return_value=json.dumps(
            {
                "name": "test-project",
                "services": {
                    "local-postgres": {
                        "environment": {
                            "POSTGRES_USER": "life365_local_admin",
                            "CUSTOMER_SYNC_TEST_PASSWORD": "example",
                        }
                    }
                },
            }
        )
    )
    monkeypatch.setattr(docker, "run", run)
    monkeypatch.setattr(docker.shutil, "which", lambda _: "/usr/bin/docker")
    postgres = docker.LocalPostgres()
    run.reset_mock()
    return postgres, run


def test_running_container_is_reused_without_start_or_recreation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    postgres, run = _postgres(monkeypatch)
    run.side_effect = ["", "container-id", json.dumps([_info()]), json.dumps([_info()])]
    assert postgres.up() == "container-id"
    assert all(
        "up" not in call.args[0] and "start" not in call.args[0]
        for call in run.call_args_list
    )


def test_stopped_container_is_started_without_recreation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    postgres, run = _postgres(monkeypatch)
    run.side_effect = [
        "",
        "container-id",
        json.dumps([_info(running=False)]),
        "",
        json.dumps([_info()]),
    ]
    assert postgres.up() == "container-id"
    assert any(
        call.args[0] == ["docker", "start", "container-id"]
        for call in run.call_args_list
    )
    assert all("--force-recreate" not in call.args[0] for call in run.call_args_list)


def test_new_service_waits_for_readiness_and_prohibits_recreation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    postgres, run = _postgres(monkeypatch)
    run.side_effect = ["", "", "", "container-id", json.dumps([_info()])]
    assert postgres.up() == "container-id"
    command = run.call_args_list[2].args[0]
    assert {"--no-recreate", "--wait", "--wait-timeout"} <= set(command)
    assert command[-1] == "local-postgres"


def test_existing_legacy_server_is_not_silently_replaced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    postgres, run = _postgres(monkeypatch)
    run.return_value = "old-container"
    with pytest.raises(LocalDatabaseError, match="old customer-sync-test-db"):
        postgres.up()
    assert run.call_count == 1


@pytest.mark.parametrize("change", ["project", "service", "image", "port", "password"])
def test_wrong_container_or_changed_settings_are_rejected(
    change: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    postgres, run = _postgres(monkeypatch)
    info = deepcopy(_info())
    if change in ("project", "service"):
        info["Config"]["Labels"][f"com.docker.compose.{change}"] = "other"
    elif change == "image":
        info["Config"]["Image"] = "postgres:latest"
    elif change == "port":
        info["HostConfig"]["PortBindings"]["5432/tcp"][0]["HostIp"] = "0.0.0.0"
    else:
        info["Config"]["Env"] = []
    run.return_value = json.dumps([info])
    with pytest.raises(LocalDatabaseError):
        postgres.inspect("container-id")


def test_unready_database_fails_without_destroying_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    postgres, run = _postgres(monkeypatch)
    run.side_effect = [
        "",
        "container-id",
        json.dumps([_info()]),
        json.dumps([_info(healthy=False)]),
    ]
    with pytest.raises(LocalDatabaseError, match="did not become healthy"):
        postgres.up(timeout=0)
    assert all(
        "rm" not in call.args[0] and "stop" not in call.args[0]
        for call in run.call_args_list
    )


def test_stop_affects_only_the_database_and_warns_about_both_databases(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    postgres, run = _postgres(monkeypatch)
    run.side_effect = ["container-id", json.dumps([_info()]), ""]
    postgres.stop()
    assert run.call_args.args[0] == ["docker", "stop", "container-id"]
    assert "BOTH sandbox and automated-test" in capsys.readouterr().out


def test_concurrent_lifecycle_operations_cannot_interfere(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "ROOT", tmp_path)
    with operation_lock():
        with pytest.raises(
            LocalDatabaseError, match="Another local database operation"
        ):
            with operation_lock():
                pytest.fail("Lock was not exclusive")
    with operation_lock():
        pass
    assert (tmp_path / ".sandbox-db/operation.lock").exists()


def test_seed_is_static_and_never_uses_production_configuration() -> None:
    root = config.ROOT
    initializer = (root / "docker/postgres/init-databases.sh").read_text()
    assert "DATABASE_URL" not in initializer
    assert "pg_dump" not in initializer
    assert "--dbname life365_sandbox" in initializer
    makefile = (root / "Makefile").read_text()
    assert "sandbox-db-refresh:" not in makefile
    assert "docker-dev-up: docker-test-db-up" in makefile
    assert "docker-prod-up: docker-network docker-test-db-up" in makefile
    assert "--profile dev down" not in makefile
    assert "--profile prod down" not in makefile
