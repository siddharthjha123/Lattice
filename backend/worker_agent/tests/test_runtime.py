from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from docker.errors import NotFound
from worker_agent.docker_runtime.manager import DockerManager
from worker_agent.security.policy import WORKER_LABEL
from worker_agent.telemetry.system_monitor import GIB
from worker_agent.tests.test_config import settings
from worker_agent.tests.test_security import run_command


def manager(tmp_path, **overrides):
    client = Mock()
    client.info.return_value = {"OSType": "linux", "NCPU": 8, "MemTotal": 8 * GIB}
    client.containers.list.return_value = []
    client.df.return_value = {"Volumes": []}
    client.volumes.get.side_effect = NotFound("missing")
    client.networks.get.side_effect = NotFound("missing")
    monitor = Mock()
    monitor.read.return_value = SimpleNamespace(
        available_ram_bytes=8 * GIB, available_storage_bytes=64 * GIB
    )
    runtime = DockerManager(settings(tmp_path, **overrides), "W-001", client, monitor)
    runtime.initialize()
    return runtime, client


def test_run_pulls_image_creates_limits_and_starts(tmp_path):
    runtime, client = manager(tmp_path)
    container = client.containers.create.return_value
    container.status = "running"
    container.id = "container-1"
    command = run_command()
    assert runtime.run(command) == "container-1"
    client.images.pull.assert_called_once_with(command.image_reference)
    container.start.assert_called_once()
    assert client.containers.create.call_args.kwargs["mem_limit"] == 256 * 1024**2


def test_failed_start_removes_only_new_container(tmp_path):
    runtime, client = manager(tmp_path)
    container = client.containers.create.return_value
    container.start.side_effect = RuntimeError("start failed")
    with pytest.raises(RuntimeError, match="start failed"):
        runtime.run(run_command())
    container.remove.assert_called_once_with(force=True)


@pytest.mark.parametrize(
    "limits, command",
    [
        ({"max_cpu_cores": 0.5}, {"cpu_limit_cores": 1}),
        ({"max_ram_gb": 0.1}, {"ram_limit_mb": 256}),
    ],
)
def test_insufficient_resources_fail_before_image_pull(tmp_path, limits, command):
    runtime, client = manager(tmp_path, **limits)
    with pytest.raises(ValueError, match="Insufficient"):
        runtime.run(run_command(**command))
    client.images.pull.assert_not_called()


def test_stop_rejects_foreign_containers(tmp_path):
    runtime, client = manager(tmp_path)
    client.containers.get.return_value.labels = {WORKER_LABEL: "someone-else"}
    with pytest.raises(PermissionError):
        runtime.stop("foreign-container")
    client.containers.get.return_value.stop.assert_not_called()


def test_stop_already_missing_is_idempotent(tmp_path):
    runtime, client = manager(tmp_path)
    client.containers.get.side_effect = NotFound("missing")
    assert runtime.stop("removed-container") == "removed-container"
