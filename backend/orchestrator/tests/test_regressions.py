"""Review regressions for reservation safety, replay and failover state handling."""

import time
from concurrent.futures import ThreadPoolExecutor
from itertools import permutations
from uuid import uuid4

import pytest
from shared.contracts import (
    Box,
    BoxCreationRequest,
    FailoverDecision,
    ResourceRequirements,
    ResourceReservation,
)
from shared.enums import FailoverState

from orchestrator.service import (
    FailoverEngine,
    calculate_worker_capacity,
    create_box_placement,
    release_box_reservation,
    select_deployment_worker,
    select_failover_worker,
    validate_box_creation,
)
from orchestrator.tests.test_orchestrator import make_worker


def reservation(
    worker_id="W-001", *, box_id=None, role="primary", cpu=1, ram=2, storage=10
):
    return ResourceReservation(
        reservation_id=uuid4(),
        box_id=box_id or uuid4(),
        worker_id=worker_id,
        role=role,
        cpu_limit_cores=cpu,
        ram_limit_gb=ram,
        storage_limit_gb=storage,
        container_slots=1,
    )


def box():
    return Box(
        box_id=uuid4(),
        name="app",
        cpu_limit_cores=1,
        ram_limit_gb=2,
        storage_limit_gb=10,
        eligible_worker_ids=["W-001", "W-002", "W-003"],
        primary_worker_id="W-001",
        standby_worker_id="W-002",
        failover_enabled=True,
        status="deployed",
    )


def reservations_for(value):
    return [
        reservation("W-001", box_id=value.box_id),
        reservation("W-002", box_id=value.box_id, role="standby"),
    ]


def test_capacity_never_rounds_up_physical_free_resources():
    worker = make_worker(available_cpu_cores=0.00006)
    assert (
        calculate_worker_capacity(worker, []).available_cpu_cores
        <= worker.available_cpu_cores
    )


def test_ambiguous_active_reservations_require_reconciliation():
    worker = make_worker(active_container_count=1)
    with pytest.raises(ValueError, match="active_reservation_ids"):
        calculate_worker_capacity(worker, [reservation()])


def test_active_plus_idle_slots_cannot_be_overbooked():
    worker = make_worker(active_container_count=1, max_containers=2)
    idle = reservation()
    capacity = calculate_worker_capacity(worker, [idle], active_reservation_ids=set())
    assert capacity.available_container_slots == 0


def test_active_reservation_is_not_subtracted_from_free_resources_twice():
    worker = make_worker(active_container_count=1, available_ram_gb=6)
    active = reservation(ram=2)
    capacity = calculate_worker_capacity(
        worker, [active], active_reservation_ids={active.reservation_id}
    )
    assert capacity.available_ram_gb == 6
    assert capacity.available_container_slots == 3


def test_failover_rejects_failure_of_an_unrelated_worker():
    value = box()
    workers = [make_worker("W-001"), make_worker("W-002")]
    assert select_failover_worker(value, workers, "W-unrelated").worker_id is None


def test_failover_never_selects_an_unreserved_fallback():
    value = box()
    workers = [
        make_worker("W-001", status="offline"),
        make_worker("W-002", status="offline"),
        make_worker("W-003"),
    ]
    assert select_failover_worker(value, workers, "W-001").worker_id is None


def test_deployment_respects_other_boxes_idle_reservations():
    value = box()
    worker = make_worker("W-001", available_ram_gb=4)
    ledger = [reservation("W-001", box_id=value.box_id), reservation("W-001", ram=3)]
    result = select_deployment_worker(value, [worker], reservations=ledger)
    assert result.worker_id is None


def test_architecture_and_runtime_are_checked_before_placement():
    worker = make_worker("W-001")
    request = BoxCreationRequest(
        name="arm-app",
        cpu_limit_cores=1,
        ram_limit_gb=1,
        storage_limit_gb=1,
        eligible_worker_ids=["W-001"],
    )
    with pytest.raises(ValueError, match="architecture"):
        create_box_placement(request, [worker], [], required_architecture="arm64")


