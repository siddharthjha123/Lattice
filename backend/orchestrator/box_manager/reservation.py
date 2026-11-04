"""Pure reservation plans; the Control Plane persists them atomically."""

from uuid import UUID, uuid4, uuid5

from shared.contracts import (
    BoxCreationRequest,
    PlacementDecision,
    ReservationReleaseResult,
    ResourceReservation,
    WorkerSnapshot,
)
from shared.enums import ApplicationType, ReplicaRole

from orchestrator._inputs import compatibility_errors, reservation_ledger, worker_index
from orchestrator.box_manager.validator import validate_box_creation
from orchestrator.scheduler.ranking import rank_workers


def _decision(request, box_id, reservations):
    primary = next(item for item in reservations if item.role == ReplicaRole.PRIMARY)
    standby = next(
        (item for item in reservations if item.role == ReplicaRole.STANDBY), None
    )
    reason = f"Successfully placed Box '{request.name}' with primary worker '{primary.worker_id}'"
    reason += f" and standby worker '{standby.worker_id}'." if standby else "."
    return PlacementDecision(
        box_id=box_id,
        primary_worker_id=primary.worker_id,
        standby_worker_id=standby.worker_id if standby else None,
        reason=reason,
        reservations=[item.model_copy(deep=True) for item in reservations],
    )


def create_box_placement(
    request: BoxCreationRequest,
    workers: list[WorkerSnapshot],
    reservations: list[ResourceReservation],
    *,
    box_id: UUID | None = None,
    active_reservation_ids: set[UUID] | None = None,
    required_architecture: str | None = None,
    application_type: ApplicationType | None = None,
) -> PlacementDecision:
    """Plan a new allocation or replay one using a caller-persisted stable Box ID.

    This function never mutates the supplied ledger. Callers must lock and save
    plans transactionally before dispatching workloads; a stale list is not a lock.
    """
    ledger = reservation_ledger(reservations)
    worker_map = worker_index(workers)
    stable_id = box_id or uuid4()
    existing = [item for item in ledger if item.box_id == stable_id]
    if existing:
        roles = [item.role for item in existing]
        expected = (
            [ReplicaRole.PRIMARY, ReplicaRole.STANDBY]
            if request.failover_enabled
            else [ReplicaRole.PRIMARY]
        )
        if sorted(roles) != sorted(expected):
            raise ValueError(
                "Existing Box has an incomplete or conflicting reservation plan"
            )
        for item in existing:
            if (
                item.worker_id not in request.eligible_worker_ids
                or any(
                    getattr(item, field) != getattr(request, field)
                    for field in ("cpu_limit_cores", "ram_limit_gb", "storage_limit_gb")
                )
                or item.container_slots != 1
            ):
                raise ValueError(
                    "Box ID was reused with a different allocation request"
                )
            if required_architecture is not None or application_type is not None:
                worker = worker_map.get(item.worker_id)
                if worker is None or compatibility_errors(
                    worker, required_architecture, application_type
                ):
                    raise ValueError(
                        "Existing Box cannot satisfy the requested architecture/runtime"
                    )
        existing.sort(key=lambda item: item.role.value)
        return _decision(request, stable_id, existing)

    context = {
        "active_reservation_ids": active_reservation_ids,
        "required_architecture": required_architecture,
        "application_type": application_type,
    }
    validation = validate_box_creation(request, workers, ledger, **context)
    if not validation.valid:
        raise ValueError(
            f"Box creation validation failed: {'; '.join(validation.errors)}"
        )
    candidates = [worker_map[key] for key in validation.eligible_worker_ids]
    ranked = rank_workers(
        candidates,
        ledger,
        request.cpu_limit_cores,
        request.ram_limit_gb,
        request.storage_limit_gb,
        **context,
    )
    required = 2 if request.failover_enabled else 1
    if len(ranked) < required:
        raise ValueError(
            "No distinct primary/standby placement has sufficient capacity"
        )
    placed = []
    for (worker, _), role in zip(
        ranked[:required], (ReplicaRole.PRIMARY, ReplicaRole.STANDBY), strict=False
    ):
        placed.append(
            ResourceReservation(
                reservation_id=uuid5(stable_id, f"{role.value}:{worker.worker_id}"),
                box_id=stable_id,
                worker_id=worker.worker_id,
                role=role,
                cpu_limit_cores=request.cpu_limit_cores,
                ram_limit_gb=request.ram_limit_gb,
                storage_limit_gb=request.storage_limit_gb,
                container_slots=1,
            )
        )
    return _decision(request, stable_id, placed)


def release_box_reservation(
    box_id: UUID, reservations: list[ResourceReservation]
) -> ReservationReleaseResult:
    ledger = reservation_ledger(reservations)
    return ReservationReleaseResult(
        box_id=box_id,
        reservations=[
            item.model_copy(deep=True) for item in ledger if item.box_id != box_id
        ],
        released_reservation_ids=[
            item.reservation_id for item in ledger if item.box_id == box_id
        ],
    )
