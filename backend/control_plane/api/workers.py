"""Provisioned worker identity, authenticated snapshots and safe disconnect."""

import re
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, field_validator
from shared.contracts import WorkerSnapshot
from shared.enums import WorkerStatus

from control_plane.database.models import (
    Box,
    Pool,
    Replica,
    ResourceReservation,
    Worker,
)
from control_plane.services.auth import (
    authorize_worker,
    generate_worker_token,
    hash_token,
    require_admin,
)
from control_plane.services.contracts import aware, worker_snapshot

router = APIRouter(prefix="/api/workers", tags=["workers"])


class WorkerRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    worker_id: str
    hostname: str
    cpu_cores: int
    total_ram_gb: float
    total_storage_gb: float
    max_containers: int
    architecture: str
    supported_runtimes: list[str]
    available_cpu_cores: float | None = None
    available_ram_gb: float | None = None
    available_storage_gb: float | None = None
    address: str = "127.0.0.1"

    @field_validator("worker_id")
    @classmethod
    def valid_worker_id(cls, value):
        from worker_agent.security.auth import validate_worker_id

        return validate_worker_id(value)

    @field_validator("address")
    @classmethod
    def valid_address(cls, value):
        try:
            parsed = ip_address(value)
        except ValueError:
            if not re.fullmatch(
                r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?", value
            ):
                raise ValueError(
                    "Worker address must be an IP address or hostname"
                ) from None
            return value
        if parsed.is_unspecified or parsed.is_multicast or parsed.is_link_local:
            raise ValueError("Worker address is not routable")
        return str(parsed)

    def snapshot(self):
        return WorkerSnapshot(
            worker_id=self.worker_id,
            hostname=self.hostname,
            status="offline",
            cpu_cores=self.cpu_cores,
            available_cpu_cores=self.available_cpu_cores
            if self.available_cpu_cores is not None
            else self.cpu_cores,
            total_ram_gb=self.total_ram_gb,
            available_ram_gb=self.available_ram_gb
            if self.available_ram_gb is not None
            else self.total_ram_gb,
            total_storage_gb=self.total_storage_gb,
            available_storage_gb=self.available_storage_gb
            if self.available_storage_gb is not None
            else self.total_storage_gb,
            active_container_count=0,
            max_containers=self.max_containers,
            architecture=self.architecture,
            supported_runtimes=self.supported_runtimes,
            last_heartbeat=datetime.now(UTC),
        )


@router.post("/register", status_code=201, dependencies=[Depends(require_admin)])
async def register_worker(payload: WorkerRegisterRequest, request: Request):
    ctx = request.app.state.context
    try:
        snapshot = payload.snapshot()
    except ValueError:
        raise HTTPException(422, "Invalid worker hardware or resource limits") from None
    token = generate_worker_token()

    def provision(session):
        if session.get(Worker, payload.worker_id):
            raise HTTPException(
                409,
                "Worker already exists; reuse its token rather than silently rotating it",
            )
        values = snapshot.model_dump(mode="json", exclude={"last_heartbeat"})
        values["status"] = WorkerStatus.OFFLINE
        worker = Worker(
            **values, token_hash=hash_token(token, ctx.config), address=payload.address
        )
        session.add(worker)
        session.flush()
        return {
            "worker_id": worker.worker_id,
            "token": token,
            "status": "offline",
            "message": "Provisioned. Connect the authenticated worker to report live capacity.",
        }

    return await ctx.db.run(provision)


@router.get(
    "", dependencies=[Depends(require_admin)], response_model=list[WorkerSnapshot]
)
async def list_workers(request: Request):
    return await request.app.state.context.db.run(
        lambda session: [
            worker_snapshot(row)
            for row in session.query(Worker)
            .filter(Worker.deleted_at.is_(None))
            .order_by(Worker.worker_id)
        ]
    )


@router.get(
    "/{worker_id}", dependencies=[Depends(require_admin)], response_model=WorkerSnapshot
)
async def get_worker(worker_id: str, request: Request):
    def read(session):
        worker = session.get(Worker, worker_id)
        if worker is None or worker.deleted_at is not None:
            raise HTTPException(404, "Worker not found")
        return worker_snapshot(worker)

    return await request.app.state.context.db.run(read)


@router.post("/{worker_id}/snapshot")
async def publish_snapshot(worker_id: str, payload: WorkerSnapshot, request: Request):
    ctx = request.app.state.context
    if payload.worker_id != worker_id:
        raise HTTPException(403, "Snapshot identity mismatch")

    def publish(session):
        worker = authorize_worker(session, worker_id, request.headers, ctx.config)
        if not ctx.gateway.is_worker_connected(worker_id):
            raise HTTPException(409, "Worker WebSocket is not connected")
        if request.headers.get("x-worker-lease-id") != str(worker.lease_id):
            raise HTTPException(409, "Snapshot belongs to a stale worker session")
        for field in WorkerSnapshot.model_fields:
            if field not in {"worker_id", "status", "last_heartbeat"}:
                value = getattr(payload, field)
                setattr(
                    worker,
                    field,
                    [str(item) for item in value]
                    if field == "supported_runtimes"
                    else value,
                )
        worker.status = (
            WorkerStatus.OFFLINE if worker.draining else payload.status.value
        )
        worker.snapshot_at = datetime.now(UTC)
        worker.last_heartbeat = datetime.now(UTC)
        return {"accepted": True}

    return await ctx.db.run(publish)


