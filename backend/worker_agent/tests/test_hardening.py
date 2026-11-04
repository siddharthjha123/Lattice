import io
import json
import logging
from unittest.mock import Mock

import pytest
from docker.errors import ImageNotFound
from worker_agent.config import load_settings
from worker_agent.logging import configure_logging
from worker_agent.main import main
from worker_agent.security.policy import (
    DEPLOYMENT_LABEL,
    FINGERPRINT_LABEL,
    REQUEST_LABEL,
    STORAGE_LABEL,
    WORKER_LABEL,
    fingerprint,
)
from worker_agent.state import StateDirectory
from worker_agent.tests.test_config import settings
from worker_agent.tests.test_runtime import manager
from worker_agent.tests.test_security import run_command


def test_json_escaped_secret_is_redacted_before_serialization(tmp_path):
    secret = 'token-"quoted"-\\value'
    stream = io.StringIO()
    configure_logging(settings(tmp_path, worker_token=secret).worker_token, stream)
    logging.getLogger("worker_agent.test").error("value=%s", secret)
    assert json.loads(stream.getvalue())["message"] == "value=[REDACTED]"


def test_token_configuration_requires_owner_only_permissions(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {"control_plane_url": "http://localhost:8000", "worker_token": "file-token"}
        )
    )
    path.chmod(0o644)
    with pytest.raises(PermissionError):
        load_settings(path)
    path.chmod(0o600)
    assert load_settings(path).worker_token.get_secret_value() == "file-token"
    link = tmp_path / "config-link.json"
    link.symlink_to(path)
    with pytest.raises(ValueError, match="symlink"):
        load_settings(link)


def test_corrupt_identity_cannot_inject_authentication_headers(tmp_path):
    state = StateDirectory(tmp_path)
    state.prepare()
    state.write_json("identity.json", {"worker_id": "W-001\r\nInjected: true"})
    with pytest.raises(ValueError):
        state.identity()


def test_image_pull_rechecks_owner_drain_before_creation(tmp_path):
    runtime, client = manager(tmp_path)

    def drain(image):
        runtime.draining = True

    client.images.pull.side_effect = drain
    with pytest.raises(ValueError, match="draining"):
        runtime.run(run_command())
    client.containers.create.assert_not_called()


def test_invalid_image_is_rejected_before_registry_access(tmp_path):
    runtime, client = manager(tmp_path)
    with pytest.raises(ValueError, match="Image reference"):
        runtime.run(run_command(image_reference="bad image"))
    client.images.pull.assert_not_called()


def pending_container(command):
    container = Mock(id="pending-container", status="created")
    container.labels = {
        WORKER_LABEL: "W-001",
        DEPLOYMENT_LABEL: str(command.deployment_id),
        REQUEST_LABEL: str(command.request_id),
        FINGERPRINT_LABEL: fingerprint(command),
        STORAGE_LABEL: "1.0",
    }
    container.attrs = {
        "HostConfig": {"NanoCpus": 1_000_000_000, "Memory": 256 * 1024**2}
    }
    container.start.side_effect = lambda: setattr(container, "status", "running")
    return container


def test_interrupted_create_recovers_without_duplicate_pull_or_container(tmp_path):
    runtime, client = manager(tmp_path)
    command = run_command()
    container = pending_container(command)
    client.containers.list.return_value = [container]
    assert runtime.run(command) == container.id
    container.start.assert_called_once()
    client.images.pull.assert_not_called()
    client.containers.create.assert_not_called()


def test_interrupted_create_respects_new_lower_resource_policy(tmp_path):
    runtime, client = manager(tmp_path, max_cpu_cores=0.5)
    command = run_command()
    container = pending_container(command)
    client.containers.list.return_value = [container]
    with pytest.raises(ValueError, match="CPU"):
        runtime.run(command)
    container.start.assert_not_called()


def test_container_count_and_unbounded_foreign_workloads_fail_admission(tmp_path):
    runtime, client = manager(tmp_path, max_containers=1)
    command = run_command()
    container = pending_container(command)
    container.status = "running"
    client.containers.list.return_value = [container]
    capacity = runtime.capacity()
    assert capacity.container_slots == 0
    container.labels = {WORKER_LABEL: "foreign-worker"}
    container.attrs = {"HostConfig": {}}
    capacity = runtime.capacity()
    assert capacity.cpu_cores == 0
    assert capacity.ram_gb == 0


def test_stop_created_container_releases_admission_slot(tmp_path):
    runtime, client = manager(tmp_path)
    container = pending_container(run_command())
    client.containers.get.return_value = container
    assert runtime.stop(container.id) == container.id
    container.remove.assert_called_once()
    container.stop.assert_not_called()


def test_fingerprint_ignores_environment_key_order():
    command = run_command(environment_variables={"A": "one", "B": "two"})
    reordered = command.model_copy(
        update={"environment_variables": {"B": "two", "A": "one"}}
    )
    assert fingerprint(command) == fingerprint(reordered)


def test_cli_validation_does_not_log_sensitive_dictionary_keys(tmp_path, monkeypatch):
    secret = "credential-value"
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "control_plane_url": "http://localhost:8000",
                "worker_token": secret,
                "state_dir": str(tmp_path / "state"),
                "deployment_storage_limits": {secret: 1},
            }
        )
    )
    path.chmod(0o600)
    error = Mock()
    monkeypatch.setattr(logging.getLogger("worker_agent"), "error", error)
    assert main(["--config", str(path)]) == 2
    assert secret not in str(error.call_args)
    assert "deployment_storage_limits" in str(error.call_args)


@pytest.mark.parametrize(
    "override",
    [
        {"worker_token": "token\tvalue"},
        {"worker_id": "W-001\x1f"},
        {"container_user": "0:0"},
    ],
)
def test_invalid_security_settings_fail_before_startup(tmp_path, override):
    with pytest.raises(ValueError):
        settings(tmp_path, **override)


@pytest.mark.parametrize("present", [True, False])
def test_digest_cache_policy_uses_local_image_or_pulls_missing_image(tmp_path, present):
    runtime, client = manager(tmp_path, image_pull_policy="if_not_present")
    command = run_command(image_reference="registry.example/app@sha256:" + "a" * 64)
    if not present:
        client.images.get.side_effect = ImageNotFound("missing")
    client.containers.create.return_value.status = "running"
    runtime.run(command)
    if present:
        client.images.pull.assert_not_called()
    else:
        client.images.pull.assert_called_once_with(command.image_reference)


def test_cached_policy_refuses_mutable_tags(tmp_path):
    runtime, client = manager(tmp_path, image_pull_policy="if_not_present")
    with pytest.raises(ValueError, match="immutable"):
        runtime.run(run_command())
    client.images.pull.assert_not_called()
