"""Validate scheduler collections without inventing another shared model."""

from shared.contracts import ResourceReservation, WorkerSnapshot
from shared.enums import ApplicationType


def reservation_ledger(
    reservations: list[ResourceReservation],
) -> list[ResourceReservation]:
    by_id = {}
    allocations = {}
    for reservation in reservations:
        previous = by_id.get(reservation.reservation_id)
        if previous is not None:
            if previous != reservation:
                raise ValueError("Conflicting records use the same reservation ID")
            continue
        key = (reservation.box_id, reservation.worker_id)
        if key in allocations:
            raise ValueError("Duplicate Box allocation on one worker")
        by_id[reservation.reservation_id] = reservation
        allocations[key] = reservation
    return list(by_id.values())


def worker_index(workers: list[WorkerSnapshot]) -> dict[str, WorkerSnapshot]:
    result = {}
    for worker in workers:
        if worker.worker_id in result and result[worker.worker_id] != worker:
            raise ValueError(f"Conflicting snapshots for worker '{worker.worker_id}'")
        result[worker.worker_id] = worker
    return result


def normalized_architecture(value: str) -> str:
    value = value.strip().lower()
    aliases = {
        "x86_64": "amd64",
        "x64": "amd64",
        "aarch64": "arm64",
        "arm64/v8": "arm64",
    }
    if value.startswith("linux/"):
        value = value.removeprefix("linux/")
    return aliases.get(value, value)


def compatibility_errors(
    worker, required_architecture=None, application_type=None
) -> list[str]:
    errors = []
    if required_architecture is not None:
        if not normalized_architecture(required_architecture):
            raise ValueError("Required architecture must be nonblank")
        if normalized_architecture(worker.architecture) != normalized_architecture(
            required_architecture
        ):
            errors.append(
                f"incompatible architecture '{worker.architecture}' (requires '{required_architecture}')"
            )
    if (
        application_type is not None
        and ApplicationType(application_type) not in worker.supported_runtimes
    ):
        errors.append(
            f"unsupported runtime '{ApplicationType(application_type).value}'"
        )
    return errors


def application_errors(box, requirements):
    if requirements is None:
        return []
    return [
        f"Application {label} requirement exceeds the Box limit"
        for field, label in (
            ("cpu_limit_cores", "CPU"),
            ("ram_limit_gb", "RAM"),
            ("storage_limit_gb", "storage"),
        )
        if getattr(requirements, field) > getattr(box, field)
    ]
