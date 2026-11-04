"""Opt-in real Docker tests. All created resources carry a unique test worker ID.

Run: LATTICE_RUN_DOCKER_TESTS=1 python -m pytest worker_agent/tests/test_docker_integration.py
No daemon objects are mocked. The WebSocket fixture represents the gateway peer.
"""

import asyncio
import io
import os
import tarfile
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from shared.contracts import (
    WORKER_MESSAGE_ADAPTER,
    InspectContainerCommand,
    StopContainerCommand,
)
from websockets.asyncio.server import serve
from worker_agent.application import WorkerApplication
from worker_agent.communication.control import send_control
from worker_agent.communication.dispatcher import CommandDispatcher
from worker_agent.communication.journal import RequestJournal
from worker_agent.communication.lifecycle import ControlPlaneLifecycle
from worker_agent.docker_runtime.logs import LogCollector
from worker_agent.docker_runtime.manager import DockerManager
from worker_agent.security.policy import WORKER_LABEL, open_local_docker
from worker_agent.state import StateDirectory
from worker_agent.telemetry.system_monitor import SystemMonitor
from worker_agent.tests.test_config import settings
from worker_agent.tests.test_security import run_command

pytestmark = pytest.mark.skipif(
    os.environ.get("LATTICE_RUN_DOCKER_TESTS") != "1",
    reason="Set LATTICE_RUN_DOCKER_TESTS=1 for real Docker execution",
)
IMAGE = "public.ecr.aws/docker/library/traefik@sha256:16acb89c6db341182970d6fdafece31303b0a380a8ed7aa51682e225229bf1d2"


@pytest.fixture
def docker_runtime():
    with tempfile.TemporaryDirectory(prefix="lattice-real-", dir="/tmp") as directory:
        state = StateDirectory(Path(directory))
        state.prepare()
        worker_id = f"test-{uuid4()}"
        config = settings(
            state.path,
            max_ram_gb=0.5,
            max_cpu_cores=1,
            max_containers=2,
            max_storage_gb=1,
            deployment_storage_gb=1 / 1024,
            heartbeat_interval=0.2,
            image_pull_policy="if_not_present",
            disconnect_grace_seconds=0,
        )
        client = open_local_docker(config)
        runtime = DockerManager(config, worker_id, client, SystemMonitor(state.path))
        runtime.initialize()
        try:
            yield runtime, state
        finally:
            for container in runtime.containers():
                container.remove(force=True)
            filters = {"label": f"{WORKER_LABEL}={worker_id}"}
            for network in client.networks.list(filters=filters):
                network.remove()
            for volume in client.volumes.list(filters=filters):
                volume.remove()
            runtime.close()


def real_command():
    return run_command(
        image_reference=IMAGE,
        container_name=f"lattice-smoke-{uuid4()}",
        cpu_limit_cores=0.25,
        ram_limit_mb=128,
        internal_port=8080,
        environment_variables={
            "TRAEFIK_API_INSECURE": "true",
            "TRAEFIK_LOG_LEVEL": "INFO",
            "TRAEFIK_GLOBAL_CHECKNEWVERSION": "false",
            "TRAEFIK_GLOBAL_SENDANONYMOUSUSAGE": "false",
        },
    )


def test_real_container_limits_network_logs_and_idempotent_stop(docker_runtime):
    runtime, _ = docker_runtime
    command = real_command()
    container_id = runtime.run(command)
    container = runtime.client.containers.get(container_id)
    host = container.attrs["HostConfig"]
    assert host["NanoCpus"] == 250_000_000
    assert host["Memory"] == 128 * 1024**2
    assert host["ReadonlyRootfs"]
    assert host["Privileged"] is False
    assert host["CapDrop"] == ["ALL"]
    assert container.attrs["Config"]["User"] == "65532:65532"
    inspection = runtime.inspect(container_id)
    port = inspection.ports["8080/tcp"][0]["HostPort"]
    assert inspection.ports["8080/tcp"][0]["HostIp"] == "127.0.0.1"
    deadline = time.monotonic() + 5
    while True:
        try:
            response = httpx.get(
                f"http://127.0.0.1:{port}/api/version", timeout=1, trust_env=False
            )
            response.raise_for_status()
            break
        except httpx.HTTPError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.1)
    assert "Version" in response.json()
    assert runtime.run(command) == container_id
    assert LogCollector(runtime.settings).collect(container)
    runtime.stop(container_id, str(command.deployment_id))
    assert runtime.inspect(container_id, False).status == "exited"
    assert runtime.stop(container_id) == container_id