def test_failover_state_machine_rejects_skipped_health_verification():
    value = box()
    workers = [make_worker("W-001", status="offline"), make_worker("W-002")]
    engine = FailoverEngine()
    decision = engine.evaluate_failover(uuid4(), value, workers, "W-001")
    with pytest.raises(ValueError, match="transition"):
        engine.advance_failover_state(decision.decision_id, FailoverState.RECOVERED)


def test_callers_cannot_mutate_the_cached_failover_decision():
    value = box()
    workers = [make_worker("W-001", status="offline"), make_worker("W-002")]
    engine = FailoverEngine()
    deployment_id = uuid4()
    decision = engine.evaluate_failover(deployment_id, value, workers, "W-001")
    decision.replacement_worker_id = "W-unrelated"
    assert (
        engine.evaluate_failover(
            deployment_id, value, workers, "W-001"
        ).replacement_worker_id
        == "W-002"
    )


def test_failover_cache_does_not_silently_cross_box_boundaries():
    value = box()
    workers = [make_worker("W-001", status="offline"), make_worker("W-002")]
    engine = FailoverEngine()
    deployment_id = uuid4()
    engine.evaluate_failover(deployment_id, value, workers, "W-001")
    other = value.model_copy(update={"box_id": uuid4()})
    with pytest.raises(ValueError, match="Box"):
        engine.evaluate_failover(deployment_id, other, workers, "W-001")


def test_failover_decision_identity_is_stable_across_process_restarts():
    value = box()
    workers = [make_worker("W-001", status="offline"), make_worker("W-002")]
    deployment_id = uuid4()
    first = FailoverEngine().evaluate_failover(deployment_id, value, workers, "W-001")
    second = FailoverEngine().evaluate_failover(deployment_id, value, workers, "W-001")
    assert first.decision_id == second.decision_id


def test_box_creation_replay_uses_a_stable_box_identity():
    request = BoxCreationRequest(
        name="app",
        cpu_limit_cores=1,
        ram_limit_gb=1,
        storage_limit_gb=1,
        eligible_worker_ids=["W-001"],
    )
    worker = make_worker("W-001")
    box_id = uuid4()
    first = create_box_placement(request, [worker], [], box_id=box_id)
    second = create_box_placement(request, [worker], first.reservations, box_id=box_id)
    assert second == first


def test_identical_ledger_rows_are_deduplicated_and_conflicts_are_rejected():
    worker = make_worker()
    held = reservation()
    one = calculate_worker_capacity(worker, [held])
    assert calculate_worker_capacity(worker, [held, held.model_copy()]) == one
    conflicting = held.model_copy(update={"ram_limit_gb": 5})
    with pytest.raises(ValueError, match="Conflicting"):
        calculate_worker_capacity(worker, [held, conflicting])
    second_id = held.model_copy(update={"reservation_id": uuid4()})
    with pytest.raises(ValueError, match="Duplicate"):
        calculate_worker_capacity(worker, [held, second_id])


def test_invalid_active_metadata_fails_instead_of_manufacturing_free_capacity():
    held = reservation()
    with pytest.raises(ValueError, match="unknown"):
        calculate_worker_capacity(
            make_worker(), [held], active_reservation_ids={uuid4()}
        )
    with pytest.raises(ValueError, match="active container count"):
        calculate_worker_capacity(
            make_worker(), [held], active_reservation_ids={held.reservation_id}
        )


def test_decimal_resource_boundaries_fit_without_upward_rounding():
    worker = make_worker(available_cpu_cores=0.3)
    held = reservation(cpu=0.1)
    capacity = calculate_worker_capacity(worker, [held])
    assert capacity.available_cpu_cores == 0.2


def test_own_reservation_is_consumed_without_being_subtracted_twice():
    value = box()
    worker = make_worker("W-001", available_ram_gb=2)
    result = select_deployment_worker(
        value, [worker], reservations=[reservation(box_id=value.box_id)]
    )
    assert result.worker_id == "W-001"


