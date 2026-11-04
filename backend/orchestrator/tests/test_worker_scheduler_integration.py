"""Real Worker Service telemetry/admission code feeds Orchestrator through shared contracts.

Only the external Docker/system boundary is mocked in these unit integrations.
The separate opt-in worker suite verifies real Docker and WebSocket execution.
"""

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from shared.contracts import (
    Box,
    BoxCreationRequest,
    ResourceReservation,
    RunContainerCommand,
)
from worker_agent.config import Settings
from worker_agent.docker_runtime.manager import DockerManager
from worker_agent.security.policy import DEPLOYMENT_LABEL, STORAGE_LABEL, WORKER_LABEL
from worker_agent.telemetry.system_monitor import GIB, SystemReading

from orchestrator.service import (
    calculate_worker_capacity,
    select_deployment_worker,
    validate_box_creation,
)


def setup_runtime(tmp_path):
    active_deployment, new_deployment = uuid4(), uuid4()
    settings = Settings(
        control_plane_url="http://localhost:8000",
        worker_token="test-token",
        max_cpu_cores=4,
        require_control_plane_lease=False,
        max_ram_gb=8,
        max_storage_gb=10,
        max_containers=4,
        deployment_storage_limits={new_deployment: 2},
        state_dir=tmp_path,
    )
    container = SimpleNamespace(
        id="active-container",
        status="running",
        labels={WORKER_LABEL: "W-001", DEPLOYMENT_LABEL: str(active_deployment)},
        attrs={"HostConfig": {"NanoCpus": 1_000_000_000, "Memory": 2 * GIB}},
    )
    client = Mock()
    client.info.return_value = {
        "OSType": "linux",
        "NCPU": 4,
        "MemTotal": 8 * GIB,
        "Architecture": "aarch64",
    }
    client.containers.list.return_value = [container]
    client.df.return_value = {
        "Volumes": [
            {
                "Name": "active-volume",
                "Labels": {
                    WORKER_LABEL: "W-001",
                    DEPLOYMENT_LABEL: str(active_deployment),
                    STORAGE_LABEL: "1",
                },
                "UsageData": {"Size": 0},
            }
        ]
    }
    monitor = Mock()
    monitor.read.return_value = SystemReading(
        4, 20, 8 * GIB, 6 * GIB, 100 * GIB, 90 * GIB, 0, 0, "arm64"
    )
    runtime = DockerManager(settings, "W-001", client, monitor)
    runtime.initialize()
    active = ResourceReservation(
        reservation_id=uuid4(),
        box_id=uuid4(),
        worker_id="W-001",
        role="primary",
        cpu_limit_cores=1,
        ram_limit_gb=2,
        storage_limit_gb=1,
    )
    idle = ResourceReservation(
        reservation_id=uuid4(),
        box_id=uuid4(),
        worker_id="W-001",
        role="primary",
        cpu_limit_cores=1,
        ram_limit_gb=1,
        storage_limit_gb=2,
    )
    return runtime, active, idle, new_deployment


def test_worker_snapshot_and_orchestrator_agree_on_active_and_idle_allocations(
    tmp_path,
):
    runtime, active, idle, deployment_id = setup_runtime(tmp_path)
    snapshot, _ = runtime.telemetry()
    assert snapshot.available_cpu_cores == 3
    assert snapshot.available_ram_gb == 6
    assert snapshot.available_storage_gb == 9
    capacity = calculate_worker_capacity(
        snapshot, [active, idle], active_reservation_ids={active.reservation_id}
    )
    assert capacity.available_cpu_cores == 2
    assert capacity.available_ram_gb == 5
    assert capacity.available_storage_gb == 7
    assert capacity.available_container_slots == 2

    value = Box(
        box_id=idle.box_id,
        name="new-app",
        cpu_limit_cores=1,
        ram_limit_gb=1,
        storage_limit_gb=2,
        eligible_worker_ids=["W-001"],
        primary_worker_id="W-001",
        status="available",
    )
    selection = select_deployment_worker(
        value,
        [snapshot],
        reservations=[active, idle],
        active_reservation_ids={active.reservation_id},
        required_architecture="arm64",
        application_type="python",
    )
    assert selection.worker_id == runtime.worker_id
    command = RunContainerCommand(
        request_id=uuid4(),
        deployment_id=deployment_id,
        box_id=value.box_id,
        image_reference="example/app:latest",
        container_name="new-app",
        cpu_limit_cores=1,
        ram_limit_mb=1024,
        internal_port=8000,
        role="primary",
    )
    assert runtime._admit(command) == 2


def test_owner_pause_is_rejected_by_both_scheduler_and_worker(tmp_path):
    runtime, _, _, deployment_id = setup_runtime(tmp_path)
    runtime.paused = True
    snapshot, _ = runtime.telemetry()
    request = BoxCreationRequest(
        name="new-app",
        cpu_limit_cores=1,
        ram_limit_gb=1,
        storage_limit_gb=1,
        eligible_worker_ids=["W-001"],
    )
    assert not validate_box_creation(request, [snapshot], []).valid
    command = RunContainerCommand(
        request_id=uuid4(),
        deployment_id=deployment_id,
        box_id=uuid4(),
        image_reference="example/app:latest",
        container_name="new-app",
        cpu_limit_cores=1,
        ram_limit_mb=1024,
        internal_port=8000,
        role="primary",
    )
    with pytest.raises(ValueError, match="paused"):
        runtime.run(command)
