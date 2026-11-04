"""Contract boundary tests; no Docker daemon, database, or network needed."""

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError
from shared.contracts import (
    CONTROL_PLANE_COMMAND_ADAPTER,
    WORKER_MESSAGE_ADAPTER,
    Box,
    BoxCreationRequest,
    BoxValidationResult,
    CommandResult,
    ContainerLogsEvent,
    ContainerStatusEvent,
    Deployment,
    Heartbeat,
    InspectContainerCommand,
    PlacementDecision,
    Replica,
    ResourceReservation,
    RunContainerCommand,
    StopContainerCommand,
    WorkerSnapshot,
)


def run_payload():
    return {
        "type": "run_container",
        "request_id": str(uuid4()),
        "deployment_id": str(uuid4()),
        "box_id": str(uuid4()),
        "image_reference": "ghcr.io/example/application:latest",
        "container_name": "application-1",
        "cpu_limit_cores": 1.5,
        "ram_limit_mb": 512,
        "internal_port": 8000,
        "environment_variables": {"MODE": "production"},
        "role": "primary",
    }


def worker_payload():
    return {
        "worker_id": "W-001",
        "hostname": "test-worker",
        "status": "online",
        "cpu_cores": 4,
        "available_cpu_cores": 3.5,
        "total_ram_gb": 16,
        "available_ram_gb": 8,
        "total_storage_gb": 256,
        "available_storage_gb": 128,
        "active_container_count": 0,
        "max_containers": 4,
        "architecture": "arm64",
        "supported_runtimes": ["python", "node"],
        "last_heartbeat": datetime.now(UTC),
    }


def test_command_json_round_trip():
    command = CONTROL_PLANE_COMMAND_ADAPTER.validate_json(json.dumps(run_payload()))
    assert isinstance(command, RunContainerCommand)
    assert (
        CONTROL_PLANE_COMMAND_ADAPTER.validate_json(command.model_dump_json())
        == command
    )
    assert isinstance(command.model_dump(mode="json")["deployment_id"], str)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("cpu_limit_cores", 0),
        ("cpu_limit_cores", float("inf")),
        ("cpu_limit_cores", float("nan")),
        ("ram_limit_mb", -1),
        ("ram_limit_mb", True),
        ("internal_port", 65536),
        ("container_name", "bad/name"),
        ("environment_variables", {"BAD=KEY": "value"}),
        ("role", "unknown"),
    ],
)
def test_invalid_run_inputs(field, value):
    payload = run_payload()
    payload[field] = value
    with pytest.raises(ValidationError):
        RunContainerCommand.model_validate(payload)


@pytest.mark.parametrize("kind", ["execute_shell", None])
def test_unknown_or_missing_command_type_rejected(kind):
    payload = run_payload()
    if kind is None:
        payload.pop("type")
    else:
        payload["type"] = kind
    with pytest.raises(ValidationError):
        CONTROL_PLANE_COMMAND_ADAPTER.validate_python(payload)


def test_unknown_fields_rejected():
    payload = run_payload() | {"privileged": True}
    with pytest.raises(ValidationError):
        CONTROL_PLANE_COMMAND_ADAPTER.validate_python(payload)


@pytest.mark.parametrize("model", [StopContainerCommand, InspectContainerCommand])
def test_other_command_variants(model):
    payload = {"request_id": uuid4(), "container_id": "container-1"}
    if model is StopContainerCommand:
        payload["deployment_id"] = uuid4()
    command = model(**payload)
    assert (
        CONTROL_PLANE_COMMAND_ADAPTER.validate_json(command.model_dump_json())
        == command
    )


