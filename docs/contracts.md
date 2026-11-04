# Integrated backend contracts

Shared Pydantic models define the backend protocol. Deploy compatible contract versions to the controller and workers together; strict parsers reject unknown messages and fields.

| Owner | Responsibilities |
| --- | --- |
| Control Plane, `control_plane` | Management API, database/migrations, registration, worker gateway, builds/publication, readiness/routing and recovery coordination |
| Worker Service, `worker_agent` | Local Docker, resource admission, snapshots/heartbeats/events, owner socket and lease watchdog |
| Orchestrator, `orchestrator` | Pure deterministic Box/capacity/placement/reservation/failover decisions; never starts containers |

## Types and units

Use Python 3.12/Pydantic v2, `shared` imports from `backend`, and
`model_dump(mode="json")` / `model_dump_json(exclude_none=True)`. Unknown fields,
nonfinite resources and naive datetimes are rejected. UUIDs serialize as strings;
worker IDs are stable nonblank strings (header transport restricts them to
printable ASCII without spaces, at most 256 characters). All frames are one JSON
object with a top-level `type` discriminator, with no nested payload envelope.

`_gb` is GiB and `_mb` is MiB. RAM commands use `ceil(Box GB * 1024)` and the
worker rechecks actual MiB capacity. A Box fits entirely on one worker, and
standby capacity is independently funded on a distinct eligible worker. Disk is
local, not pooled or replicated. Docker hard-limits CPU/RAM; storage is monitored
logical data-volume enforcement, not a portable hard filesystem quota.

## Provisioning and sessions

- Management uses `Authorization: Bearer <ADMIN_TOKEN>`. This is administration,
  not an end-user identity/tenant system.
- `POST /api/workers/register` takes `worker_id`, `hostname`, CPU/RAM/storage,
  max containers, architecture, supported runtimes and optional available values
  plus a trusted reachable `address`. It returns a token once and remains offline
  until an authenticated worker publishes actual capacity. Duplicate IDs are
  409 and never silently rotate tokens. Database storage is HMAC-SHA256 only.
- `/ws/workers` requires `Authorization: Bearer <worker_token>`,
  `X-Worker-ID`, and `X-Worker-Lease-Enforced: true`. Tokens in URLs are rejected.
  One current authenticated socket/session owns each worker's pending commands.
  Results from another worker or stale socket cannot resolve those commands.
- `POST /api/workers/{worker_id}/snapshot` accepts exactly `WorkerSnapshot`.
  It requires the same bearer/ID plus `X-Worker-Lease-ID` matching the current
  connected session. Snapshots publish automatically on heartbeat/reconnect.
  Server receipt time is authoritative; stale session publication is rejected.
- Disconnect accepts a worker's token/ID or the management bearer. Acknowledgment
  marks draining and initiates handoff; it is not confirmation of migration.

## WebSocket protocol

| Direction | type | Model / meaning |
| --- | --- | --- |
| Controller → worker | `run_container` | `RunContainerCommand`; includes optional positive `storage_limit_gb` carrying the Box's complete allocation |
| Controller → worker | `stop_container` | `StopContainerCommand` |
| Controller → worker | `inspect_container` | `InspectContainerCommand` |
| Controller → worker | `lease` | `LeaseGrant`: worker/session ID, issued/expires timestamps, lifetime at most 60 seconds |
| Worker → controller | `command_result` | `CommandResult`; optional typed `inspection` |
| Worker → controller | `heartbeat` | `Heartbeat`; identity must match authentication |
| Worker → controller | `container_status` | `ContainerStatusEvent`; validated replica/container ownership |
| Worker → controller | `container_logs` | `ContainerLogsEvent`; same ownership validation |

Use `CONTROL_PLANE_MESSAGE_ADAPTER` for all incoming controller frames.
`CONTROL_PLANE_COMMAND_ADAPTER` still parses only the three executable commands.
Use `WORKER_MESSAGE_ADAPTER` for worker frames.

`ContainerInspection` contains container/deployment IDs, lifecycle, Docker health,
CPU/RAM limits, optional memory use, and typed `PortBinding` entries (internal
port, host IP/port, protocol). It excludes raw Docker config, environments and
credentials. A successful inspection must match its request's container ID.
A successful run proves Docker startup only; controller HTTP readiness is
required before enabling the application route.

