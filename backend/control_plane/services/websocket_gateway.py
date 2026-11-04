"""Session-bound authenticated worker transport and command correlation."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from shared.contracts import (
    WORKER_MESSAGE_ADAPTER,
    CommandResult,
    ContainerLogsEvent,
    ContainerStatusEvent,
    Heartbeat,
    InspectContainerCommand,
    LeaseGrant,
    RunContainerCommand,
    StopContainerCommand,
)

from control_plane.config import settings
from control_plane.database.models import (
    DeploymentEvent,
    DeploymentLog,
    Replica,
    Worker,
)
from control_plane.services.auth import hash_token

LOGGER = logging.getLogger(__name__)


@dataclass
class Pending:
    worker_id: str
    socket: object
    command: object
    future: asyncio.Future


class WorkerConnectionManager:
    def __init__(self, database=None, config=None):
        self.db = database
        self.config = config or settings
        self.active_connections = {}
        self.sessions = {}
        self._pending_commands = {}
        self.send_locks = {}
        self.on_failure = None

    async def authenticate_worker(self, token, worker_id=None):
        if not token or self.db is None:
            return None
        digest = hash_token(token, self.config)

        def authenticate(session):
            worker = (
                session.query(Worker)
                .filter_by(token_hash=digest, deleted_at=None)
                .first()
            )
            if (
                worker is None
                or worker_id is not None
                and worker.worker_id != worker_id
            ):
                return None
            return worker.worker_id

        return await self.db.run(authenticate)

    def is_worker_connected(self, worker_id):
        return worker_id in self.active_connections

    async def _send(self, worker_id, payload):
        async with self.send_locks.setdefault(worker_id, asyncio.Lock()):
            socket = self.active_connections.get(worker_id)
            if socket is None:
                raise ConnectionError("Worker is disconnected")
            await socket.send_text(payload)

    async def connect(self, worker_id, socket):
        await socket.accept()
        previous = self.active_connections.get(worker_id)
        identity = uuid4()
        self.active_connections[worker_id] = socket
        self.sessions[worker_id] = identity
        if previous is not None and previous is not socket:
            self._fail_pending(worker_id, previous)
            try:
                await previous.close(
                    code=4001, reason="Replaced by a new authenticated session"
                )
            except RuntimeError:
                pass

        def connected(session):
            worker = (
                session.query(Worker)
                .filter_by(worker_id=worker_id)
                .with_for_update()
                .first()
            )
            if worker is None or worker.deleted_at is not None:
                raise PermissionError("Worker enrollment was deleted")
            worker.session_id = identity
            worker.lease_id = identity
            worker.draining = False
            worker.fenced_at = None
            worker.status = "unhealthy"
            worker.last_heartbeat = datetime.now(UTC)

        await self.db.run(connected)
        await self.grant_lease(worker_id, socket)

    async def grant_lease(self, worker_id, socket):
        if self.active_connections.get(worker_id) is not socket:
            return
        identity = self.sessions[worker_id]
        now = datetime.now(UTC)
        grant = LeaseGrant(
            worker_id=worker_id,
            lease_id=identity,
            issued_at=now,
            expires_at=now + timedelta(seconds=self.config.LEASE_SECONDS),
        )

        def persist(session):
            worker = session.get(Worker, worker_id)
            if (
                worker.deleted_at is not None
                or worker.session_id != identity
                or worker.draining
            ):
                return False
            worker.lease_expires_at = grant.expires_at
            return True

        if await self.db.run(persist):
            await self._send(worker_id, grant.model_dump_json())

    def _fail_pending(self, worker_id, socket):
        for pending in list(self._pending_commands.values()):
            if (
                pending.worker_id == worker_id
                and pending.socket is socket
                and not pending.future.done()
            ):
                pending.future.set_exception(
                    ConnectionResetError("Worker session disconnected")
                )

    async def disconnect(self, worker_id, socket):
        if self.active_connections.get(worker_id) is not socket:
            return
        self.active_connections.pop(worker_id, None)
        identity = self.sessions.pop(worker_id, None)
        self._fail_pending(worker_id, socket)

        def disconnected(session):
            worker = session.get(Worker, worker_id)
            if worker is not None and worker.session_id == identity:
                worker.status = "offline"
                worker.disconnected_at = datetime.now(UTC)

        await self.db.run(disconnected)
        if self.on_failure:
            self.on_failure(worker_id)

    async def send_worker_command(self, worker_id, command, timeout=None):
        socket = self.active_connections.get(worker_id)
        if socket is None:
            raise ConnectionError("Target worker is disconnected")
        existing = self._pending_commands.get(command.request_id)
        if existing is not None:
            if existing.worker_id != worker_id or existing.command != command:
                raise ValueError("Conflicting command request ID")
            return await asyncio.wait_for(
                asyncio.shield(existing.future), timeout or self.config.COMMAND_TIMEOUT
            )
        future = asyncio.get_running_loop().create_future()
        future.add_done_callback(
            lambda completed: (
                completed.exception() if not completed.cancelled() else None
            )
        )
        pending = Pending(worker_id, socket, command, future)
        self._pending_commands[command.request_id] = pending
        try:
            await self._send(worker_id, command.model_dump_json(exclude_none=True))
            return await asyncio.wait_for(
                asyncio.shield(future), timeout or self.config.COMMAND_TIMEOUT
            )
        finally:
            if self._pending_commands.get(command.request_id) is pending:
                self._pending_commands.pop(command.request_id, None)

    async def _handle_command_result(self, worker_id, result, socket=None):
        pending = self._pending_commands.get(result.request_id)
        if pending is None or pending.worker_id != worker_id:
            return
        if socket is not None and pending.socket is not socket:
            return
        if isinstance(pending.command, InspectContainerCommand) and result.success:
            inspection = result.inspection
            if (
                inspection is None
                or inspection.container_id != pending.command.container_id
                or result.container_id != inspection.container_id
            ):
                raise PermissionError("Invalid inspection correlation")
        if (
            isinstance(pending.command, RunContainerCommand)
            and result.container_id
            and self.db is not None
        ):

            def associate(session):
                replica = (
                    session.query(Replica)
                    .filter_by(request_id=result.request_id, worker_id=worker_id)
                    .first()
                )
                if replica is not None:
                    replica.container_id = result.container_id

            await self.db.run(associate)
        if (
            isinstance(pending.command, StopContainerCommand)
            and result.success
            and self.db is not None
        ):

            def stopped_identity(session):
                for replica in session.query(Replica).filter_by(
                    worker_id=worker_id, deployment_id=pending.command.deployment_id
                ):
                    name = f"lattice-{replica.deployment_id.hex[:12]}-{replica.replica_id.hex[:8]}"
                    if (
                        replica.container_id is None
                        and name == pending.command.container_id
                    ):
                        replica.container_id = result.container_id or name

            await self.db.run(stopped_identity)
        if not pending.future.done():
            pending.future.set_result(result)

    async def handle_worker_message(self, worker_id, raw_text, socket=None):
        if socket is not None and self.active_connections.get(worker_id) is not socket:
            return
        message = WORKER_MESSAGE_ADAPTER.validate_json(raw_text)
        if isinstance(message, CommandResult):
            await self._handle_command_result(worker_id, message, socket)
        elif isinstance(message, Heartbeat):
            if message.worker_id != worker_id:
                raise PermissionError("Heartbeat identity mismatch")

            def heartbeat(session):
                worker = session.get(Worker, worker_id)
                worker.last_heartbeat = datetime.now(UTC)
                worker.running_containers = message.running_containers
                # Full snapshots are authoritative for available CPU and limits;
                # utilization is not a substitute for resource reservation data.

            await self.db.run(heartbeat)
            if socket is not None:
                await self.grant_lease(worker_id, socket)
        elif isinstance(message, (ContainerStatusEvent, ContainerLogsEvent)):

            def persist(session):
                replicas = (
                    session.query(Replica)
                    .filter_by(worker_id=worker_id, deployment_id=message.deployment_id)
                    .all()
                )
                replica = next(
                    (
                        item
                        for item in replicas
                        if item.container_id == message.container_id
                    ),
                    None,
                )
                if replica is None and isinstance(message, ContainerStatusEvent):
                    replica = next(
                        (
                            item
                            for item in replicas
                            if item.container_id is None and item.status == "pending"
                        ),
                        None,
                    )
                if replica is None:
                    raise PermissionError(
                        "Container event does not belong to this worker/replica"
                    )
                if isinstance(message, ContainerLogsEvent):
                    session.add(
                        DeploymentLog(
                            deployment_id=message.deployment_id,
                            container_id=message.container_id,
                            log_level=message.log_level.value,
                            message=message.message,
                            timestamp=message.timestamp,
                        )
                    )
                else:
                    old = replica.container_status
                    replica.container_id = message.container_id
                    replica.container_status = message.status.value
                    replica.reported_at = datetime.now(UTC)
                    if message.status.value in {"exited", "dead", "stopped"}:
                        replica.status = "stopped"
                    elif message.status.value in {"paused", "unhealthy", "restarting"}:
                        replica.status = "unhealthy"
                    elif message.status.value == "running":
                        replica.status = "running"
                    session.add(
                        DeploymentEvent(
                            deployment_id=message.deployment_id,
                            event_type="container_status",
                            from_status=old,
                            to_status=message.status.value,
                            message="Authenticated container lifecycle observation",
                            timestamp=datetime.now(UTC),
                        )
                    )

            await self.db.run(persist)

    async def close(self):
        for worker_id, socket in list(self.active_connections.items()):
            await socket.close(code=1001, reason="Control Plane shutting down")
            self._fail_pending(worker_id, socket)
        self.active_connections.clear()
        self.sessions.clear()