@pytest.mark.parametrize(
    "message",
    [
        CommandResult(request_id=uuid4(), success=False, message="Image pull failed"),
        Heartbeat(
            worker_id="W-001",
            cpu_usage_percent=20,
            available_ram_gb=8,
            available_storage_gb=128,
            active_container_count=1,
            running_containers=["container-1"],
            timestamp=datetime.now(UTC),
        ),
        ContainerStatusEvent(
            deployment_id=uuid4(),
            container_id="container-1",
            status="running",
            timestamp=datetime.now(UTC),
        ),
        ContainerLogsEvent(
            deployment_id=uuid4(),
            container_id="container-1",
            log_level="info",
            message="Ready",
            timestamp=datetime.now(UTC),
        ),
    ],
)
def test_all_worker_message_variants_round_trip(message):
    assert WORKER_MESSAGE_ADAPTER.validate_json(message.model_dump_json()) == message


def test_snapshot_capacity_and_timezone_validation():
    payload = worker_payload()
    assert WorkerSnapshot(**payload).worker_id == "W-001"
    with pytest.raises(ValidationError):
        WorkerSnapshot(**(payload | {"available_ram_gb": 17}))
    with pytest.raises(ValidationError):
        WorkerSnapshot(**(payload | {"last_heartbeat": datetime(2026, 1, 1)}))


def test_box_requires_distinct_eligible_placements():
    payload = {
        "box_id": uuid4(),
        "name": "Box 1",
        "ram_limit_gb": 8,
        "cpu_limit_cores": 2,
        "storage_limit_gb": 16,
        "eligible_worker_ids": ["W-001", "W-002"],
        "primary_worker_id": "W-001",
        "standby_worker_id": "W-002",
        "failover_enabled": True,
        "status": "available",
    }
    assert Box(**payload).standby_worker_id == "W-002"
    for invalid in ({"standby_worker_id": "W-001"}, {"primary_worker_id": "W-003"}):
        with pytest.raises(ValidationError):
            Box(**(payload | invalid))


def test_failover_creation_requires_two_unique_candidates():
    payload = {
        "name": "Box",
        "ram_limit_gb": 1,
        "cpu_limit_cores": 1,
        "storage_limit_gb": 1,
    }
    for ids in (["W-001"], ["W-001", "W-001"]):
        with pytest.raises(ValidationError):
            BoxCreationRequest(
                **payload, eligible_worker_ids=ids, failover_enabled=True
            )


def test_deployment_and_replica_accept_json_ids_and_consistent_worker_id():
    deployment = Deployment(
        deployment_id=uuid4(),
        box_id=uuid4(),
        repository_url="https://example.com/repo.git",
        branch="main",
        application_type="python",
        image_reference="app:v1",
        status="queued",
        created_at=datetime.now(UTC),
    )
    assert Deployment.model_validate_json(deployment.model_dump_json()) == deployment
    replica = Replica(
        replica_id=uuid4(),
        deployment_id=deployment.deployment_id,
        worker_id="W-001",
        role="primary",
        status="pending",
        internal_port=8000,
    )
    assert replica.worker_id == WorkerSnapshot(**worker_payload()).worker_id


def test_placement_requires_matching_reservations():
    box_id = uuid4()
    reservation = ResourceReservation(
        reservation_id=uuid4(),
        box_id=box_id,
        worker_id="W-001",
        role="primary",
        ram_limit_gb=1,
        cpu_limit_cores=1,
        storage_limit_gb=1,
    )
    payload = {"box_id": box_id, "primary_worker_id": "W-001", "reason": "Fits"}
    assert PlacementDecision(**payload, reservations=[reservation]).box_id == box_id
    with pytest.raises(ValidationError):
        PlacementDecision(
            **payload, standby_worker_id="W-002", reservations=[reservation]
        )
    with pytest.raises(ValidationError):
        PlacementDecision(**payload, reservations=[reservation, reservation])


def test_validation_outcomes_are_unambiguous():
    assert BoxValidationResult(valid=False, errors=["Insufficient RAM"]).errors
    with pytest.raises(ValidationError):
        BoxValidationResult(valid=True, errors=["Insufficient RAM"])
    with pytest.raises(ValidationError):
        BoxValidationResult(valid=False)
