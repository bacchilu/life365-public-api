"""Start the local database without replacing a running tmpfs container."""

import json
import shutil
import subprocess
import time
from typing import Any

from .config import IMAGE, ROOT, SERVICE, LocalDatabaseError


def run(
    command: list[str], *, capture: bool = True, env: dict[str, str] | None = None
) -> str:
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=False,
    )
    if result.returncode:
        raise LocalDatabaseError(
            f"Local Docker command failed (exit {result.returncode}). "
            "Check Docker access and `docker compose --profile test logs local-postgres`."
        )
    return result.stdout.strip() if capture else ""


class LocalPostgres:
    def __init__(self) -> None:
        if shutil.which("docker") is None:
            raise LocalDatabaseError("Docker and Docker Compose are required")
        self.compose = [
            "docker",
            "compose",
            "--project-directory",
            str(ROOT),
            "-f",
            str(ROOT / "docker-compose.yaml"),
            "--profile",
            "test",
        ]
        config = json.loads(run([*self.compose, "config", "--format", "json"]))
        self.project = config["name"]
        self.environment = config["services"][SERVICE]["environment"]

    def container_id(self) -> str | None:
        value = run([*self.compose, "ps", "--all", "--quiet", SERVICE])
        if "\n" in value:
            raise LocalDatabaseError("Expected exactly one local PostgreSQL container")
        return value or None

    def inspect(
        self, container_id: str, *, check_environment: bool = True
    ) -> dict[str, Any]:
        info = json.loads(run(["docker", "inspect", container_id]))[0]
        labels = info["Config"]["Labels"]
        if (
            labels.get("com.docker.compose.project") != self.project
            or labels.get("com.docker.compose.service") != SERVICE
        ):
            raise LocalDatabaseError(
                "Container does not belong to the intended local PostgreSQL service"
            )
        if (
            info["Config"]["Image"] != IMAGE
            or "/var/lib/postgresql" not in info["HostConfig"]["Tmpfs"]
        ):
            raise LocalDatabaseError("Expected postgres:18.6 with tmpfs storage")
        environment = dict(
            value.split("=", 1) for value in info["Config"]["Env"] if "=" in value
        )
        if check_environment and any(
            environment.get(key) != value for key, value in self.environment.items()
        ):
            raise LocalDatabaseError(
                "Local database settings changed. Explicitly stop/remove its container before applying new settings; both databases will be lost"
            )
        bindings = info["HostConfig"]["PortBindings"].get("5432/tcp", [])
        if bindings != [{"HostIp": "127.0.0.1", "HostPort": "55432"}]:
            raise LocalDatabaseError("Local PostgreSQL must bind only 127.0.0.1:55432")
        return info

    def up(self, timeout: float = 90) -> str:
        legacy = run(
            [
                "docker",
                "ps",
                "--all",
                "--quiet",
                "--filter",
                f"label=com.docker.compose.project={self.project}",
                "--filter",
                "label=com.docker.compose.service=customer-sync-test-db",
            ]
        )
        if legacy:
            raise LocalDatabaseError(
                "Remove the old customer-sync-test-db container explicitly before starting local-postgres; its temporary test data will be lost"
            )
        container_id = self.container_id()
        if container_id is None:
            print(
                "Starting shared local PostgreSQL and loading the bundled sandbox sample",
                flush=True,
            )
            run(
                [
                    *self.compose,
                    "up",
                    "--detach",
                    "--no-recreate",
                    "--wait",
                    "--wait-timeout",
                    str(int(timeout)),
                    SERVICE,
                ],
                capture=False,
            )
            container_id = self.container_id()
            if container_id is None:
                raise LocalDatabaseError("Local PostgreSQL container was not created")
        elif not self.inspect(container_id)["State"]["Running"]:
            print(
                "Starting stopped PostgreSQL; temporary databases will be initialized again",
                flush=True,
            )
            run(["docker", "start", container_id])
        deadline = time.monotonic() + timeout
        while True:
            state = self.inspect(container_id)["State"]
            if state.get("Health", {}).get("Status") == "healthy":
                print(
                    "Local PostgreSQL ready: seeded life365_sandbox; separate automated-test database",
                    flush=True,
                )
                return container_id
            if not state["Running"] or time.monotonic() >= deadline:
                raise LocalDatabaseError(
                    "Local PostgreSQL did not become healthy; inspect its logs. No container was recreated"
                )
            time.sleep(0.5)

    def stop(self) -> None:
        print(
            "WARNING: stopping local PostgreSQL loses BOTH sandbox and automated-test databases",
            flush=True,
        )
        container_id = self.container_id()
        if container_id is not None:
            self.inspect(container_id, check_environment=False)
            run(["docker", "stop", container_id], capture=False)