Request UUID/payload pairs are stable across retries. The worker's private
journal and Docker labels deduplicate execution and recover interrupted creates.
Successful replay never restarts a subsequently stopped application. Historical
container reports do not change deployment lifecycle to running. Retain the
journal/identity across restarts.

The worker renews an execution lease on authenticated heartbeats. No lease means
no new admissions. Expiry independently kills owned workloads, without waiting
behind an image-pull lock. Persisted lease expiry bounds restart authorization. Supervisor shutdown fences
remaining workloads before its watchdog exits, regardless of retention settings.
Default lease/heartbeat are 15/5 seconds; controller fence grace is 75 seconds,
covering worker maximum lifetime and clock-skew policy. Lower timing only when
both sides are configured together. Fencing is a process watchdog assumption,
not external consensus/power fencing; a frozen watchdog/failed Docker daemon can
break it. No guaranteed recovery time is claimed.

## Orchestrator and reservation reconciliation

The original interfaces in `orchestrator/service.py` are retained. Integrated
callers additionally pass the complete reservation ledger, explicit
`active_reservation_ids`, required image architecture and application runtime.
Creation uses one stable Box UUID and deterministic reservation IDs. Selection
must choose an already funded worker; no unreserved alternatives are dispatched.

`WorkerSnapshot.available_*` is observed free execution capacity before idle
reservation subtraction. A reservation is active only when the current replica
and an authenticated, sufficiently recent snapshot/heartbeat show its running
container. Only that matching allocation is added back during selection;
other idle holds remain subtracted. Conservative stale observations can defer
placement until a fresh snapshot arrives. Worker admission always rechecks.

The controller locks worker rows in stable order during ledger/Box mutation.
Uniqueness constraints prevent duplicate Box-worker and Box-role holds. Stop
releases reservations only after acknowledged termination or the configured
fencing deadline; deletion is soft to preserve history.

Failover decisions have stable UUIDs and persistent state in PostgreSQL.
Promotion and request identity are committed before dispatch. Restart resumes
pending builds/deployments/recoveries with the same request identity. Recovery
uses only the reserved standby, verifies readiness again and updates the actual
route; absence of a safe replacement produces failure rather than fake success.

## Pool membership and application relay (implemented, manual verification pending)

The existing shared entities/executable command messages are unchanged.
`shared/relay.py` adds separate `RelayRequest`/`RelayResponse` envelopes with
request UUID, bounded headers and base64 body. A request includes deployment and
owned container identity, HTTP method, relative path/query and internal port;
it cannot supply an arbitrary URL, address or host port. Bodies are limited to
4 MiB and frames to 6 MiB. Responses bind to the exact worker/socket/request.

Pool membership is persisted by the Control Plane as nullable `Worker.pool_id`
and `Box.pool_id`, preserving unpooled legacy records. Pool creation/list/code
rotation/status require admin authentication. `/api/pools/join` exchanges an
unexpired, bounded-use join code plus a locally generated worker identity/token
for membership; only an HMAC hash is retained. A repeated enrollment with the
same identity/token is idempotent. A code does not authorize scheduling or
management. Box creation rejects workers outside the chosen pool and requires
live pool workers before admitting a new Box.

`/ws/workers/apps` is independent of `/ws/workers`. Its worker token/ID and
session header must match the current live control session. Worker's relay
reconnects when the control session changes. It checks lease validity and
Docker ownership/deployment labels before using the container's inspected local
binding. Public proxy and readiness checks use this relay for joined workers;
legacy direct-address workers retain their explicit direct transport.

The default route is `/apps/{deployment_id}/{path}` on the configured public
origin; only the current running primary is served. Optional APP_DOMAIN routing
maps flat app UUID hostnames after owner-managed DNS/tunnel configuration.
HTTP application upgrades/streaming, transparent HTML asset rewriting, tenant
browser-origin isolation, data replication and HA remain out of scope. See
[manual milestone](backend-milestone.md) for operator and laptop commands.

The user requested no feature tests yet. Previous test totals do not verify this
new relay/pool/package feature set.
