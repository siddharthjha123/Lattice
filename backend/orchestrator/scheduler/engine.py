"""Select only complete, compatible workers with protected Box allocations."""

from uuid import UUID

from shared.contracts import (
    Box,
    ResourceRequirements,
    ResourceReservation,
    WorkerId,
    WorkerSelectionResult,
    WorkerSnapshot,
)
from shared.enums import ApplicationType, WorkerStatus

from orchestrator._inputs import (
    application_errors,
    compatibility_errors,
    reservation_ledger,
    worker_index,
)
from orchestrator.scheduler.capacity import (
    calculate_worker_capacity,
    has_sufficient_capacity,
)


def select_deployment_worker(
    box: Box,
    workers: list[WorkerSnapshot],
    excluded_worker_ids: list[WorkerId] | None = None,
    *,
    reservations: list[ResourceReservation] | None = None,
    active_reservation_ids: set[UUID] | None = None,
    required_architecture: str | None = None,
    application_type: ApplicationType | None = None,
    application_requirements: ResourceRequirements | None = None,
) -> WorkerSelectionResult:
    """Prefer the assigned primary, standby, then another already reserved worker.

    The original two-argument interface treats assigned Box workers as trusted
    reservation evidence. It cannot choose an unassigned fallback. Integrated
    callers should always supply their complete ledger and active-ID mapping.
    """
    errors = application_errors(box, application_requirements)
    if errors:
        return WorkerSelectionResult(worker_id=None, reason="; ".join(errors))
    worker_map = worker_index(workers)
    ledger = None if reservations is None else reservation_ledger(reservations)
    excluded = set(excluded_worker_ids or ())
    active_ids = set(active_reservation_ids or ())
    if ledger is not None and active_ids - {item.reservation_id for item in ledger}:
        raise ValueError("active_reservation_ids includes an unknown reservation")
    candidates = []
    failures = []
    for worker_id in box.eligible_worker_ids:
        if worker_id in excluded:
            continue
        worker = worker_map.get(worker_id)
        if worker is None or worker.status != WorkerStatus.ONLINE:
            failures.append(f"{worker_id}: missing or offline")
            continue
        errors = compatibility_errors(worker, required_architecture, application_type)
        if errors:
            failures.append(f"{worker_id}: {', '.join(errors)}")
            continue
        if ledger is None:
            if worker_id not in {box.primary_worker_id, box.standby_worker_id}:
                failures.append(
                    f"{worker_id}: no reservation ledger for an unassigned fallback"
                )
                continue
            other_reservations = []
            candidate_active_ids = None
        else:
            if (
                worker.active_container_count
                and active_reservation_ids is None
                and any(item.worker_id == worker_id for item in ledger)
            ):
                failures.append(
                    f"{worker_id}: active_reservation_ids is required for reservation reconciliation"
                )
                continue
            own = [
                item
                for item in ledger
                if item.box_id == box.box_id and item.worker_id == worker_id
            ]
            if not own or not all(
                item.cpu_limit_cores >= box.cpu_limit_cores
                and item.ram_limit_gb >= box.ram_limit_gb
                and item.storage_limit_gb >= box.storage_limit_gb
                and item.container_slots >= 1
                for item in own
            ):
                failures.append(f"{worker_id}: no sufficient reservation for this Box")
                continue
            if any(item.reservation_id in active_ids for item in own):
                failures.append(
                    f"{worker_id}: Box allocation is already active; reconcile or stop it first"
                )
                continue
            own_ids = {item.reservation_id for item in own}
            # Release only this target's idle hold for the fit calculation. It is
            # still reserved in the caller's ledger, never available to other Boxes.
            other_reservations = [
                item for item in ledger if item.reservation_id not in own_ids
            ]
            candidate_active_ids = active_reservation_ids
        try:
            capacity = calculate_worker_capacity(
                worker, other_reservations, active_reservation_ids=candidate_active_ids
            )
            fits, deficits = has_sufficient_capacity(
                capacity, box.cpu_limit_cores, box.ram_limit_gb, box.storage_limit_gb
            )
        except ValueError as exc:
            failures.append(f"{worker_id}: {exc}")
            continue
        if not fits:
            failures.append(f"{worker_id}: {', '.join(deficits)}")
            continue
        preference = (
            0
            if worker_id == box.primary_worker_id
            else 1
            if worker_id == box.standby_worker_id
            else 2
        )
        candidates.append(
            (
                preference,
                worker.max_containers - capacity.available_container_slots,
                -capacity.available_ram_gb,
                -capacity.available_cpu_cores,
                -capacity.available_storage_gb,
                worker_id,
            )
        )
    if not candidates:
        return WorkerSelectionResult(
            worker_id=None,
            reason=f"No suitable worker available for Box '{box.box_id}': {'; '.join(failures)}",
        )
    selected = min(candidates)[-1]
    label = (
        "designated primary worker"
        if selected == box.primary_worker_id
        else "designated standby worker"
        if selected == box.standby_worker_id
        else "reserved eligible worker"
    )
    evidence = (
        "full reservation ledger"
        if ledger is not None
        else "trusted Box assignment; ledger not supplied"
    )
    return WorkerSelectionResult(
        worker_id=selected, reason=f"Selected {label} '{selected}' using {evidence}."
    )
