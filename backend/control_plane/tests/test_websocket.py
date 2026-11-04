import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from shared.contracts import CommandResult, Heartbeat, StopContainerCommand
from starlette.websockets import WebSocketDisconnect

from control_plane.database.models import Worker
from control_plane.services.websocket_gateway import WorkerConnectionManager


def test_header_auth_and_lease_bound_snapshot(client, provision, context):
    token = provision()
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws/workers?token=" + token),
    ):
        pass
    headers = {
        "Authorization": "Bearer " + token,
        "X-Worker-ID": "worker-1",
        "X-Worker-Lease-Enforced": "true",
    }
    with client.websocket_connect("/ws/workers", headers=headers) as ws:
        grant = ws.receive_json()
        assert grant["type"] == "lease"
        snapshot = client.get("/api/workers/worker-1").json() | {"status": "online"}
        endpoint = "/api/workers/worker-1/snapshot"
        assert client.post(endpoint, json=snapshot, headers=headers).status_code == 409
        assert (
            client.post(
                endpoint,
                json=snapshot,
                headers=headers | {"X-Worker-Lease-ID": grant["lease_id"]},
            ).status_code
            == 200
        )
        heartbeat = Heartbeat(
            worker_id="worker-1",
            cpu_usage_percent=75,
            available_ram_gb=1,
            available_storage_gb=1,
            active_container_count=0,
            running_containers=[],
            timestamp=datetime.now(UTC),
        )
        ws.send_text(heartbeat.model_dump_json())
        assert ws.receive_json()["type"] == "lease"
        with context.db.session() as session:
            assert (
                session.get(Worker, "worker-1").available_ram_gb == 8
            )  # utilization is not allocation
        ws.send_text(
            heartbeat.model_copy(update={"worker_id": "other"}).model_dump_json()
        )
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


class Socket:
    def __init__(self):
        self.messages = []

    async def send_text(self, text):
        self.messages.append(text)

    async def close(self, **kwargs):
        pass


async def test_results_are_scoped_to_worker_and_session():
    gateway = WorkerConnectionManager()
    a = Socket()
    b = Socket()
    gateway.active_connections.update(a=a, b=b)
    command = StopContainerCommand(
        request_id=uuid4(), deployment_id=uuid4(), container_id="container-a"
    )
    task = asyncio.create_task(gateway.send_worker_command("a", command, timeout=0.5))
    await asyncio.sleep(0)
    result = CommandResult(
        request_id=command.request_id,
        success=True,
        container_id="container-a",
        message="Stopped",
    )
    await gateway._handle_command_result("b", result, b)
    assert not task.done()
    await gateway._handle_command_result("a", result, b)
    assert not task.done()
    await gateway._handle_command_result("a", result, a)
    assert (await task).success
    assert not gateway._pending_commands


async def test_disconnect_fails_only_its_own_pending_commands():
    gateway = WorkerConnectionManager()
    a = Socket()
    b = Socket()
    gateway.active_connections.update(a=a, b=b)
    ca = StopContainerCommand(
        request_id=uuid4(), deployment_id=uuid4(), container_id="a"
    )
    cb = StopContainerCommand(
        request_id=uuid4(), deployment_id=uuid4(), container_id="b"
    )
    ta = asyncio.create_task(gateway.send_worker_command("a", ca, timeout=0.5))
    tb = asyncio.create_task(gateway.send_worker_command("b", cb, timeout=0.5))
    await asyncio.sleep(0)
    gateway._fail_pending("a", a)
    with pytest.raises(ConnectionResetError):
        await ta
    assert not tb.done()
    await gateway._handle_command_result(
        "b", CommandResult(request_id=cb.request_id, success=True, message="Stopped"), b
    )
    assert (await tb).success


async def test_command_timeout_and_offline():
    gateway = WorkerConnectionManager()
    gateway.active_connections["a"] = Socket()
    command = StopContainerCommand(
        request_id=uuid4(), deployment_id=uuid4(), container_id="a"
    )
    with pytest.raises(TimeoutError):
        await gateway.send_worker_command("a", command, timeout=0.01)
    assert not gateway._pending_commands
    with pytest.raises(ConnectionError):
        await gateway.send_worker_command("missing", command)