def test_active_box_cannot_receive_another_container_without_reconciliation():
    value = box()
    held = reservation(box_id=value.box_id)
    worker = make_worker(active_container_count=1)
    assert (
        select_deployment_worker(
            value,
            [worker],
            reservations=[held],
            active_reservation_ids={held.reservation_id},
        ).worker_id
        is None
    )
    assert (
        select_deployment_worker(value, [worker], reservations=[held]).worker_id is None
    )


def test_explicit_empty_ledger_does_not_trust_stale_box_assignment():
    value = box()
    workers = [make_worker("W-001"), make_worker("W-002")]
    assert select_deployment_worker(value, workers, reservations=[]).worker_id is None
    assert (
        select_failover_worker(value, workers, "W-001", reservations=[]).worker_id
        is None
    )


def test_fallback_must_have_its_own_box_reservation():
    value = box()
    workers = [
        make_worker("W-001", status="offline"),
        make_worker("W-002", status="offline"),
        make_worker("W-003"),
    ]
    unrelated = reservation("W-003")
    assert (
        select_failover_worker(
            value, workers, "W-001", reservations=[unrelated]
        ).worker_id
        is None
    )
    covered = reservation("W-003", box_id=value.box_id, role="standby")
    assert (
        select_failover_worker(
            value, workers, "W-001", reservations=[covered]
        ).worker_id
        == "W-003"
    )


def test_standby_failure_does_not_trigger_duplicate_primary_deployment():
    value = box()
    workers = [
        make_worker("W-001"),
        make_worker("W-002", status="offline"),
        make_worker("W-003"),
    ]
    result = select_failover_worker(
        value, workers, "W-002", reservations=reservations_for(value)
    )
    assert result.worker_id is None
    with pytest.raises(ValueError, match="primary"):
        FailoverEngine().evaluate_failover(uuid4(), value, workers, "W-002")


def test_architecture_aliases_and_unsupported_runtimes():
    request = BoxCreationRequest(
        name="app",
        cpu_limit_cores=1,
        ram_limit_gb=1,
        storage_limit_gb=1,
        eligible_worker_ids=["W-001"],
    )
    worker = make_worker()
    assert validate_box_creation(
        request, [worker], [], required_architecture="linux/amd64"
    ).valid
    python_only = worker.model_copy(update={"supported_runtimes": ["python"]})
    assert not validate_box_creation(
        request, [python_only], [], application_type="node"
    ).valid
    arm = worker.model_copy(update={"architecture": "aarch64"})
    assert validate_box_creation(
        request, [arm], [], required_architecture="arm64"
    ).valid


def test_incompatible_standby_is_not_used_for_failover():
    value = box()
    workers = [make_worker("W-001", status="offline"), make_worker("W-002")]
    assert (
        select_failover_worker(
            value, workers, "W-001", required_architecture="arm64"
        ).worker_id
        is None
    )


def test_placement_is_deterministic_under_worker_and_ledger_permutations():
    workers = [make_worker("W-003"), make_worker("W-001"), make_worker("W-002")]
    request = BoxCreationRequest(
        name="app",
        cpu_limit_cores=1,
        ram_limit_gb=1,
        storage_limit_gb=1,
        eligible_worker_ids=["W-003", "W-002", "W-001"],
        failover_enabled=True,
    )
    box_id = uuid4()
    decisions = [
        create_box_placement(request, list(order), [], box_id=box_id)
        for order in permutations(workers)
    ]
    assert all(value == decisions[0] for value in decisions)


def test_duplicate_conflicting_worker_snapshots_fail_validation():
    request = BoxCreationRequest(
        name="app",
        cpu_limit_cores=1,
        ram_limit_gb=1,
        storage_limit_gb=1,
        eligible_worker_ids=["W-001"],
    )
    worker = make_worker()
    conflict = worker.model_copy(update={"available_ram_gb": 1})
    result = validate_box_creation(request, [worker, conflict], [])
    assert not result.valid
    assert "Conflicting snapshots" in result.errors[0]


