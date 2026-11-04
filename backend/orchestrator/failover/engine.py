"""Reserved failover targets and thread-safe, restorable decision history."""

import threading
from collections.abc import Sequence
from uuid import NAMESPACE_URL, UUID, uuid5

from shared.contracts import (
    Box,
    FailoverDecision,
    ResourceRequirements,
    ResourceReservation,
    WorkerId,
    WorkerSelectionResult,
    WorkerSnapshot,
)
from shared.enums import ApplicationType, FailoverState

from orchestrator._inputs import application_errors
from orchestrator.scheduler.engine import select_deployment_worker

TRANSITIONS = {
    FailoverState.DETECTING: {FailoverState.WORKER_FAILED, FailoverState.FAILED},
    FailoverState.WORKER_FAILED: {
        FailoverState.SELECTING_STANDBY,
        FailoverState.FAILED,
    },
    FailoverState.SELECTING_STANDBY: {FailoverState.REDEPLOYING, FailoverState.FAILED},
    FailoverState.REDEPLOYING: {FailoverState.HEALTH_CHECK, FailoverState.FAILED},
    FailoverState.HEALTH_CHECK: {FailoverState.RECOVERED, FailoverState.FAILED},
    FailoverState.RECOVERED: set(),
    FailoverState.FAILED: set(),
}


def select_failover_worker(
    box: Box,
    workers: list[WorkerSnapshot],
    failed_worker_id: WorkerId,
    *,
    reservations: list[ResourceReservation] | None = None,
    active_reservation_ids: set[UUID] | None = None,
    required_architecture: str | None = None,
    application_type: ApplicationType | None = None,
    application_requirements: ResourceRequirements | None = None,
) -> WorkerSelectionResult:
    if not box.failover_enabled:
        return WorkerSelectionResult(
            worker_id=None, reason=f"Box '{box.box_id}' does not have failover enabled."
        )
    if box.primary_worker_id != failed_worker_id:
        return WorkerSelectionResult(
            worker_id=None,
            reason="Failure does not affect this Box's primary; repair standby reservations without redeploying a healthy primary.",
        )
    selection = select_deployment_worker(
        box,
        workers,
        excluded_worker_ids=[failed_worker_id],
        reservations=reservations,
        active_reservation_ids=active_reservation_ids,
        required_architecture=required_architecture,
        application_type=application_type,
        application_requirements=application_requirements,
    )
    if selection.worker_id is None:
        return WorkerSelectionResult(
            worker_id=None,
            reason=f"No eligible replacement worker available for Box '{box.box_id}' after failure of worker '{failed_worker_id}': {selection.reason}",
        )
    return WorkerSelectionResult(
        worker_id=selection.worker_id, reason=f"Failover: {selection.reason}"
    )