@router.post("/{worker_id}/disconnect")
async def disconnect_worker(worker_id: str, request: Request):
    ctx = request.app.state.context

    def drain(session):
        worker = authorize_worker(
            session, worker_id, request.headers, ctx.config, allow_admin=True
        )
        worker.draining = True
        worker.status = WorkerStatus.OFFLINE
        worker.disconnected_at = datetime.now(UTC)

    await ctx.db.run(drain)
    ctx.manager.schedule_worker_failure(worker_id, intentional=True)
    return {
        "worker_id": worker_id,
        "status": "offline",
        "message": "Draining; workload handoff is being verified.",
    }


@router.post("/{worker_id}/rotate-token", dependencies=[Depends(require_admin)])
async def rotate_worker_token(worker_id: str, request: Request):
    """Recover an offline identity after secret rotation without duplicating it."""
    ctx = request.app.state.context
    token = generate_worker_token()

    def rotate(session):
        worker = (
            session.query(Worker)
            .filter_by(worker_id=worker_id)
            .with_for_update()
            .first()
        )
        if worker is None or worker.deleted_at is not None:
            raise HTTPException(404, "Worker not found")
        active = (
            session.query(Replica)
            .filter_by(worker_id=worker_id)
            .filter(Replica.status != "stopped")
            .first()
        )
        lease_pending = worker.lease_expires_at is not None and aware(
            worker.lease_expires_at
        ) + timedelta(seconds=ctx.config.FENCE_GRACE_SECONDS) > datetime.now(UTC)
        if (
            ctx.gateway.is_worker_connected(worker_id)
            or active is not None
            or lease_pending
        ):
            raise HTTPException(
                409,
                "Drain workloads and confirm worker fencing before rotating its token",
            )
        worker.token_hash = hash_token(token, ctx.config)
        worker.status = "offline"
        worker.session_id = worker.lease_id = worker.lease_expires_at = None
        worker.snapshot_at = worker.last_heartbeat = None
        worker.running_containers = []
        worker.active_container_count = 0
        worker.draining = False
        return {
            "worker_id": worker_id,
            "token": token,
            "status": "offline",
            "message": "Credential rotated. Reconfigure this worker; previous token is revoked.",
        }

    return await ctx.db.run(rotate)


@router.delete("/{worker_id}", status_code=204, dependencies=[Depends(require_admin)])
async def delete_worker(worker_id: str, request: Request):
    ctx = request.app.state.context

    def retire(session):
        worker = session.get(Worker, worker_id)
        if worker is None or worker.deleted_at is not None:
            raise HTTPException(404, "Worker not found")
        # Same parent->worker lock order as join, Box creation and pool retirement.
        if worker.pool_id is not None:
            session.query(Pool).filter_by(
                pool_id=worker.pool_id
            ).with_for_update().first()
        worker = (
            session.query(Worker)
            .filter_by(worker_id=worker_id)
            .with_for_update()
            .populate_existing()
            .first()
        )
        if worker.deleted_at is not None:
            raise HTTPException(404, "Worker not found")
        if ctx.gateway.is_worker_connected(worker_id) or ctx.relay.connected(worker_id):
            raise HTTPException(
                409,
                "Disconnect this worker and wait for both channels to close before deleting it",
            )
        now = datetime.now(UTC)
        if (
            worker.lease_expires_at is not None
            and aware(worker.lease_expires_at)
            + timedelta(seconds=ctx.config.FENCE_GRACE_SECONDS)
            > now
        ):
            raise HTTPException(
                409,
                "Worker lease fencing is still pending; wait for the lease and safety grace period to expire",
            )
        if (
            worker.active_container_count
            or worker.running_containers
            or session.query(Replica)
            .filter(Replica.worker_id == worker_id, Replica.status != "stopped")
            .first()
        ):
            raise HTTPException(
                409, "Stop and confirm all worker workloads before deleting it"
            )
        if session.query(ResourceReservation).filter_by(worker_id=worker_id).first():
            raise HTTPException(
                409, "Delete or release this worker's Box reservations first"
            )
        for box in session.query(Box).filter(Box.deleted_at.is_(None)):
            if worker_id in (box.eligible_worker_ids or []) or worker_id in (
                box.primary_worker_id,
                box.standby_worker_id,
            ):
                raise HTTPException(
                    409, "Delete Boxes that reference this worker before deleting it"
                )
        worker.deleted_at = now
        worker.status = "offline"
        worker.draining = True
        worker.session_id = worker.lease_id = None
        worker.token_hash = hash_token(generate_worker_token(), ctx.config)
        worker.available_cpu_cores = worker.available_ram_gb = (
            worker.available_storage_gb
        ) = 0

    await ctx.db.run(retire)
