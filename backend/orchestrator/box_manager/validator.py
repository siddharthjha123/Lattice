"""Validate candidate existence, health, compatibility and independent capacity."""

from uuid import UUID

from shared.contracts import (
    BoxCreationRequest,
    BoxValidationResult,
    ResourceReservation,
    WorkerSnapshot,
)
from shared.enums import ApplicationType, WorkerStatus

from orchestrator._inputs import compatibility_errors, reservation_ledger, worker_index
from orchestrator.scheduler.capacity import (
    calculate_worker_capacity,
    has_sufficient_capacity,
)


def validate_box_creation(
    request: BoxCreationRequest,
    workers: list[WorkerSnapshot],
    reservations: list[ResourceReservation],
    *,
    active_reservation_ids: set[UUID] | None = None,
    required_architecture: str | None = None,
    application_type: ApplicationType | None = None,
) -> BoxValidationResult:
    try:
        worker_map = worker_index(workers)
        ledger = reservation_ledger(reservations)
    except ValueError as exc:
        return BoxValidationResult(valid=False, errors=[str(exc)])
    errors = []
    capable = []
    deficits_by_worker = {}
    for worker_id in request.eligible_worker_ids:
        worker = worker_map.get(worker_id)
        if worker is None:
            errors.append(f"Worker '{worker_id}' does not exist.")
            continue
        if worker.status != WorkerStatus.ONLINE:
            errors.append(
                f"Worker '{worker_id}' is currently {worker.status.value}; all requested workers must be online."
            )
            continue
        try:
            deficits = compatibility_errors(
                worker, required_architecture, application_type
            )
            capacity = calculate_worker_capacity(
                worker, ledger, active_reservation_ids=active_reservation_ids
            )
            _, capacity_deficits = has_sufficient_capacity(
                capacity,
                request.cpu_limit_cores,
                request.ram_limit_gb,
                request.storage_limit_gb,
            )
            deficits.extend(capacity_deficits)
        except ValueError as exc:
            deficits = [str(exc)]
        if deficits:
            deficits_by_worker[worker_id] = deficits
        else:
            capable.append(worker_id)
    if not capable:
        details = "; ".join(
            f"Worker '{key}': {', '.join(value)}"
            for key, value in deficits_by_worker.items()
        )
        errors.append(
            f"No eligible worker has sufficient allocatable resources for Box '{request.name}': {details}"
        )
    if request.failover_enabled and len(capable) < 2:
        errors.append(
            f"Failover requires at least two online workers with sufficient capacity, but found only {len(capable)} capable worker(s)."
        )
    return BoxValidationResult(
        valid=not errors, errors=errors, eligible_worker_ids=capable
    )
