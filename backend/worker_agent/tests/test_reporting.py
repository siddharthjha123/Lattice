import asyncio
import threading
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

from shared.contracts import CommandResult, Heartbeat, WorkerSnapshot
from worker_agent.communication.client import GatewayClient
from worker_agent.communication.dispatcher import Execution
from worker_agent.communication.reporting import WorkerReporter
from worker_agent.state import StateDirectory
from worker_agent.tests.test_config import settings
from worker_agent.tests.test_security import run_command


def telemetry():
    snapshot = WorkerSnapshot(
        worker_id="W-001",
        hostname="worker",
        status="online",
        cpu_cores=2,
        available_cpu_cores=1,
        total_ram_gb=4,
        available_ram_gb=2,
        total_storage_gb=16,
        available_storage_gb=8,
        active_container_count=0,
        max_containers=4,
        architecture="arm64",
        supported_runtimes=["python"],
        last_heartbeat=datetime.now(UTC),
    )
    heartbeat = Heartbeat(
        worker_id="W-001",
        cpu_usage_percent=10,
        available_ram_gb=2,
        available_storage_gb=8,
        active_container_count=0,
        running_containers=[],
        timestamp=datetime.now(UTC),
    )
    return snapshot, heartbeat


async def test_initial_snapshot_is_private_and_heartbeat_is_canonical(tmp_path):
    runtime = Mock(settings=settings(tmp_path))
    runtime.telemetry.return_value = telemetry()
    state = StateDirectory(tmp_path)
    state.prepare()
    gateway = Mock()
    gateway.connected = asyncio.Event()
    gateway.connected.set()
    gateway.send = AsyncMock()
    lifecycle = Mock(publish_snapshot=AsyncMock(return_value=False))
    reporter = WorkerReporter(runtime, gateway, lifecycle, state)
    await reporter.heartbeat()
    gateway.send.assert_awaited_once_with(runtime.telemetry.return_value[1])
    assert state.read_json("snapshot.json")["worker_id"] == "W-001"
    assert (tmp_path / "snapshot.json").stat().st_mode & 0o777 == 0o600


async def test_slow_docker_commands_do_not_block_heartbeat(tmp_path):
    runtime = Mock(settings=settings(tmp_path, heartbeat_interval=0.1))
    runtime.telemetry.return_value = telemetry()
    state = StateDirectory(tmp_path)
    state.prepare()
    release, started, finished = threading.Event(), threading.Event(), threading.Event()
    command = run_command()

    def execute(command):
        started.set()
        release.wait(3)
        finished.set()
        return Execution(
            CommandResult(
                request_id=command.request_id,
                success=True,
                container_id="container-1",
                message="Started",
            )
        )

    gateway = GatewayClient(runtime.settings, "W-001", Mock(execute=execute))
    gateway.send = AsyncMock()
    gateway.connected.set()
    lifecycle = Mock(publish_snapshot=AsyncMock(return_value=False))
    reporter = WorkerReporter(runtime, gateway, lifecycle, state)
    stop = asyncio.Event()
    task = asyncio.create_task(reporter.heartbeat_loop(stop))
    consumer = asyncio.create_task(gateway._consume())
    await gateway.queue.put(command)
    try:
        assert await asyncio.to_thread(started.wait, 1)
        await asyncio.sleep(0.25)
        assert not finished.is_set()
        assert gateway.send.await_count >= 2
        assert all(
            call.args[0].type == "heartbeat" for call in gateway.send.await_args_list
        )
    finally:
        release.set()
        stop.set()
        await task
        await gateway.queue.join()
        await gateway.queue.put(None)
        await consumer


async def test_snapshot_waits_for_session_lease_without_suppressing_heartbeat(tmp_path):
    from uuid import uuid4

    runtime = Mock(settings=settings(tmp_path, require_control_plane_lease=True))
    runtime.telemetry.return_value = telemetry()
    state = StateDirectory(tmp_path)
    state.prepare()
    gateway = Mock(connected=asyncio.Event(), send=AsyncMock())
    gateway.connected.set()
    lifecycle = Mock(lease_id=None, publish_snapshot=AsyncMock())
    reporter = WorkerReporter(runtime, gateway, lifecycle, state)
    await reporter.heartbeat()
    lifecycle.publish_snapshot.assert_not_awaited()
    gateway.send.assert_awaited_once()
    lifecycle.lease_id = uuid4()
    await reporter.heartbeat()
    lifecycle.publish_snapshot.assert_awaited_once_with(
        runtime.telemetry.return_value[0]
    )
    assert gateway.send.await_count == 2