def test_placement_replay_cannot_change_allocations():
    request = BoxCreationRequest(
        name="app",
        cpu_limit_cores=1,
        ram_limit_gb=1,
        storage_limit_gb=1,
        eligible_worker_ids=["W-001"],
    )
    worker = make_worker()
    identity = uuid4()
    first = create_box_placement(request, [worker], [], box_id=identity)
    changed = request.model_copy(update={"ram_limit_gb": 2})
    with pytest.raises(ValueError, match="different allocation"):
        create_box_placement(changed, [worker], first.reservations, box_id=identity)


def test_reservation_release_does_not_mutate_the_original_ledger():
    held = reservation()
    other = reservation()
    ledger = [held, other]
    result = release_box_reservation(held.box_id, ledger)
    result.reservations[0].ram_limit_gb = 9
    assert other.ram_limit_gb == 2
    assert len(ledger) == 2


def test_failover_restores_persisted_history_without_changing_target():
    value = box()
    workers = [make_worker("W-001", status="offline"), make_worker("W-002")]
    engine = FailoverEngine()
    deployment_id = uuid4()
    first = engine.evaluate_failover(deployment_id, value, workers, "W-001")
    engine.advance_failover_state(first.decision_id, FailoverState.REDEPLOYING)
    engine.advance_failover_state(first.decision_id, FailoverState.HEALTH_CHECK)
    final = engine.advance_failover_state(first.decision_id, FailoverState.RECOVERED)
    serialized = [
        FailoverDecision.model_validate_json(item.model_dump_json())
        for item in engine.decisions()
    ]
    restored = FailoverEngine(serialized)
    assert restored.evaluate_failover(deployment_id, value, workers, "W-001") == final
    with pytest.raises(ValueError, match="transition"):
        restored.advance_failover_state(final.decision_id, FailoverState.REDEPLOYING)
    with pytest.raises(RuntimeError, match="history"):
        restored.clear()


def test_concurrent_failover_notifications_select_once(monkeypatch):
    import orchestrator.failover.engine as module

    value = box()
    workers = [make_worker("W-001", status="offline"), make_worker("W-002")]
    original = module.select_failover_worker
    calls = []

    def select(*args, **kwargs):
        calls.append(True)
        time.sleep(0.01)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "select_failover_worker", select)
    engine = FailoverEngine()
    deployment_id = uuid4()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda _: engine.evaluate_failover(
                    deployment_id, value, workers, "W-001"
                ),
                range(24),
            )
        )
    assert len(calls) == 1
    assert all(result == results[0] for result in results)


def test_deployment_id_must_match_the_current_box_deployment():
    value = box().model_copy(update={"deployment_id": uuid4()})
    with pytest.raises(ValueError, match="Deployment ID"):
        FailoverEngine().evaluate_failover(uuid4(), value, [], "W-001")


@pytest.mark.parametrize(
    "resource", ["cpu_limit_cores", "ram_limit_gb", "storage_limit_gb"]
)
def test_application_requirements_must_fit_inside_the_box(resource):
    value = box()
    limits = {"cpu_limit_cores": 1, "ram_limit_gb": 2, "storage_limit_gb": 10}
    limits[resource] *= 2
    requirements = ResourceRequirements(**limits)
    workers = [make_worker("W-001"), make_worker("W-002")]
    result = select_deployment_worker(
        value, workers, application_requirements=requirements
    )
    assert result.worker_id is None
    assert "exceeds the Box" in result.reason
    assert (
        select_failover_worker(
            value, workers, "W-001", application_requirements=requirements
        ).worker_id
        is None
    )


def test_cached_failover_cannot_bypass_application_limit_validation():
    value = box()
    workers = [make_worker("W-001", status="offline"), make_worker("W-002")]
    engine = FailoverEngine()
    deployment_id = uuid4()
    first = engine.evaluate_failover(deployment_id, value, workers, "W-001")
    oversized = ResourceRequirements(
        cpu_limit_cores=2, ram_limit_gb=2, storage_limit_gb=10
    )
    with pytest.raises(ValueError, match="exceeds the Box"):
        engine.evaluate_failover(
            deployment_id, value, workers, "W-001", application_requirements=oversized
        )
    assert engine.get_decision(deployment_id, "W-001") == first
