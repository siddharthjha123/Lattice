from types import SimpleNamespace
from uuid import uuid4

import pytest
from shared.contracts import RunContainerCommand
from worker_agent.security.policy import (
    DEPLOYMENT_LABEL,
    WORKER_LABEL,
    assert_owned,
    container_options,
    open_local_docker,
)
from worker_agent.tests.test_config import settings


def run_command(**overrides):
    payload = {
        "request_id": uuid4(),
        "deployment_id": uuid4(),
        "box_id": uuid4(),
        "image_reference": "test-image:latest",
        "container_name": "test-app",
        "cpu_limit_cores": 1,
        "ram_limit_mb": 256,
        "internal_port": 8000,
        "environment_variables": {},
        "role": "primary",
    }
    return RunContainerCommand(**(payload | overrides))


def test_container_policy_drops_privileges_and_limits_resources(tmp_path):
    command = run_command()
    options = container_options(
        command, settings(tmp_path), "W-001", "network", "volume", 1
    )
    assert options["privileged"] is False
    assert options["cap_drop"] == ["ALL"]
    assert options["read_only"] is True
    assert options["nano_cpus"] == 1_000_000_000
    assert options["mem_limit"] == 256 * 1024**2
    assert options["volumes"] == {"volume": {"bind": "/data", "mode": "rw"}}
    assert options["ports"]["8000/tcp"] == ("127.0.0.1", 0)
    assert options["labels"][WORKER_LABEL] == "W-001"
    assert options["user"] == "65532:65532"


def test_foreign_containers_and_deployments_are_rejected():
    container = SimpleNamespace(
        labels={WORKER_LABEL: "W-001", DEPLOYMENT_LABEL: "deployment-1"}
    )
    with pytest.raises(PermissionError):
        assert_owned(container, "W-002")
    with pytest.raises(PermissionError):
        assert_owned(container, "W-001", "deployment-2")


def test_remote_docker_daemon_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCKER_HOST", "tcp://example.com:2375")
    with pytest.raises(ValueError, match="local Docker"):
        open_local_docker(settings(tmp_path))
