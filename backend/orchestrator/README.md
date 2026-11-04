# Orchestrator

Pure Python Box validation, resource accounting, deterministic primary/standby
placement and failover decisions. This module consumes the existing shared
Pydantic models. It does not run Docker, serve HTTP or own a database schema.

## Run and test

Use Python 3.12 and the repository virtual environment. From the repository root:

```bash
.venv/bin/python -m pytest backend/orchestrator/tests
.venv/bin/python -m pytest
.venv/bin/ruff check backend tests
.venv/bin/ruff format --check backend tests
# Includes the existing real Docker worker tests:
LATTICE_RUN_DOCKER_TESTS=1 .venv/bin/python -m pytest
```

Default pytest discovery now includes every backend module. Imports use
`backend` as the source root; set `PYTHONPATH=backend` for standalone Python
commands. This module needs no environment variables or running external service.

## Resource accounting

Each Box fits entirely on one physical worker. A failover Box has an independent,
distinct standby allocation. CPU, RAM, storage and container slots are never
pooled across workers. GB/MB follow the shared binary units.

Worker free capacity already reflects active local allocations. Only **idle**
reservations are subtracted from that free capacity. The Control Plane supplies
`active_reservation_ids: set[UUID]` identifying allocations reflected in the
specific snapshot being evaluated. This is local Python context, not a new wire
message or a shared-model change.

- `None`: no reconciliation metadata supplied. Safe when there is no overlap to
  resolve. Active containers plus recorded reservations require explicit metadata.
- `set()`: all listed reservations are known to be idle; actual active containers
  still count separately toward slots.
- A populated set: those complete allocations are already counted by telemetry;
  subtract only the other reservations. Unknown IDs or more active reserved slots
  than actual active containers are rejected.

For example, one active container plus one idle reservation occupies **two**
slots. Using `max(active_count, reserved_count)` can overbook a worker. An active
2 GB allocation already reflected in 6 GB free RAM leaves 6 GB; subtracting it
again would incorrectly report 4 GB.

The metadata must describe the same observation as the snapshot, not merely a
dispatched command. For the full-allocation accounting used here, apply the Box's
complete CPU/RAM limits and matching data-volume budget on Worker Service. Partial
allocations would need richer reconciliation metadata before they can safely be
treated as fully active reservations.

Resource arithmetic preserves decimal boundaries without rounding free capacity
upward. Identical duplicate rows are counted once; conflicting IDs or duplicate
Box allocations on one worker fail validation. Capacity is clamped at zero.

## Placement and compatibility

Workers must exist, be online and fit the complete profile. When supplied,
`required_architecture` and `application_type` filter compatibility. Common
architecture aliases are normalized (`x86_64`/`amd64`, `aarch64`/`arm64`). Supply
the image architecture/runtime during deployment; an unspecified constraint is
not evidence that an arbitrary image can run everywhere.

Eligible workers are ranked by reconciled occupied slots, available RAM, CPU,
local storage, then worker ID. Input order does not change the selected workers.
`application_requirements: ResourceRequirements` can additionally verify that
application requirements fit inside the Box. The complete Box remains reserved.

`create_box_placement(..., box_id=stable_uuid)` supports idempotent retry using a
Control Plane-assigned ID. Reservation UUIDs derive deterministically from the
Box, role and worker. Replays return the same existing allocations and reject a
changed allocation request. Without `box_id`, each call is a new creation.

## Public interfaces

Import these unchanged names from `orchestrator.service`:

| Function | Return model |
| --- | --- |
| `validate_box_creation(request, workers, reservations, **context)` | `BoxValidationResult` |
| `create_box_placement(request, workers, reservations, box_id=None, **context)` | `PlacementDecision` |
| `calculate_worker_capacity(worker, reservations, active_reservation_ids=None)` | `WorkerCapacity` |
| `select_deployment_worker(box, workers, excluded_worker_ids=None, **selection_context)` | `WorkerSelectionResult` |
| `select_failover_worker(box, workers, failed_worker_id, **selection_context)` | `WorkerSelectionResult` |
| `release_box_reservation(box_id, reservations)` | `ReservationReleaseResult` |

