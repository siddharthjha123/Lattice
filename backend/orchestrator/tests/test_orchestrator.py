"""Unit tests for Lattice Orchestrator (Orchestrator).

Verifies all required scheduling, validation, capacity, and failover scenarios.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from shared.contracts import (
    Box,
    BoxCreationRequest,
    PlacementDecision,
    ReservationReleaseResult,
    ResourceReservation,
    WorkerSnapshot,
)
from shared.enums import (
    ApplicationType,
    BoxStatus,
    FailoverState,
    ReplicaRole,
    WorkerStatus,
)

from orchestrator.service import (
    FailoverEngine,
    calculate_worker_capacity,
    create_box_placement,
    release_box_reservation,
    select_deployment_worker,
    select_failover_worker,
    validate_box_creation,
)


def make_worker(
    worker_id: str = "W-001",
    status: WorkerStatus = WorkerStatus.ONLINE,
    cpu_cores: int = 4,
    available_cpu_cores: float = 4.0,
    total_ram_gb: float = 16.0,
    available_ram_gb: float = 16.0,
    total_storage_gb: float = 256.0,
    available_storage_gb: float = 256.0,
    active_container_count: int = 0,
    max_containers: int = 4,
) -> WorkerSnapshot:
    """Deterministic worker snapshot fixture."""
    return WorkerSnapshot(
        worker_id=worker_id,
        hostname=f"host-{worker_id}",
        status=status,
        cpu_cores=cpu_cores,
        available_cpu_cores=available_cpu_cores,
        total_ram_gb=total_ram_gb,
        available_ram_gb=available_ram_gb,
        total_storage_gb=total_storage_gb,
        available_storage_gb=available_storage_gb,
        active_container_count=active_container_count,
        max_containers=max_containers,
        architecture="x86_64",
        supported_runtimes=[ApplicationType.PYTHON, ApplicationType.NODE],
        last_heartbeat=datetime.now(UTC),
    )


# 1. Two-worker Box creation
def test_two_worker_box_creation():
    w1 = make_worker("W-001", available_ram_gb=8.0, available_cpu_cores=4.0)
    w2 = make_worker("W-002", available_ram_gb=8.0, available_cpu_cores=4.0)

    req = BoxCreationRequest(
        name="web-service",
        ram_limit_gb=2.0,
        cpu_limit_cores=1.0,
        storage_limit_gb=10.0,
        eligible_worker_ids=["W-001", "W-002"],
        failover_enabled=True,
    )

    validation = validate_box_creation(req, [w1, w2], [])
    assert validation.valid is True
    assert validation.errors == []
    assert set(validation.eligible_worker_ids) == {"W-001", "W-002"}

    decision = create_box_placement(req, [w1, w2], [])
    assert isinstance(decision, PlacementDecision)
    assert decision.primary_worker_id == "W-001"
    assert decision.standby_worker_id == "W-002"
    assert len(decision.reservations) == 2

    # Check reservations match roles
    roles = {r.role: r.worker_id for r in decision.reservations}
    assert roles[ReplicaRole.PRIMARY] == "W-001"
    assert roles[ReplicaRole.STANDBY] == "W-002"
    assert all(r.box_id == decision.box_id for r in decision.reservations)
    assert all(r.ram_limit_gb == 2.0 for r in decision.reservations)


# 2. Insufficient RAM
def test_insufficient_ram():
    w1 = make_worker("W-001", available_ram_gb=2.0)
    req = BoxCreationRequest(
        name="heavy-service",
        ram_limit_gb=4.0,  # exceeds available 2.0 GB
        cpu_limit_cores=1.0,
        storage_limit_gb=10.0,
        eligible_worker_ids=["W-001"],
        failover_enabled=False,
    )

    validation = validate_box_creation(req, [w1], [])
    assert validation.valid is False
    assert len(validation.errors) > 0
    assert any("insufficient RAM" in err for err in validation.errors)
    assert validation.eligible_worker_ids == []

    with pytest.raises(ValueError, match="Box creation validation failed"):
        create_box_placement(req, [w1], [])


# 3. Insufficient storage
def test_insufficient_storage():
    w1 = make_worker("W-001", available_storage_gb=15.0)
    req = BoxCreationRequest(
        name="db-service",
        ram_limit_gb=1.0,
        cpu_limit_cores=1.0,
        storage_limit_gb=50.0,  # exceeds 15.0 GB
        eligible_worker_ids=["W-001"],
        failover_enabled=False,
    )

    validation = validate_box_creation(req, [w1], [])
    assert validation.valid is False
    assert any("insufficient storage" in err for err in validation.errors)


# 4. Worker offline during creation
def test_worker_offline_during_creation():
    w1 = make_worker("W-001", status=WorkerStatus.OFFLINE)
    req = BoxCreationRequest(
        name="offline-test",
        ram_limit_gb=1.0,
        cpu_limit_cores=1.0,
        storage_limit_gb=5.0,
        eligible_worker_ids=["W-001"],
        failover_enabled=False,
    )

    validation = validate_box_creation(req, [w1], [])
    assert validation.valid is False
    assert any("offline" in err.lower() for err in validation.errors)

    with pytest.raises(ValueError, match="validation failed"):
        create_box_placement(req, [w1], [])


# 5. Container capacity exhausted
def test_container_capacity_exhausted():
    # Worker is at its container limit
    w1 = make_worker("W-001", max_containers=2, active_container_count=2)
    req = BoxCreationRequest(
        name="container-cap-test",
        ram_limit_gb=1.0,
        cpu_limit_cores=1.0,
        storage_limit_gb=5.0,
        eligible_worker_ids=["W-001"],
        failover_enabled=False,
    )

    validation = validate_box_creation(req, [w1], [])
    assert validation.valid is False
    assert any("container capacity exhausted" in err for err in validation.errors)


# 6. No standby worker available
def test_no_standby_worker_available():
    # W-001 has capacity; W-002 has insufficient RAM
    w1 = make_worker("W-001", available_ram_gb=8.0)
    w2 = make_worker("W-002", available_ram_gb=1.0)

    req = BoxCreationRequest(
        name="failover-service",
        ram_limit_gb=4.0,  # W-001 fits, W-002 does not
        cpu_limit_cores=1.0,
        storage_limit_gb=10.0,
        eligible_worker_ids=["W-001", "W-002"],
        failover_enabled=True,
    )

    validation = validate_box_creation(req, [w1, w2], [])
    assert validation.valid is False
    assert any("Failover requires at least two" in err for err in validation.errors)
    assert validation.eligible_worker_ids == ["W-001"]

    with pytest.raises(ValueError, match="validation failed"):
        create_box_placement(req, [w1, w2], [])


# 7. Primary worker failure
def test_primary_worker_failure():
    w1 = make_worker("W-001", status=WorkerStatus.OFFLINE)
    w2 = make_worker("W-002", status=WorkerStatus.ONLINE, available_ram_gb=8.0)

    box = Box(
        box_id=uuid4(),
        name="test-box",
        ram_limit_gb=2.0,
        cpu_limit_cores=1.0,
        storage_limit_gb=10.0,
        eligible_worker_ids=["W-001", "W-002"],
        primary_worker_id="W-001",
        standby_worker_id="W-002",
        failover_enabled=True,
        status=BoxStatus.DEPLOYED,
    )

    result = select_failover_worker(box, [w1, w2], failed_worker_id="W-001")
    assert result.worker_id == "W-002"
    assert "designated standby worker" in result.reason

    engine = FailoverEngine()
    dep_id = uuid4()
    decision = engine.evaluate_failover(dep_id, box, [w1, w2], failed_worker_id="W-001")
    assert decision.replacement_worker_id == "W-002"
    assert decision.state == FailoverState.SELECTING_STANDBY


# 8. Standby worker failure
def test_standby_worker_failure():
    w1 = make_worker("W-001", status=WorkerStatus.OFFLINE)  # Primary failed
    w2 = make_worker("W-002", status=WorkerStatus.OFFLINE)  # Standby also failed
    w3 = make_worker(
        "W-003", status=WorkerStatus.ONLINE, available_ram_gb=8.0
    )  # Eligible replacement

    box = Box(
        box_id=uuid4(),
        name="test-box",
        ram_limit_gb=2.0,
        cpu_limit_cores=1.0,
        storage_limit_gb=10.0,
        eligible_worker_ids=["W-001", "W-002", "W-003"],
        primary_worker_id="W-001",
        standby_worker_id="W-002",
        failover_enabled=True,
        status=BoxStatus.DEGRADED,
    )

    # A free third worker is not sufficient evidence of protected capacity.
    unreserved = select_failover_worker(box, [w1, w2, w3], failed_worker_id="W-001")
    assert unreserved.worker_id is None
    replacement_reservation = ResourceReservation(
        reservation_id=uuid4(),
        box_id=box.box_id,
        worker_id="W-003",
        role=ReplicaRole.STANDBY,
        ram_limit_gb=2,
        cpu_limit_cores=1,
        storage_limit_gb=10,
        container_slots=1,
    )
    result = select_failover_worker(
        box,
        [w1, w2, w3],
        failed_worker_id="W-001",
        reservations=[replacement_reservation],
    )
    assert result.worker_id == "W-003"
    assert "reserved eligible worker" in result.reason


# 9. Double reservation prevention
def test_double_reservation_prevention():
    w1 = make_worker("W-001", available_ram_gb=8.0)

    # First reservation takes 6.0 GB RAM
    res1 = ResourceReservation(
        reservation_id=uuid4(),
        box_id=uuid4(),
        worker_id="W-001",
        role=ReplicaRole.PRIMARY,
        ram_limit_gb=6.0,
        cpu_limit_cores=1.0,
        storage_limit_gb=10.0,
        container_slots=1,
    )

    # Remaining capacity should now be 2.0 GB
    cap = calculate_worker_capacity(w1, [res1])
    assert cap.available_ram_gb == 2.0
    assert cap.available_container_slots == 3

    # Attempting to allocate another Box requiring 3.0 GB must fail
    req2 = BoxCreationRequest(
        name="box-2",
        ram_limit_gb=3.0,
        cpu_limit_cores=1.0,
        storage_limit_gb=10.0,
        eligible_worker_ids=["W-001"],
        failover_enabled=False,
    )

    validation = validate_box_creation(req2, [w1], [res1])
    assert validation.valid is False
    assert any("insufficient RAM" in err for err in validation.errors)


# 10. Reservation release
def test_reservation_release():
    w1 = make_worker("W-001", available_ram_gb=8.0)
    box_id = uuid4()
    other_box_id = uuid4()

    res1 = ResourceReservation(
        reservation_id=uuid4(),
        box_id=box_id,
        worker_id="W-001",
        role=ReplicaRole.PRIMARY,
        ram_limit_gb=4.0,
        cpu_limit_cores=1.0,
        storage_limit_gb=10.0,
        container_slots=1,
    )
    res2 = ResourceReservation(
        reservation_id=uuid4(),
        box_id=other_box_id,
        worker_id="W-001",
        role=ReplicaRole.PRIMARY,
        ram_limit_gb=2.0,
        cpu_limit_cores=1.0,
        storage_limit_gb=10.0,
        container_slots=1,
    )

    current_reservations = [res1, res2]
    cap_before = calculate_worker_capacity(w1, current_reservations)
    assert cap_before.available_ram_gb == 2.0  # 8 - 4 - 2

    # Release box_id
    release_res = release_box_reservation(box_id, current_reservations)
    assert isinstance(release_res, ReservationReleaseResult)
    assert release_res.box_id == box_id
    assert release_res.released_reservation_ids == [res1.reservation_id]
    assert release_res.reservations == [res2]

    # Capacity updates correctly after release
    cap_after = calculate_worker_capacity(w1, release_res.reservations)
    assert cap_after.available_ram_gb == 6.0  # 8 - 2

    # Releasing already released box is idempotent
    second_release = release_box_reservation(box_id, release_res.reservations)
    assert second_release.released_reservation_ids == []
    assert second_release.reservations == [res2]


# 11. Repeated failover notification (idempotency)
def test_repeated_failover_notification():
    w1 = make_worker("W-001", status=WorkerStatus.OFFLINE)
    w2 = make_worker("W-002", status=WorkerStatus.ONLINE, available_ram_gb=8.0)

    box = Box(
        box_id=uuid4(),
        name="test-box",
        ram_limit_gb=2.0,
        cpu_limit_cores=1.0,
        storage_limit_gb=10.0,
        eligible_worker_ids=["W-001", "W-002"],
        primary_worker_id="W-001",
        standby_worker_id="W-002",
        failover_enabled=True,
        status=BoxStatus.DEPLOYED,
    )

    engine = FailoverEngine()
    dep_id = uuid4()

    decision1 = engine.evaluate_failover(
        dep_id, box, [w1, w2], failed_worker_id="W-001"
    )
    assert decision1.replacement_worker_id == "W-002"

    # Repeated notification with identical parameters returns cached decision
    decision2 = engine.evaluate_failover(
        dep_id, box, [w1, w2], failed_worker_id="W-001"
    )
    assert decision1.decision_id == decision2.decision_id
    assert decision1.replacement_worker_id == decision2.replacement_worker_id

    # Advance state to REDEPLOYING
    advanced = engine.advance_failover_state(
        decision1.decision_id,
        FailoverState.REDEPLOYING,
        reason="Dispatched redeploy command to standby",
    )
    assert advanced.state == FailoverState.REDEPLOYING


# 12. No eligible replacement worker
def test_no_eligible_replacement_worker():
    w1 = make_worker("W-001", status=WorkerStatus.OFFLINE)
    w2 = make_worker("W-002", status=WorkerStatus.OFFLINE)  # standby also offline

    box = Box(
        box_id=uuid4(),
        name="test-box",
        ram_limit_gb=2.0,
        cpu_limit_cores=1.0,
        storage_limit_gb=10.0,
        eligible_worker_ids=["W-001", "W-002"],
        primary_worker_id="W-001",
        standby_worker_id="W-002",
        failover_enabled=True,
        status=BoxStatus.DEGRADED,
    )

    result = select_failover_worker(box, [w1, w2], failed_worker_id="W-001")
    assert result.worker_id is None
    assert "No eligible replacement worker available" in result.reason

    engine = FailoverEngine()
    dep_id = uuid4()
    decision = engine.evaluate_failover(dep_id, box, [w1, w2], failed_worker_id="W-001")
    assert decision.replacement_worker_id is None
    assert decision.state == FailoverState.FAILED


# 13. Deployment worker selection with exclusion
def test_deployment_worker_selection():
    w1 = make_worker("W-001", status=WorkerStatus.ONLINE, available_ram_gb=8.0)
    w2 = make_worker("W-002", status=WorkerStatus.ONLINE, available_ram_gb=8.0)

    box = Box(
        box_id=uuid4(),
        name="test-box",
        ram_limit_gb=2.0,
        cpu_limit_cores=1.0,
        storage_limit_gb=10.0,
        eligible_worker_ids=["W-001", "W-002"],
        primary_worker_id="W-001",
        standby_worker_id="W-002",
        failover_enabled=True,
        status=BoxStatus.AVAILABLE,
    )

    # Normal selection chooses primary
    sel1 = select_deployment_worker(box, [w1, w2])
    assert sel1.worker_id == "W-001"

    # With primary excluded, chooses standby
    sel2 = select_deployment_worker(box, [w1, w2], excluded_worker_ids=["W-001"])
    assert sel2.worker_id == "W-002"

    # With both excluded, returns None
    sel3 = select_deployment_worker(
        box, [w1, w2], excluded_worker_ids=["W-001", "W-002"]
    )
    assert sel3.worker_id is None


# 14. Deterministic tie-breaking
def test_deterministic_ranking_tie_breaking():
    wA = make_worker("W-AAA", available_ram_gb=8.0, available_cpu_cores=4.0)
    wB = make_worker("W-BBB", available_ram_gb=8.0, available_cpu_cores=4.0)

    req = BoxCreationRequest(
        name="tie-test",
        ram_limit_gb=2.0,
        cpu_limit_cores=1.0,
        storage_limit_gb=10.0,
        eligible_worker_ids=["W-BBB", "W-AAA"],  # Given in reverse order
        failover_enabled=True,
    )

    decision = create_box_placement(req, [wB, wA], [])
    # Lexicographical tie-breaker ensures W-AAA is primary and W-BBB is standby
    assert decision.primary_worker_id == "W-AAA"
    assert decision.standby_worker_id == "W-BBB"


# 15. Capacity clamping (no negative values)
def test_capacity_clamping():
    w = make_worker(
        "W-001", available_ram_gb=1.0, available_cpu_cores=0.5, available_storage_gb=5.0
    )
    res = ResourceReservation(
        reservation_id=uuid4(),
        box_id=uuid4(),
        worker_id="W-001",
        role=ReplicaRole.PRIMARY,
        ram_limit_gb=4.0,  # exceeds available
        cpu_limit_cores=2.0,  # exceeds available
        storage_limit_gb=20.0,  # exceeds available
        container_slots=10,  # exceeds max
    )

    cap = calculate_worker_capacity(w, [res])
    assert cap.available_ram_gb == 0.0
    assert cap.available_cpu_cores == 0.0
    assert cap.available_storage_gb == 0.0
    assert cap.available_container_slots == 0


# 16. Nonexistent worker ID validation
def test_nonexistent_worker_validation():
    w1 = make_worker("W-001")
    req = BoxCreationRequest(
        name="missing-worker-test",
        ram_limit_gb=1.0,
        cpu_limit_cores=1.0,
        storage_limit_gb=5.0,
        eligible_worker_ids=["W-001", "W-999"],  # W-999 does not exist
        failover_enabled=False,
    )

    validation = validate_box_creation(req, [w1], [])
    assert validation.valid is False
    assert any("Worker 'W-999' does not exist" in err for err in validation.errors)
