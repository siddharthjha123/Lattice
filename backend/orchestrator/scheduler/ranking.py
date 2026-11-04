"""Deterministic, compatibility-aware ranking of complete physical workers."""

from uuid import UUID

from shared.contracts import (
    PositiveFloat,
    PositiveInt,
    ResourceReservation,
    WorkerCapacity,
    WorkerId,
    WorkerSnapshot,
)
from shared.enums import ApplicationType, WorkerStatus

from orchestrator._inputs import compatibility_errors, reservation_ledger, worker_index
from orchestrator.scheduler.capacity import (
    calculate_worker_capacity,
    has_sufficient_capacity,
)


def rank_workers(
    workers: list[WorkerSnapshot],
    reservations: list[ResourceReservation],
    required_cpu: PositiveFloat,
    required_ram: PositiveFloat,
    required_storage: PositiveFloat,
    required_slots: PositiveInt = 1,
    excluded_worker_ids: set[WorkerId] | None = None,
    *,
    active_reservation_ids: set[UUID] | None = None,
    required_architecture: str | None = None,
    application_type: ApplicationType | None = None,
) -> list[tuple[WorkerSnapshot, WorkerCapacity]]:
    ledger = reservation_ledger(reservations)
    eligible = []
    for worker in worker_index(workers).values():
        if (
            worker.worker_id in (excluded_worker_ids or ())
            or worker.status != WorkerStatus.ONLINE
        ):
            continue
        if compatibility_errors(worker, required_architecture, application_type):
            continue
        capacity = calculate_worker_capacity(
            worker, ledger, active_reservation_ids=active_reservation_ids
        )
        sufficient, _ = has_sufficient_capacity(
            capacity, required_cpu, required_ram, required_storage, required_slots
        )
        if sufficient:
            occupied = worker.max_containers - capacity.available_container_slots
            eligible.append((worker, capacity, occupied))
    eligible.sort(
        key=lambda item: (
            item[2],
            -item[1].available_ram_gb,
            -item[1].available_cpu_cores,
            -item[1].available_storage_gb,
            item[0].worker_id,
        )
    )
    return [(worker, capacity) for worker, capacity, _ in eligible]
