"""Heartbeats remain independent of slow image pulls and command execution."""

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from docker.errors import DockerException, NotFound
from shared.contracts import ContainerLogsEvent, ContainerStatusEvent
from websockets.exceptions import ConnectionClosed

from worker_agent.communication.lifecycle import ControlPlaneUnavailable
from worker_agent.docker_runtime.logs import LogCollector
from worker_agent.security.auth import WorkerAuthenticationError

LOGGER = logging.getLogger(__name__)


async def wait_interval(stop, seconds):
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except TimeoutError:
        pass


class WorkerReporter:
    def __init__(self, runtime, gateway, lifecycle, state):
        self.runtime = runtime
        self.gateway = gateway
        self.lifecycle = lifecycle
        self.state = state
        self.settings = runtime.settings
        self.logs = LogCollector(self.settings)
        self.last_status = {}

    async def heartbeat(self):
        snapshot, heartbeat = await asyncio.to_thread(self.runtime.telemetry)
        await asyncio.to_thread(
            self.state.write_json, "snapshot.json", snapshot.model_dump(mode="json")
        )
        if self.gateway.connected.is_set():
            if (
                not self.settings.require_control_plane_lease
                or self.lifecycle.lease_id is not None
            ):
                try:
                    await self.lifecycle.publish_snapshot(snapshot)
                except ControlPlaneUnavailable:
                    LOGGER.warning(
                        "Snapshot HTTP publication unavailable; heartbeat continues"
                    )
            await self.gateway.send(heartbeat)

    async def reconcile(self):
        self.last_status.clear()
        try:
            await self.heartbeat()
            containers = await asyncio.to_thread(self.runtime.containers)
        except WorkerAuthenticationError:
            raise
        except (DockerException, OSError, ValueError, RuntimeError) as exc:
            LOGGER.warning(
                "Initial reconciliation unavailable (%s)", type(exc).__name__
            )
            return
        for container in containers:
            try:
                inspection = await asyncio.to_thread(
                    self.runtime.inspect, container.id, False
                )
                await self.gateway.send(inspection.event())
                self.last_status[container.id] = (inspection.status, inspection.health)
            except NotFound:
                continue

    async def heartbeat_loop(self, stop):
        while not stop.is_set():
            try:
                await self.heartbeat()
            except (
                DockerException,
                OSError,
                ValueError,
                RuntimeError,
                ConnectionClosed,
            ) as exc:
                # Authentication errors are RuntimeError subclasses but must be fatal.
                if isinstance(exc, WorkerAuthenticationError):
                    raise
                LOGGER.warning("Heartbeat unavailable (%s)", type(exc).__name__)
            await wait_interval(stop, self.settings.heartbeat_interval)

    async def poll_events(self):
        try:
            stopped = await asyncio.to_thread(self.runtime.enforce_storage)
        except (DockerException, OSError, RuntimeError, ValueError) as exc:
            self.runtime.storage_errors = ["Storage measurement unavailable"]
            LOGGER.warning("Storage measurement unavailable (%s)", type(exc).__name__)
            return
        for container_id, deployment_id, reason in stopped:
            await self.gateway.send(
                ContainerLogsEvent(
                    deployment_id=UUID(deployment_id),
                    container_id=container_id,
                    log_level="error",
                    message=reason,
                    timestamp=datetime.now(UTC),
                )
            )
            await self.gateway.send(
                ContainerStatusEvent(
                    deployment_id=UUID(deployment_id),
                    container_id=container_id,
                    status="unhealthy",
                    timestamp=datetime.now(UTC),
                )
            )
        containers = await asyncio.to_thread(self.runtime.containers)
        self.logs.retain({item.id for item in containers})
        for container in containers:
            try:
                inspection = await asyncio.to_thread(
                    self.runtime.inspect, container.id, False
                )
                status = (inspection.status, inspection.health)
                if status != self.last_status.get(container.id):
                    await self.gateway.send(inspection.event())
                    self.last_status[container.id] = status
                for event in await asyncio.to_thread(self.logs.collect, container):
                    await self.gateway.send(event)
            except NotFound:
                continue

    async def event_loop(self, stop):
        while not stop.is_set():
            if self.gateway.connected.is_set():
                try:
                    await self.poll_events()
                except (
                    DockerException,
                    OSError,
                    ValueError,
                    RuntimeError,
                    ConnectionClosed,
                ) as exc:
                    LOGGER.warning(
                        "Container event polling unavailable (%s)", type(exc).__name__
                    )
            await wait_interval(stop, self.settings.heartbeat_interval)