class FailoverEngine:
    """One decision per (deployment, failed worker), using shared Pydantic models.

    Stable IDs and restored history allow Control Plane persistence/idempotent
    dispatch. This in-process lock is not a distributed transaction or fencing.
    """

    def __init__(self, initial_decisions: Sequence[FailoverDecision] = ()) -> None:
        self._lock = threading.RLock()
        self._decisions: dict[tuple[UUID, WorkerId], FailoverDecision] = {}
        seen_ids = set()
        for decision in initial_decisions:
            key = (decision.deployment_id, decision.failed_worker_id)
            if key in self._decisions or decision.decision_id in seen_ids:
                raise ValueError("Conflicting or duplicate restored failover history")
            if decision.replacement_worker_id == decision.failed_worker_id:
                raise ValueError("A failed worker cannot be its own replacement")
            self._decisions[key] = decision.model_copy(deep=True)
            seen_ids.add(decision.decision_id)

    def evaluate_failover(
        self,
        deployment_id: UUID,
        box: Box,
        workers: list[WorkerSnapshot],
        failed_worker_id: WorkerId,
        *,
        reservations: list[ResourceReservation] | None = None,
        active_reservation_ids: set[UUID] | None = None,
        required_architecture: str | None = None,
        application_type: ApplicationType | None = None,
        application_requirements: ResourceRequirements | None = None,
    ) -> FailoverDecision:
        with self._lock:
            errors = application_errors(box, application_requirements)
            if errors:
                raise ValueError("; ".join(errors))
            if box.deployment_id is not None and box.deployment_id != deployment_id:
                raise ValueError(
                    "Deployment ID does not match the Box's current deployment"
                )
            key = (deployment_id, failed_worker_id)
            existing = self._decisions.get(key)
            if existing is not None:
                if existing.box_id != box.box_id:
                    raise ValueError("Failover replay refers to a different Box")
                if existing.state not in {
                    FailoverState.DETECTING,
                    FailoverState.WORKER_FAILED,
                }:
                    return existing.model_copy(deep=True)
            if box.primary_worker_id != failed_worker_id:
                raise ValueError("Failed worker is not the Box's assigned primary")
            selection = select_failover_worker(
                box,
                workers,
                failed_worker_id,
                reservations=reservations,
                active_reservation_ids=active_reservation_ids,
                required_architecture=required_architecture,
                application_type=application_type,
                application_requirements=application_requirements,
            )
            decision_id = (
                existing.decision_id
                if existing
                else uuid5(
                    NAMESPACE_URL,
                    f"lattice/failover/{deployment_id}/{box.box_id}/{failed_worker_id}",
                )
            )
            decision = FailoverDecision(
                decision_id=decision_id,
                deployment_id=deployment_id,
                box_id=box.box_id,
                failed_worker_id=failed_worker_id,
                replacement_worker_id=selection.worker_id,
                state=FailoverState.SELECTING_STANDBY
                if selection.worker_id
                else FailoverState.FAILED,
                reason=selection.reason,
            )
            self._decisions[key] = decision
            return decision.model_copy(deep=True)

    def advance_failover_state(
        self, decision_id: UUID, next_state: FailoverState, reason: str | None = None
    ) -> FailoverDecision:
        next_state = FailoverState(next_state)
        with self._lock:
            for key, decision in self._decisions.items():
                if decision.decision_id != decision_id:
                    continue
                if next_state == decision.state:
                    return decision.model_copy(deep=True)
                if next_state not in TRANSITIONS[decision.state]:
                    raise ValueError(
                        f"Invalid failover transition: {decision.state.value} -> {next_state.value}"
                    )
                if (
                    next_state
                    in {
                        FailoverState.SELECTING_STANDBY,
                        FailoverState.REDEPLOYING,
                        FailoverState.HEALTH_CHECK,
                        FailoverState.RECOVERED,
                    }
                    and not decision.replacement_worker_id
                ):
                    raise ValueError(
                        "Failover transition requires a selected replacement worker"
                    )
                updated = FailoverDecision(
                    **(
                        decision.model_dump()
                        | {
                            "state": next_state,
                            "reason": reason if reason is not None else decision.reason,
                        }
                    )
                )
                self._decisions[key] = updated
                return updated.model_copy(deep=True)
        raise KeyError(f"FailoverDecision with id '{decision_id}' not found.")

    def get_decision(
        self, deployment_id: UUID, failed_worker_id: WorkerId
    ) -> FailoverDecision | None:
        with self._lock:
            decision = self._decisions.get((deployment_id, failed_worker_id))
            return decision.model_copy(deep=True) if decision else None

    def decisions(self) -> list[FailoverDecision]:
        """Snapshot for Control Plane persistence; this method does not save a DB."""
        with self._lock:
            return [
                self._decisions[key].model_copy(deep=True)
                for key in sorted(
                    self._decisions, key=lambda value: (str(value[0]), value[1])
                )
            ]

    def clear(self) -> None:
        with self._lock:
            if any(
                decision.replacement_worker_id is not None
                for decision in self._decisions.values()
            ):
                raise RuntimeError(
                    "Cannot discard actionable failover history; persist or restore it instead"
                )
            self._decisions.clear()
