"""Canonical ORM-to-contract conversion and reservation reconciliation."""

from datetime import UTC

from shared.contracts import Box as BoxContract
from shared.contracts import ResourceReservation as ReservationContract
from shared.contracts import WorkerSnapshot
from shared.enums import WorkerStatus

from control_plane.database.models import Box, Replica, ResourceReservation, Worker


def aware(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def worker_snapshot(worker):
    return WorkerSnapshot(
        worker_id=worker.worker_id,
        hostname=worker.hostname,
        status=WorkerStatus.OFFLINE if worker.draining else worker.status,
        cpu_cores=worker.cpu_cores,
        available_cpu_cores=min(worker.cpu_cores, worker.available_cpu_cores),
        total_ram_gb=worker.total_ram_gb,
        available_ram_gb=min(worker.total_ram_gb, worker.available_ram_gb),
        total_storage_gb=worker.total_storage_gb,
        available_storage_gb=min(worker.total_storage_gb, worker.available_storage_gb),
        active_container_count=worker.active_container_count,
        max_containers=worker.max_containers,
        architecture=worker.architecture,
        supported_runtimes=worker.supported_runtimes,
        last_heartbeat=aware(worker.last_heartbeat or worker.registered_at),
    )


def box_contract(box):
    return BoxContract(
        **{field: getattr(box, field) for field in BoxContract.model_fields}
    )


def reservation_contract(row):
    return ReservationContract(
        **{field: getattr(row, field) for field in ReservationContract.model_fields}
    )


def scheduling_context(session, *, lock=False, pool_id=None):
    query = (
        session.query(Worker)
        .filter(Worker.deleted_at.is_(None))
        .order_by(Worker.worker_id)
    )
    if pool_id is not None:
        query = query.filter(Worker.pool_id == pool_id)
    if lock:
        query = query.with_for_update()
    workers = query.all()
    rows = session.query(ResourceReservation).all()
    replicas = session.query(Replica).all()
    boxes = {row.box_id: row for row in session.query(Box).all()}
    by_worker = {row.worker_id: row for row in workers}
    active = set()
    for reservation in rows:
        worker = by_worker.get(reservation.worker_id)
        box = boxes.get(reservation.box_id)
        if worker is None or box is None or worker.snapshot_at is None:
            continue
        for replica in replicas:
            if (
                replica.worker_id != worker.worker_id
                or replica.deployment_id != box.deployment_id
            ):
                continue
            if replica.container_status not in {
                "created",
                "running",
                "paused",
                "restarting",
            }:
                continue
            if replica.reported_at is None or aware(replica.reported_at) > aware(
                worker.snapshot_at
            ):
                continue
            # A complete allocation must be reflected by a fresh snapshot; count
            # and lifecycle data come from the authenticated worker session.
            if (
                replica.container_id in worker.running_containers
                and worker.active_container_count > 0
            ):
                active.add(reservation.reservation_id)
    return (
        [worker_snapshot(row) for row in workers],
        [reservation_contract(row) for row in rows],
        active,
    )