def test_real_volume_overrun_stops_workload_and_retains_data(docker_runtime):
    runtime, _ = docker_runtime
    command = real_command()
    container_id = runtime.run(command)
    container = runtime.client.containers.get(container_id)
    archive = io.BytesIO()
    payload = b"x" * (2 * 1024**2)
    with tarfile.open(fileobj=archive, mode="w") as tar:
        entry = tarfile.TarInfo("over-budget.bin")
        entry.size = len(payload)
        tar.addfile(entry, io.BytesIO(payload))
    assert container.put_archive("/data", archive.getvalue())
    violations = runtime.enforce_storage()
    assert violations[0][0] == container_id
    assert runtime.inspect(container_id, False).status == "exited"
    assert runtime.storage.volumes()[0].used_bytes >= len(payload)
    assert runtime.storage_errors
    runtime.enforce_storage()
    assert runtime.storage_errors  # Retained data remains over quota after stop.


async def test_real_worker_websocket_lifecycle_and_owner_controls(docker_runtime):
    runtime, state = docker_runtime
    command = real_command()
    running = asyncio.Future()
    owner_done = asyncio.Event()
    completed = asyncio.Future()
    heartbeats = []

    async def conversation(socket):
        assert socket.request.headers["X-Worker-ID"] == runtime.worker_id
        await socket.send(command.model_dump_json())

        async def result_for(request_id):
            while True:
                message = WORKER_MESSAGE_ADAPTER.validate_json(await socket.recv())
                if message.type == "heartbeat":
                    heartbeats.append(message)
                if (
                    message.type == "command_result"
                    and message.request_id == request_id
                ):
                    assert message.success, message.message
                    return message

        first = await result_for(command.request_id)
        running.set_result(first.container_id)
        await owner_done.wait()
        inspect = InspectContainerCommand(
            request_id=uuid4(), container_id=first.container_id
        )
        await socket.send(inspect.model_dump_json())
        inspected = await result_for(inspect.request_id)
        assert "state=running" in inspected.message
        stop = StopContainerCommand(
            request_id=uuid4(),
            deployment_id=command.deployment_id,
            container_id=first.container_id,
        )
        await socket.send(stop.model_dump_json())
        await result_for(stop.request_id)
        completed.set_result(True)
        await socket.wait_closed()

    async def handler(socket):
        try:
            await conversation(socket)
        except Exception as exc:  # noqa: BLE001 -- relay fixture failures immediately to the test
            target = running if not running.done() else completed
            if not target.done():
                target.set_exception(exc)

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        runtime.settings.control_plane_url = f"http://127.0.0.1:{port}"
        journal = RequestJournal(state)
        lifecycle = ControlPlaneLifecycle(runtime.settings, runtime.worker_id)
        dispatcher = CommandDispatcher(runtime, journal, runtime.settings)
        app = WorkerApplication(runtime, dispatcher, lifecycle, state)
        task = asyncio.create_task(app.run(install_signals=False))
        try:
            container_id = await asyncio.wait_for(running, 90)
            assert (await send_control(state, "pause"))["success"]
            assert (
                await asyncio.to_thread(runtime.inspect, container_id, False)
            ).status == "paused"
            assert (await send_control(state, "resume"))["success"]
            owner_done.set()
            await asyncio.wait_for(completed, 20)
            assert heartbeats
            assert (await send_control(state, "disconnect"))["success"]
            await asyncio.wait_for(task, 20)
        finally:
            app.stop.set()
            await asyncio.wait_for(task, 20)
            await lifecycle.close()
            journal.close()


async def test_real_supervisor_exit_fences_container_without_gateway(docker_runtime):
    runtime, state = docker_runtime
    container_id = runtime.run(real_command())
    runtime.settings.require_control_plane_lease = True
    assert runtime.inspect(container_id, False).status == "running"
    app = WorkerApplication(runtime, Mock(), Mock(), state)
    app.control.start = AsyncMock()
    app.control.close = AsyncMock()
    app.gateway.run = AsyncMock()
    app.stop.set()
    await app.run(install_signals=False)
    assert runtime.inspect(container_id, False).status == "exited"
    assert not runtime.lease_valid