Additional context is keyword-only:

- Validation/creation/ranking: `active_reservation_ids`, `required_architecture`,
  `application_type`.
- Selection/failover: the above plus `reservations` and optional
  `application_requirements`.
- Capacity calculation: `active_reservation_ids` only.

The original two-argument selection form treats the assigned Box primary/standby
as trusted evidence of existing reservations. It checks their physical fit but
cannot audit the ledger. It **never** chooses an unassigned fallback. Integrated
Control Plane callers should always pass the full ledger and active-ID mapping;
an explicit empty ledger proves no allocations and therefore selects nothing.

With a ledger, selection requires a sufficient reservation for this specific
Box, preserves all other Boxes' idle holds, and checks physical capacity. A target
already active for this Box needs reconciliation/promotion rather than another
run command. Healthy spare capacity alone is not a reserved failover target.

If a standby fails, keep a healthy primary serving. A new standby must first be
reserved safely and persisted by the Control Plane. The selector can then use a
reserved eligible alternative after primary failure. Missing safe capacity
returns `worker_id=None` with a reason. Invalid input raises `ValueError` or
produces validation errors; no simulated deployment is reported.

## Failover state and persistence

`FailoverEngine.evaluate_failover(...)` is called after a confirmed primary
failure. It immediately returns `SELECTING_STANDBY` with a protected target, or
`FAILED` with a reason. No arbitrary timers delay decisions. Failure of an
unrelated worker or only the standby does not redeploy a healthy primary.

The state graph is validated:

```text
DETECTING -> WORKER_FAILED -> SELECTING_STANDBY -> REDEPLOYING
REDEPLOYING -> HEALTH_CHECK -> RECOVERED
```

Each nonterminal stage can also transition to `FAILED`; terminal decisions cannot
restart themselves. Repeating the same state is idempotent. Detection normally
occurs in Control Plane, so evaluation starts after it is confirmed; persisted earlier
stages can be restored and advanced.

Repeated notifications reuse one decision per `(deployment_id, failed_worker_id)`.
Decision UUIDs are stable across restarts. An in-process lock protects concurrent
notifications, and callers receive defensive copies. A different Box cannot
reuse an existing deployment/failure key.

Use `engine.decisions()` to obtain shared `FailoverDecision` models for Control
Plane persistence, and `FailoverEngine(initial_decisions=saved_models)` to
restore history. `get_decision` returns a copy. Clearing actionable history is
rejected. In-memory caching and deterministic UUIDs alone do not prevent duplicate
dispatch from independent Control Plane processes: persist and claim decisions
transactionally, restore their states, and use the decision UUID as a stable
dispatch/idempotency key. Later recovery attempts need correctly scoped deployment
identities and fencing; replaying a completed notification must not launch again.

## Control Plane integration responsibilities

1. Load current worker snapshots, all reservations and their active mappings from
   one consistent view; supply architecture, runtime and application constraints.
2. Lock the relevant worker/reservation records, calculate and persist Box plans
   atomically. Stable IDs provide retry identity, not database isolation.
3. Use ledger-aware selection. Persist failover decisions/state transitions before
   dispatch, claim each operation once, and verify the target is still eligible.
4. Dispatch Docker commands through Worker Service. Keep application readiness separate
   from a running container. Persist status/log updates and reconcile reconnects.
5. Release reservations on Box deletion/workload stop. Failover promotion,
   replacement standby reservations and stale-primary fencing must be persisted
   before conflicting work can run. Data replication is a separate concern.

Orchestrator plans decisions and returns models; it does not mutate a database or
send execution commands. Admission on Worker Service is the final local safety check.
The scheduler alone cannot guarantee a five-minute recovery time; image access,
network recovery, application readiness and data availability also matter.
