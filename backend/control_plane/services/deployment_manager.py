"""Persistent deployment lifecycle, readiness checks, stop and fenced failover."""

import asyncio
import logging
import math
from datetime import UTC, datetime, timedelta
from uuid import uuid4, uuid5

import httpx
from orchestrator.service import FailoverEngine
from shared.contracts import (
    FailoverDecision,
    InspectContainerCommand,
    RunContainerCommand,
    StopContainerCommand,
)

from control_plane.database.models import (
    Box,
    Deployment,
    DeploymentEvent,
    DeploymentLog,
    FailoverRecord,
    Replica,
    ResourceReservation,
    Worker,
)
from control_plane.logging import redact_message
from control_plane.services.application_http import application_http
from control_plane.services.contracts import aware, box_contract, scheduling_context
from control_plane.services.git_builder import ApplicationConfig
from control_plane.services.orchestrator_client import orchestrator_client

LOGGER = logging.getLogger(__name__)
ACTIVE = {"created", "running", "paused", "restarting", "pending"}


class PlacementUnavailable(RuntimeError):
    pass


class DeploymentCancelled(RuntimeError):
    pass


class DeploymentManager:
    def __init__(self, context):
        self.ctx = context
        self.db = context.db
        self.gateway = context.gateway
        self.config = context.config
        self.builder = context.builder
        self.jobs = {}
        self.dispatch_locks = {}
        self.failures = {}
        self.closed = False

    def schedule(self, deployment_id):
        if (
            self.closed
            or deployment_id in self.jobs
            and not self.jobs[deployment_id].done()
        ):
            return
        task = asyncio.create_task(self.execute_deployment_async(deployment_id))
        self.jobs[deployment_id] = task
        task.add_done_callback(
            lambda done: done.exception() if not done.cancelled() else None
        )

    def schedule_worker_failure(self, worker_id, intentional=False):
        if (
            self.closed
            or worker_id in self.failures
            and not self.failures[worker_id].done()
        ):
            return
        task = asyncio.create_task(self.worker_failed(worker_id, intentional))
        self.failures[worker_id] = task
        task.add_done_callback(
            lambda done: done.exception() if not done.cancelled() else None
        )

    async def log(self, deployment_id, message, level="info"):
        message = redact_message(message, self.config)
        await self.db.run(
            lambda session: session.add(
                DeploymentLog(
                    deployment_id=deployment_id,
                    log_level=level,
                    message=message.strip()[:16384],
                )
            )
        )

    async def transition(self, deployment_id, status, message):
        allowed = {
            "queued": {"building", "failed", "stopped"},
            "building": {"deploying", "failed", "stopped"},
            "deploying": {"running", "failed", "stopped"},
            "running": {"deploying", "failed", "stopped"},
            "failed": {"stopped"},
            "stopped": set(),
        }

        def update(session):
            deployment = session.get(Deployment, deployment_id)
            if deployment is None:
                raise ValueError("Deployment not found")
            previous = deployment.status
            if previous == status:
                return
            if status not in allowed[previous]:
                raise ValueError("Invalid deployment state transition")
            deployment.status = status
            deployment.updated_at = datetime.now(UTC)
            session.add(
                DeploymentEvent(
                    deployment_id=deployment_id,
                    event_type="status_transition",
                    from_status=previous,
                    to_status=status,
                    message=message,
                )
            )

        await self.db.run(update)

    async def check_cancelled(self, deployment_id):
        cancelled = await self.db.run(
            lambda session: session.get(Deployment, deployment_id).stop_requested
        )
        if cancelled or self.closed:
            raise DeploymentCancelled("Deployment cancellation requested")

    async def execute_deployment_async(self, deployment_id):
        attempted = False
        try:
            await self.check_cancelled(deployment_id)

            def read(session):
                row = session.get(Deployment, deployment_id)
                return (
                    row.status,
                    row.repository_url,
                    row.branch,
                    row.application_type,
                    dict(row.application_config),
                    row.image_reference,
                )

            status, url, branch, app_type, overrides, image = await self.db.run(read)
            if status not in {"queued", "building", "deploying"}:
                return
            if status != "deploying":
                if status == "queued":
                    await self.transition(
                        deployment_id,
                        "building",
                        "Cloning and building the configured application",
                    )
                path, stream = await self.builder.clone_repository(
                    url, branch, deployment_id
                )
                try:
                    async for line in stream:
                        await self.check_cancelled(deployment_id)
                        await self.log(deployment_id, line)
                finally:
                    await stream.aclose()
                application = self.builder.load_application_config(path, overrides)
                await asyncio.to_thread(
                    self.builder.prepare_dockerfile, path, app_type, application
                )

                def build_platform(session):
                    deployment = session.get(Deployment, deployment_id)
                    box = session.get(Box, deployment.box_id)
                    worker = (
                        session.get(Worker, box.primary_worker_id)
                        if box.primary_worker_id
                        else None
                    )
                    arch = (
                        worker.architecture
                        if worker and worker.application_transport == "relay"
                        else ""
                    )
                    return {
                        "x86_64": "linux/amd64",
                        "amd64": "linux/amd64",
                        "aarch64": "linux/arm64",
                        "arm64": "linux/arm64",
                    }.get(arch)

                platform = await self.db.run(build_platform)
                if platform:
                    tag, stream = await self.builder.build_docker_image(
                        path, deployment_id, platform=platform
                    )
                else:
                    tag, stream = await self.builder.build_docker_image(
                        path, deployment_id
                    )
                try:
                    async for line in stream:
                        await self.check_cancelled(deployment_id)
                        await self.log(deployment_id, line)
                finally:
                    await stream.aclose()
                await self.check_cancelled(deployment_id)
                image = await self.builder.publish(tag)
                architecture = await self.builder.image_architecture(tag)
                process = await asyncio.create_subprocess_exec(
                    "git",
                    "-C",
                    str(path),
                    "rev-parse",
                    "HEAD",
                    stdout=asyncio.subprocess.PIPE,
                )
                commit, _ = await process.communicate()

                def built(session):
                    row = session.get(Deployment, deployment_id)
                    row.image_reference = image
                    row.architecture = architecture
                    row.application_config = application.model_dump()
                    row.commit_sha = commit.decode().strip()

                await self.db.run(built)
                await self.transition(
                    deployment_id,
                    "deploying",
                    "Published an immutable image; preparing worker dispatch",
                )
            await self.check_cancelled(deployment_id)
            replica_id, worker_id = await self.wait_for_placement(deployment_id)
            await self.wait_for_worker(worker_id)
            attempted = True
            await self.log(
                deployment_id, f"Requesting container startup on worker {worker_id}"
            )
            result = await self.dispatch_run(deployment_id, replica_id, worker_id)
            if not result.success or not result.container_id:
                raise RuntimeError("Worker did not confirm container startup")
            await self.check_cancelled(deployment_id)
            await self.verify_ready(deployment_id, replica_id, result.container_id)
            await self.mark_running(deployment_id, replica_id)
        except DeploymentCancelled:
            await self.stop_deployment(deployment_id, wait_for_job=False)
        except Exception as exc:  # noqa: BLE001 -- persist failure without disclosing secrets
            if await self.db.run(
                lambda session: session.get(Deployment, deployment_id).stop_requested
            ):
                await self.stop_deployment(deployment_id, wait_for_job=False)
                return
            message = (
                str(exc)
                if isinstance(exc, (ValueError, RuntimeError))
                else f"Deployment operation failed ({type(exc).__name__})"
            )
            await self.log(deployment_id, message, "error")
            await self.fail(deployment_id, message, attempted)
        finally:
            await asyncio.to_thread(self.builder.cleanup, deployment_id)

    async def dispatch_run(self, deployment_id, replica_id, worker_id):
        async with self.dispatch_locks.setdefault(deployment_id, asyncio.Lock()):
            await self.check_cancelled(deployment_id)
            command = await self.run_command(deployment_id, replica_id)
            try:
                return await self.gateway.send_worker_command(worker_id, command)
            except TimeoutError:
                raise RuntimeError(
                    f"Worker {worker_id} did not acknowledge container startup within "
                    f"{self.config.COMMAND_TIMEOUT:g}s. Check image download, registry "
                    "access and the worker logs. Workload cleanup still requires "
                    "a stop acknowledgment or lease fencing."
                ) from None

    async def wait_for_placement(self, deployment_id):
        # Builds temporarily occupy daemon capacity. Keep the funded reservation
        # while waiting for a fresh authenticated snapshot after build completion.
        deadline = asyncio.get_running_loop().time() + self.config.COMMAND_TIMEOUT
        while True:
            await self.check_cancelled(deployment_id)
            try:
                return await self.prepare_replica(deployment_id)
            except PlacementUnavailable:
                if asyncio.get_running_loop().time() >= deadline:
                    raise
                await asyncio.sleep(0.15)

    async def prepare_replica(self, deployment_id):
        def prepare(session):
            workers, reservations, active_ids = scheduling_context(session, lock=True)
            deployment = session.get(Deployment, deployment_id)
            box = session.get(Box, deployment.box_id)
            if box.deployment_id != deployment_id or deployment.stop_requested:
                raise DeploymentCancelled("Deployment no longer owns the Box")
            existing = (
                session.query(Replica)
                .filter_by(deployment_id=deployment_id, role="primary")
                .filter(Replica.status != "stopped")
                .first()
            )
            if existing is not None:
                return existing.replica_id, existing.worker_id
            selection = orchestrator_client.select_deployment_worker(
                box_contract(box),
                workers,
                reservations=reservations,
                active_reservation_ids=active_ids,
                required_architecture=deployment.architecture,
                application_type=deployment.application_type,
            )
            if selection.worker_id is None:
                raise PlacementUnavailable(selection.reason)
            identity = uuid4()
            config = ApplicationConfig.model_validate(deployment.application_config)
            session.add(
                Replica(
                    replica_id=identity,
                    deployment_id=deployment_id,
                    worker_id=selection.worker_id,
                    request_id=uuid5(identity, "run"),
                    role="primary",
                    status="pending",
                    internal_port=config.internal_port,
                )
            )
            session.flush()
            return identity, selection.worker_id

        return await self.db.run(prepare)

    async def wait_for_worker(self, worker_id):
        deadline = asyncio.get_running_loop().time() + self.config.COMMAND_TIMEOUT
        while not self.gateway.is_worker_connected(worker_id):
            if asyncio.get_running_loop().time() >= deadline:
                raise ConnectionError(
                    "Worker did not reconnect before dispatch deadline"
                )
            await asyncio.sleep(0.1)

    async def run_command(self, deployment_id, replica_id):
        def command(session):
            deployment = session.get(Deployment, deployment_id)
            box = session.get(Box, deployment.box_id)
            replica = session.get(Replica, replica_id)
            config = ApplicationConfig.model_validate(deployment.application_config)
            return RunContainerCommand(
                request_id=replica.request_id,
                deployment_id=deployment_id,
                box_id=box.box_id,
                image_reference=deployment.image_reference,
                container_name=f"lattice-{deployment_id.hex[:12]}-{replica_id.hex[:8]}",
                cpu_limit_cores=box.cpu_limit_cores,
                ram_limit_mb=math.ceil(box.ram_limit_gb * 1024),
                storage_limit_gb=box.storage_limit_gb,
                internal_port=replica.internal_port,
                environment_variables=config.environment_variables
                | {
                    "PORT": str(replica.internal_port),
                    "DEPLOYMENT_ID": str(deployment_id),
                },
                role="primary",
            )

        return await self.db.run(command)

    async def verify_ready(self, deployment_id, replica_id, container_id):
        deadline = asyncio.get_running_loop().time() + self.config.READINESS_TIMEOUT
        while asyncio.get_running_loop().time() < deadline:
            await self.check_cancelled(deployment_id)

            def details(session):
                replica = session.get(Replica, replica_id)
                worker = session.get(Worker, replica.worker_id)
                deployment = session.get(Deployment, deployment_id)
                return (
                    replica.worker_id,
                    worker.address,
                    worker.application_transport,
                    ApplicationConfig.model_validate(deployment.application_config),
                )

            worker_id, address, transport, application = await self.db.run(details)
            result = await self.gateway.send_worker_command(
                worker_id,
                InspectContainerCommand(request_id=uuid4(), container_id=container_id),
            )
            inspection = result.inspection
            if (
                not result.success
                or inspection is None
                or inspection.deployment_id != deployment_id
            ):
                raise RuntimeError("Worker inspection could not verify the deployment")
            if inspection.status.value in {"exited", "dead", "stopped"}:
                raise RuntimeError("Application exited before readiness")
            binding = next(
                (
                    item
                    for item in inspection.port_bindings
                    if item.internal_port == application.internal_port
                    and item.protocol == "tcp"
                ),
                None,
            )
            if (
                binding is not None
                and inspection.status.value == "running"
                and inspection.health != "unhealthy"
            ):
                try:
                    response = await application_http(
                        self.ctx,
                        worker_id,
                        transport,
                        address,
                        binding.host_port,
                        deployment_id,
                        container_id,
                        application.internal_port,
                        "GET",
                        application.readiness_path,
                        timeout=2,
                    )
                    ready = (
                        200 <= response.status < 400 and inspection.health != "starting"
                    )
                except (httpx.HTTPError, ConnectionError, TimeoutError, ValueError):
                    ready = False
                if ready:

                    def persist(session, observed=inspection):
                        replica = session.get(Replica, replica_id)
                        replica.container_id = container_id
                        replica.container_status = "running"
                        replica.status = "running"
                        replica.health = observed.health
                        replica.port_bindings = [
                            item.model_dump() for item in observed.port_bindings
                        ]

                    await self.db.run(persist)
                    return
            await asyncio.sleep(0.2)
        raise RuntimeError("Application readiness deadline exceeded")

    async def mark_running(self, deployment_id, replica_id):
        def mark(session):
            deployment = session.get(Deployment, deployment_id)
            box = session.get(Box, deployment.box_id)
            replica = session.get(Replica, replica_id)
            if deployment.stop_requested or box.deployment_id != deployment_id:
                raise DeploymentCancelled("Deployment was cancelled during readiness")
            box.primary_worker_id = replica.worker_id
            box.status = (
                "deployed"
                if not box.failover_enabled or box.standby_worker_id
                else "degraded"
            )
            deployment.public_url = (
                f"https://app-{deployment_id.hex}.{self.config.APP_DOMAIN}/"
                if self.config.APP_DOMAIN
                else self.config.PUBLIC_BASE_URL.rstrip("/") + f"/apps/{deployment_id}/"
            )

        await self.db.run(mark)
        await self.transition(
            deployment_id, "running", "Application readiness verified and route enabled"
        )

    async def stop_deployment(
        self, deployment_id, wait_for_job=True, preserve_failure=False
    ):
        def request_stop(session):
            deployment = session.get(Deployment, deployment_id)
            if deployment is None:
                raise ValueError("Deployment not found")
            deployment.stop_requested = True
            deployment.public_url = None
            return [
                (row.replica_id, row.worker_id, row.container_id)
                for row in session.query(Replica)
                .filter_by(deployment_id=deployment_id)
                .filter(Replica.status != "stopped")
            ]

        replicas = await self.db.run(request_stop)
        pending = False
        async with self.dispatch_locks.setdefault(deployment_id, asyncio.Lock()):
            for replica_id, worker_id, container_id in replicas:
                # The run may still be executing or may have failed before returning
                # an ID. Docker accepts its deterministic name as an identifier.
                # The worker's serial queue executes this stop after that accepted run.
                container_id = (
                    container_id or f"lattice-{deployment_id.hex[:12]}-{replica_id.hex[:8]}"
                )
                if not self.gateway.is_worker_connected(worker_id):
                    if not await self.is_fenced(worker_id):
                        pending = True
                        continue
                else:
                    try:
                        result = await self.gateway.send_worker_command(
                            worker_id,
                            StopContainerCommand(
                                request_id=uuid4(),
                                deployment_id=deployment_id,
                                container_id=container_id,
                            ),
                        )
                        if not result.success:
                            pending = True
                            continue
                    except (ConnectionError, TimeoutError):
                        pending = True
                        continue
                await self.db.run(
                    lambda session, key=replica_id: self._stopped_replica(session, key)
                )
        job = self.jobs.get(deployment_id)
        if (
            wait_for_job
            and job is not None
            and job is not asyncio.current_task()
            and not job.done()
        ):
            try:
                await asyncio.wait_for(asyncio.shield(job), 5)
            except TimeoutError:
                pending = True
        if job is not None and job is not asyncio.current_task() and not job.done():
            pending = True
        if not pending:
            await self.finalize_stop(deployment_id, preserve_failure)
        return not pending

    @staticmethod
    def _stopped_replica(session, identity):
        replica = session.get(Replica, identity)
        replica.status = "stopped"
        replica.container_status = "stopped"

    async def finalize_stop(self, deployment_id, preserve_failure=False):
        def finalize(session):
            scheduling_context(session, lock=True)
            deployment = session.get(Deployment, deployment_id)
            box = session.get(Box, deployment.box_id)
            if any(
                row.status != "stopped"
                for row in session.query(Replica).filter_by(deployment_id=deployment_id)
            ):
                return False
            if box.deployment_id == deployment_id:
                session.query(ResourceReservation).filter_by(box_id=box.box_id).delete()
                box.deployment_id = None
                box.status = "available"
            return not (preserve_failure and deployment.status == "failed")

        if await self.db.run(finalize):
            await self.transition(
                deployment_id,
                "stopped",
                "All workloads confirmed stopped; reservations released",
            )

    async def fail(self, deployment_id, message, attempted):
        message = redact_message(message, self.config)

        def failure(session):
            deployment = session.get(Deployment, deployment_id)
            deployment.failure_message = message[:2048]
            deployment.public_url = None
            box = session.get(Box, deployment.box_id)
            if not attempted and box.deployment_id == deployment_id:
                for replica in session.query(Replica).filter_by(
                    deployment_id=deployment_id
                ):
                    self._stopped_replica(session, replica.replica_id)
                session.query(ResourceReservation).filter_by(box_id=box.box_id).delete()
                box.deployment_id = None
                box.status = "failed"
            elif attempted:
                deployment.stop_requested = True
                box.status = "degraded"

        await self.db.run(failure)
        await self.transition(deployment_id, "failed", message)
        if attempted:
            await self.stop_deployment(
                deployment_id, wait_for_job=False, preserve_failure=True
            )

    async def is_fenced(self, worker_id):
        def fenced(session):
            worker = session.get(Worker, worker_id)
            if worker is None or worker.lease_expires_at is None:
                return False
            deadline = aware(worker.lease_expires_at) + timedelta(
                seconds=self.config.FENCE_GRACE_SECONDS
            )
            return datetime.now(UTC) >= deadline

        return await self.db.run(fenced)

    async def worker_failed(self, worker_id, intentional=False):
        def affected(session):
            worker = session.get(Worker, worker_id)
            if worker is None:
                return []
            return [
                row.deployment_id
                for row in session.query(Box)
                .filter_by(primary_worker_id=worker_id)
                .filter(Box.deployment_id.is_not(None))
            ]

        draining = await self.db.run(
            lambda session: bool(session.get(Worker, worker_id).draining)
        )
        intentional = (
            intentional or draining and self.gateway.is_worker_connected(worker_id)
        )
        for deployment_id in await self.db.run(affected):
            if (
                await self.db.run(
                    lambda session, key=deployment_id: (
                        session.get(Deployment, key).status
                    )
                )
                != "running"
            ):
                continue
            try:
                if intentional:

                    def replicas(session, current=deployment_id):
                        return [
                            (row.replica_id, row.container_id)
                            for row in session.query(Replica)
                            .filter_by(deployment_id=current, worker_id=worker_id)
                            .filter(Replica.status != "stopped")
                        ]

                    for identity, container_id in await self.db.run(replicas):
                        if container_id is None:
                            raise RuntimeError(
                                "Wait for pending worker execution before handoff"
                            )
                        result = await self.gateway.send_worker_command(
                            worker_id,
                            StopContainerCommand(
                                request_id=uuid4(),
                                deployment_id=deployment_id,
                                container_id=container_id,
                            ),
                        )
                        if not result.success:
                            raise RuntimeError("Primary did not confirm stop")
                        await self.db.run(
                            lambda session, key=identity: self._stopped_replica(
                                session, key
                            )
                        )
                elif not await self.is_fenced(worker_id):
                    return
                await self.recover(deployment_id, worker_id)
            except Exception as exc:  # noqa: BLE001 -- keep other affected deployments progressing
                LOGGER.warning("Worker recovery pending (%s)", type(exc).__name__)

    async def recover(self, deployment_id, failed_worker_id):
        def plan(session):
            workers, reservations, active_ids = scheduling_context(session, lock=True)
            deployment = session.get(Deployment, deployment_id)
            box = session.get(Box, deployment.box_id)
            if deployment.stop_requested or box.deployment_id != deployment_id:
                for row in session.query(Replica).filter_by(
                    deployment_id=deployment_id, worker_id=failed_worker_id
                ):
                    self._stopped_replica(session, row.replica_id)
                return None
            if box.primary_worker_id != failed_worker_id:
                return None
            records = (
                session.query(FailoverRecord)
                .filter_by(
                    deployment_id=deployment_id, failed_worker_id=failed_worker_id
                )
                .all()
            )
            engine = FailoverEngine(
                [
                    FailoverDecision(
                        **{
                            field: getattr(row, field)
                            for field in FailoverDecision.model_fields
                        }
                    )
                    for row in records
                ]
            )
            decision = engine.evaluate_failover(
                deployment_id,
                box_contract(box),
                workers,
                failed_worker_id,
                reservations=reservations,
                active_reservation_ids=active_ids,
                required_architecture=deployment.architecture,
                application_type=deployment.application_type,
            )
            record = records[0] if records else FailoverRecord(**decision.model_dump())
            if not records:
                session.add(record)
            if decision.replacement_worker_id is None:
                box.status = "failed"
                deployment.public_url = None
                if deployment.status == "running":
                    deployment.status = "failed"
                    deployment.failure_message = decision.reason
                    session.add(
                        DeploymentEvent(
                            deployment_id=deployment_id,
                            event_type="failover_unavailable",
                            from_status="running",
                            to_status="failed",
                            message=decision.reason,
                        )
                    )
                return None
            if record.state != "selecting_standby":
                return None
            target = decision.replacement_worker_id
            record.state = "redeploying"
            for replica in session.query(Replica).filter_by(
                deployment_id=deployment_id, worker_id=failed_worker_id
            ):
                self._stopped_replica(session, replica.replica_id)
            # Persist promotion atomically before dispatching. Remove old primary
            # hold only after acknowledged stop or lease/fence deadline.
            session.query(ResourceReservation).filter_by(
                box_id=box.box_id, worker_id=failed_worker_id
            ).delete()
            standby = (
                session.query(ResourceReservation)
                .filter_by(box_id=box.box_id, worker_id=target)
                .one()
            )
            standby.role = "primary"
            box.primary_worker_id = target
            box.standby_worker_id = None
            box.status = "degraded"
            identity = uuid5(decision.decision_id, "replica")
            app = ApplicationConfig.model_validate(deployment.application_config)
            session.add(
                Replica(
                    replica_id=identity,
                    deployment_id=deployment_id,
                    worker_id=target,
                    request_id=decision.decision_id,
                    internal_port=app.internal_port,
                    role="primary",
                    status="pending",
                )
            )
            session.flush()
            return identity, target, decision.decision_id

        prepared = await self.db.run(plan)
        if prepared is None:
            return
        await self.dispatch_recovery(deployment_id, *prepared)

    async def dispatch_recovery(self, deployment_id, replica_id, target, decision_id):
        await self.transition(
            deployment_id,
            "deploying",
            "Confirmed primary fencing; redeploying to reserved standby",
        )
        try:
            await self.wait_for_worker(target)
            result = await self.dispatch_run(deployment_id, replica_id, target)
            if not result.success or not result.container_id:
                raise RuntimeError("Standby execution failed")
            await self.db.run(
                lambda session: setattr(
                    session.get(FailoverRecord, decision_id), "state", "health_check"
                )
            )
            await self.verify_ready(deployment_id, replica_id, result.container_id)
            await self.mark_running(deployment_id, replica_id)
            await self.db.run(
                lambda session: setattr(
                    session.get(FailoverRecord, decision_id), "state", "recovered"
                )
            )
        except Exception as exc:  # noqa: BLE001 -- persist failed recovery for inspection
            await self.db.run(
                lambda session: setattr(
                    session.get(FailoverRecord, decision_id), "state", "failed"
                )
            )
            await self.fail(
                deployment_id, f"Failover failed ({type(exc).__name__})", True
            )

    async def resume(self):
        def pending(session):
            recoveries = (
                session.query(FailoverRecord)
                .filter(FailoverRecord.state.in_(["redeploying", "health_check"]))
                .all()
            )
            recovery_ids = {row.deployment_id for row in recoveries}
            deployments = [
                row.deployment_id
                for row in session.query(Deployment).filter(
                    Deployment.status.in_(["queued", "building", "deploying"])
                )
                if row.deployment_id not in recovery_ids
            ]
            return deployments, [
                (
                    row.deployment_id,
                    uuid5(row.decision_id, "replica"),
                    row.replacement_worker_id,
                    row.decision_id,
                )
                for row in recoveries
            ]

        deployments, recoveries = await self.db.run(pending)
        for identity in deployments:
            self.schedule(identity)
        for deployment_id, replica_id, target, decision_id in recoveries:
            task = asyncio.create_task(
                self.dispatch_recovery(deployment_id, replica_id, target, decision_id)
            )
            task.add_done_callback(
                lambda done: done.exception() if not done.cancelled() else None
            )
            self.jobs[deployment_id] = task

    async def monitor(self, stop):
        while not stop.is_set():
            try:

                def stale(session):
                    now = datetime.now(UTC)
                    result = []
                    for worker in session.query(Worker).filter(
                        Worker.deleted_at.is_(None)
                    ):
                        timed_out = (
                            worker.last_heartbeat is None
                            or (now - aware(worker.last_heartbeat)).total_seconds()
                            > self.config.HEARTBEAT_TIMEOUT
                        )
                        if (
                            timed_out
                            or not self.gateway.is_worker_connected(worker.worker_id)
                            or worker.draining
                        ):
                            worker.status = "offline"
                            result.append(worker.worker_id)
                    return result

                for worker_id in await self.db.run(stale):
                    self.schedule_worker_failure(worker_id)

                def maintenance(session):
                    stopping = [
                        row.deployment_id
                        for row in session.query(Deployment).filter(
                            Deployment.stop_requested.is_(True),
                            Deployment.status != "stopped",
                        )
                    ]
                    broken = []
                    for row in session.query(Deployment).filter_by(
                        status="running", stop_requested=False
                    ):
                        box = session.get(Box, row.box_id)
                        worker = session.get(Worker, box.primary_worker_id)
                        if (
                            worker is None
                            or worker.draining
                            or worker.status != "online"
                        ):
                            continue
                        replicas = (
                            session.query(Replica)
                            .filter_by(
                                deployment_id=row.deployment_id,
                                worker_id=box.primary_worker_id,
                            )
                            .all()
                        )
                        if any(
                            replica.container_status
                            in {"exited", "dead", "stopped", "unhealthy"}
                            for replica in replicas
                        ):
                            broken.append(row.deployment_id)
                    return stopping, broken

                stopping, broken = await self.db.run(maintenance)
                for identity in stopping:
                    status = await self.db.run(
                        lambda session, key=identity: (
                            session.get(Deployment, key).status
                        )
                    )
                    await self.stop_deployment(
                        identity,
                        wait_for_job=False,
                        preserve_failure=status == "failed",
                    )
                for identity in broken:
                    await self.fail(
                        identity, "Application stopped or became unhealthy", True
                    )
            except Exception as exc:  # noqa: BLE001 -- a temporary DB failure must not kill monitoring
                LOGGER.warning("Worker monitor unavailable (%s)", type(exc).__name__)
            try:
                await asyncio.wait_for(stop.wait(), self.config.MONITOR_INTERVAL)
            except TimeoutError:
                pass

    async def shutdown(self):
        self.closed = True
        for task in list(self.jobs.values()) + list(self.failures.values()):
            if not task.done():
                task.cancel()
        await asyncio.gather(
            *self.jobs.values(), *self.failures.values(), return_exceptions=True
        )
