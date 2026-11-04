"""All Docker create options are owner-controlled, never arbitrary wire fields."""

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

import docker
from docker.types import LogConfig
from shared.contracts import RunContainerCommand

from worker_agent.config import Settings

WORKER_LABEL = "io.lattice.worker"
DEPLOYMENT_LABEL = "io.lattice.deployment"
BOX_LABEL = "io.lattice.box"
ROLE_LABEL = "io.lattice.role"
REQUEST_LABEL = "io.lattice.request"
FINGERPRINT_LABEL = "io.lattice.fingerprint"
STORAGE_LABEL = "io.lattice.storage-gb"


def fingerprint(command: RunContainerCommand) -> str:
    # Digest only: environment values must not be persisted in the request journal.
    canonical = json.dumps(
        command.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def resource_name(worker_id: str, deployment_id: str, kind: str) -> str:
    owner = hashlib.sha256(worker_id.encode()).hexdigest()[:12]
    return f"lattice-{owner}-{deployment_id}-{kind}"


def open_local_docker(settings: Settings):
    host = os.environ.get("DOCKER_HOST")
    if os.name == "nt":
        if not host:
            # Honor Docker Desktop's selected Linux-engine context. Never
            # silently follow an SSH/TCP context to another machine.
            context = os.environ.get("DOCKER_CONTEXT")
            try:
                result = subprocess.run(
                    ["docker", "context", "inspect", *([context] if context else [])],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10,
                )
            except FileNotFoundError:
                host = "npipe:////./pipe/docker_engine"
            else:
                if result.returncode:
                    raise ValueError(
                        "Cannot read Docker Desktop context; start Docker Desktop"
                    )
                entries = json.loads(result.stdout)
                if not isinstance(entries, list) or len(entries) != 1:
                    raise ValueError("Expected one local Docker Desktop context")
                host = entries[0]["Endpoints"]["docker"]["Host"]
        if not re.fullmatch(
            r"npipe:/{2,4}\./pipe/[A-Za-z0-9_.-]+", host, re.IGNORECASE
        ):
            raise ValueError("Windows worker requires a local Docker named pipe")
        return docker.DockerClient(base_url=host, timeout=settings.docker_timeout)
    if host and not host.startswith("unix://"):
        raise ValueError("Worker Service requires a local Docker daemon socket")
    if host:
        return docker.from_env(timeout=settings.docker_timeout)
    desktop = Path.home() / ".docker/run/docker.sock"
    if desktop.exists():
        return docker.DockerClient(
            base_url=f"unix://{desktop}", timeout=settings.docker_timeout
        )
    return docker.from_env(timeout=settings.docker_timeout)


def container_options(
    command: RunContainerCommand,
    settings: Settings,
    worker_id: str,
    network: str,
    volume: str,
    storage_gb: float,
) -> dict:
    if settings.image_pull_policy == "if_not_present" and not re.fullmatch(
        r"[^\s@]+@sha256:[0-9a-f]{64}", command.image_reference
    ):
        raise ValueError("Cached image policy requires an immutable @sha256 reference")
    if not re.fullmatch(r"[1-9][0-9]*:[0-9]+", settings.container_user):
        raise ValueError("CONTAINER_USER must be a numeric non-root UID:GID")
    if len(command.image_reference) > 512 or re.search(
        r"\s|[\x00-\x1f]", command.image_reference
    ):
        raise ValueError("Image reference contains invalid characters")
    return {
        "image": command.image_reference,
        "name": command.container_name,
        "detach": True,
        "nano_cpus": max(1, round(command.cpu_limit_cores * 1_000_000_000)),
        "mem_limit": command.ram_limit_mb * 1024**2,
        "memswap_limit": command.ram_limit_mb * 1024**2,
        "pids_limit": 128,
        "privileged": False,
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "read_only": True,
        "user": settings.container_user,
        "network": network,
        "ports": {f"{command.internal_port}/tcp": (settings.bind_address, 0)},
        "environment": command.environment_variables,
        "volumes": {volume: {"bind": "/data", "mode": "rw"}},
        "tmpfs": {
            "/tmp": "rw,noexec,nosuid,size=64m",
            "/run": "rw,noexec,nosuid,size=1m",
        },
        "restart_policy": {"Name": "no"},
        "log_config": LogConfig(
            type="json-file", config={"max-size": "10m", "max-file": "2"}
        ),
        "labels": {
            WORKER_LABEL: worker_id,
            DEPLOYMENT_LABEL: str(command.deployment_id),
            BOX_LABEL: str(command.box_id),
            ROLE_LABEL: command.role.value,
            REQUEST_LABEL: str(command.request_id),
            FINGERPRINT_LABEL: fingerprint(command),
            STORAGE_LABEL: str(storage_gb),
        },
        "use_config_proxy": False,
    }


def assert_owned(container, worker_id: str, deployment_id: str | None = None) -> None:
    labels = container.labels or {}
    if labels.get(WORKER_LABEL) != worker_id:
        raise PermissionError("Container is not owned by this worker")
    if deployment_id is not None and labels.get(DEPLOYMENT_LABEL) != deployment_id:
        raise PermissionError("Container does not belong to this deployment")
