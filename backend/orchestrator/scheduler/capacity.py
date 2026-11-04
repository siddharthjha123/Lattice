"""Reconcile physical free telemetry with reservations exactly once."""

from decimal import Decimal
from math import isfinite
from uuid import UUID

from shared.contracts import (
    PositiveFloat,
    PositiveInt,
    ResourceReservation,
    WorkerCapacity,
    WorkerSnapshot,
)

from orchestrator._inputs import reservation_ledger


def calculate_worker_capacity(
    worker: WorkerSnapshot,
    reservations: list[ResourceReservation],
    *,
    active_reservation_ids: set[UUID] | None = None,
) -> WorkerCapacity:
    """Subtract idle reservations, leaving active allocations in physical telemetry.

    When active workloads and reservations coexist, the Control Plane must state
    which reservations are already reflected in this snapshot. An explicit empty
    set means all recorded reservations are idle. Guessing overlap is unsafe.
    """
    ledger = reservation_ledger(reservations)
    known_ids = {item.reservation_id for item in ledger}
    active_ids = set(active_reservation_ids or ())
    if active_ids - known_ids:
        raise ValueError("active_reservation_ids includes an unknown reservation")
    owned = [item for item in ledger if item.worker_id == worker.worker_id]
    if worker.active_container_count and owned and active_reservation_ids is None:
        raise ValueError(
            "active_reservation_ids is required to reconcile active workloads and reservations"
        )
    active = [item for item in owned if item.reservation_id in active_ids]
    if sum(item.container_slots for item in active) > worker.active_container_count:
        raise ValueError(
            "Active reservation slots exceed the snapshot's active container count"
        )
    idle = [item for item in owned if item.reservation_id not in active_ids]

    def available(value, field):
        remaining = Decimal(str(value)) - sum(
            (Decimal(str(getattr(item, field))) for item in idle), Decimal(0)
        )
        return float(max(Decimal(0), remaining))

    return WorkerCapacity(
        worker_id=worker.worker_id,
        available_cpu_cores=available(worker.available_cpu_cores, "cpu_limit_cores"),
        available_ram_gb=available(worker.available_ram_gb, "ram_limit_gb"),
        available_storage_gb=available(worker.available_storage_gb, "storage_limit_gb"),
        available_container_slots=max(
            0,
            worker.max_containers
            - worker.active_container_count
            - sum(item.container_slots for item in idle),
        ),
    )


def has_sufficient_capacity(
    capacity: WorkerCapacity,
    required_cpu: PositiveFloat,
    required_ram: PositiveFloat,
    required_storage: PositiveFloat,
    required_slots: PositiveInt = 1,
) -> tuple[bool, list[str]]:
    values = (required_cpu, required_ram, required_storage)
    if any(not isfinite(value) or value <= 0 for value in values):
        raise ValueError("Resource requirements must be positive and finite")
    if (
        isinstance(required_slots, bool)
        or not isinstance(required_slots, int)
        or required_slots < 1
    ):
        raise ValueError("Required container slots must be a positive integer")
    deficits = []
    for actual, requested, name, unit in (
        (capacity.available_cpu_cores, required_cpu, "CPU", "cores"),
        (capacity.available_ram_gb, required_ram, "RAM", "GB"),
        (capacity.available_storage_gb, required_storage, "storage", "GB"),
    ):
        if actual < requested:
            deficits.append(
                f"insufficient {name} (available: {actual:g} {unit}, required: {requested:g} {unit})"
            )
    if capacity.available_container_slots < required_slots:
        deficits.append(
            f"container capacity exhausted (available slots: {capacity.available_container_slots}, required: {required_slots})"
        )
    return not deficits, deficits
