# Worker Service

Real local Docker execution, bounded resource admission, host telemetry,
authenticated WebSockets, request replay protection, owner controls and graceful
shutdown. See the [root walkthrough](../../WALKTHROUGH.md) for setup.

## Requirements and installation

- Python 3.12; use the repository's existing `.venv` and `requirements.txt`.
- A running **Linux-container** Docker Engine. Docker Desktop on macOS is
  supported. Native Windows worker support is implemented in the 0.3.0 candidate
  with Docker Desktop Linux containers; Windows runtime validation is pending.
- A pre-provisioned worker ID/token from the Control Plane owner.
- A registry image that the worker's Docker daemon can pull. Private-registry
  authentication uses the owner's Docker credential configuration; registry
  credentials are never included in command results.

From the repository root:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Prepare a private configuration using [the environment example](.env.example)
or [the JSON example](config.example.json). Export environment variables before
launch; `.env` files are not read implicitly. Keep real tokens in exported
environment variables or an owner-only JSON file outside Git. Use mode `0600`
for JSON config files. Environment values override JSON values.

```bash
export CONTROL_PLANE_URL=http://127.0.0.1:8000
export WORKER_ID=W-001
# Set WORKER_TOKEN securely in your shell; do not commit it or paste it into logs.
cd backend
python -m worker_agent.main
```

To use a JSON file: `python -m worker_agent.main --config /absolute/path/config.json`.
Remote connections require HTTPS/WSS unless `ALLOW_INSECURE_CONNECTION=true` is
explicitly set. Loopback HTTP/WS is permitted for local development.

## Identity and startup

`python -m worker_agent.main identity` creates/prints the stable local worker ID
without needing Docker, a URL or a token. If the Control Plane has assigned an
ID, export `WORKER_ID` **before the first identity/run command**. A mismatch with
an existing persisted identity fails; the worker does not silently change IDs.
An identity is not a registration or an authentication token.

Worker IDs used in the authentication header are printable ASCII without spaces,
at most 256 characters. The default UUID and identifiers such as `W-001` fit.

State defaults to `~/.local/share/lattice/worker` (directory `0700`,
files `0600`). Override with `STATE_DIR` or `--state-dir`; use a short path for
Unix sockets on POSIX; Windows uses authenticated loopback controls. A process lock prevents two worker processes using the same state.
Preserve this directory across restarts: it contains the identity, owner pause
state, request journal and latest canonical `snapshot.json`. Tokens are not
written into these state files. Do not delete state to work around a running
process lock.

On startup, the worker validates configuration, verifies the local Docker daemon,
loads its identity/state, starts the local owner socket, connects to
`/ws/workers`, sends a heartbeat and reconciles all owned containers. Network
loss/server restarts trigger bounded exponential backoff with jitter. HTTP
401/403 or authentication/policy WebSocket close codes are terminal, so invalid
credentials are not retried indefinitely. A stopped Docker daemon yields an
actionable nonzero startup exit; restart Docker and relaunch the worker.

## Execution leases and snapshots

The integrated controller grants an execution lease on connect/heartbeat. The
worker sends `X-Worker-Lease-Enforced: true`, publishes full hardware snapshots
with its current lease ID, and accepts new runs only while leased. A separate
watchdog kills owned workloads after expiry, including during an image pull;
it does not wait behind the runtime mutation lock. The expiry is saved privately
for bounded restart reconciliation. Keep heartbeats comfortably below the lease
lifetime (defaults 5 and 15 seconds).

This assumes the worker/watchdog and Docker remain operational. It is not
external power fencing and cannot exclude an application if the watchdog/daemon
is frozen. Default controller fence grace is 75 seconds; coordinate any reduction
with every worker's maximum lease and clock-skew policy. Disabling leases is only
for isolated adapter tests/standalone peers; the integrated gateway rejects it.

## Owner commands

Run these from `backend` in another terminal with the same `STATE_DIR` (or
`--state-dir`). They do not require a token in that terminal.

| Command | Behavior |
| --- | --- |
| `python -m worker_agent.main status` | Sanitized worker and container details |
| `python -m worker_agent.main list` | Same view, including retained stopped containers |
| `python -m worker_agent.main pause` | Persist pause state, reject new runs, freeze owned running containers |
| `python -m worker_agent.main resume` | Unpause owned containers and allow new runs |
| `python -m worker_agent.main stop` | Stop owned workloads; remain paused until resumed |
| `python -m worker_agent.main disconnect` | Drain admissions, notify the Control Plane, allow a handoff interval, then exit |
| `python -m worker_agent.main snapshot` | Print the canonical hardware/resource snapshot; requires configuration and Docker |
| `python -m worker_agent.main check` | Validate configuration/Docker and print the snapshot |

The POSIX owner API is a `0600` Unix socket inside the private state directory; it is
not exposed over TCP. SIGINT/SIGTERM use the same graceful disconnect path.
Default handoff grace is 10 seconds. `STOP_ON_DISCONNECT=false` permits serving during the handoff grace. A confirmed
controller stop or execution lease expiry still terminates workloads. `true`
also stops them at the end of the local disconnect grace. Integrated leased
workers always fence remaining workloads before the supervisor exits, since its
watchdog will no longer be running.
An HTTP acknowledgment does not prove migration completed. If notification
fails, the failure is logged and local shutdown still proceeds after the grace
interval. Accepted Docker operations are drained, not abandoned mid-creation.

## Resource and image policy

`IMAGE_PULL_POLICY=always` pulls the requested registry image before a new run.
For a pre-cached image during an outage, owners may explicitly choose
`if_not_present`; this requires an immutable `repository@sha256:<digest>`
reference. The local image is inspected first and a missing image is pulled from
the registry. There is no implicit fallback to a possibly stale mutable tag.

- Each application runs on one physical worker; nothing pools machines.
- CPU/RAM are hard Docker limits (`nano_cpus`, memory and memory+swap limits).
  Container count and owner CPU/RAM budgets are checked before admission.
  Admission also uses Docker daemon CPU/RAM and observed host free memory.
  Unbounded foreign containers conservatively reserve the daemon's capacity.
- Docker Desktop's CPU/RAM capacity is read from the **execution daemon**, rather
  than advertising the host laptop's full capacity. Architecture comes from
  that daemon too.
- Data uses a dedicated named volume mounted at `/data`; unrelated deployments
  use distinct user-defined bridge networks. Host ports are dynamically assigned
  on `127.0.0.1` by default. Inspection returns the actual bindings.
- Containers run as numeric non-root `65532:65532`, with all capabilities
  dropped, `no-new-privileges`, a read-only root, bounded `/tmp` and `/run` tmpfs,
  a PID limit and rotated Docker logs. No host paths, privileged mode, host
  network, Docker socket or arbitrary shell-command operations are accepted.
- Images must work with that non-root UID and a read-only root. Create writable
  `/data` with the configured UID **in the image** if the application needs it;
  Docker copies initial directory ownership into a new named volume. Use `/tmp`
  for temporary files, listen on `0.0.0.0` inside the container, and define an
  appropriate application health check. The worker does not rewrite an image's
  entrypoint, dependencies or filesystem permissions.

`MAX_STORAGE_GB` is the **logical data-volume** owner budget. Integrated run
commands carry the Box allocation as `storage_limit_gb`. Local
`DEPLOYMENT_STORAGE_GB` / `DEPLOYMENT_STORAGE_LIMITS` remain fallback defaults for
standalone commands without that optional field. The worker
measures volume bytes through Docker's disk-usage API, refuses over-budget
admissions, and stops offending workloads after a measured overrun. Unknown
measurements fail closed. This is periodic detection, not a portable hard
filesystem quota: data can exceed a limit between polls. It does not quota image
layers, shared daemon disk use or a container's bounded logs/tmpfs. On Docker
Desktop, host free disk is only a conservative host check and does not establish
free space within the Docker VM's disk image. Disk-full errors are reported.

Active volumes reserve their full configured budgets; stopped volumes retain
data but account only actual bytes. Stopping releases compute/count capacity.
Data is never automatically deleted. Changing an existing volume's allocation
requires an explicit owner data-management decision; a mismatched stored policy
is rejected. Do not use broad Docker prune commands as worker cleanup.

## Commands, events and failure behavior

Only shared `run_container`, `stop_container` and `inspect_container` messages
are accepted. Results correlate by UUID `request_id`. A private SQLite ledger
persists payload hashes and terminal results, not environment values. Replays
return the recorded result. A changed payload with the same request ID fails.
Docker labels recover an interrupted run after creation but before the journal
was finalized, preventing duplicate containers. A different request cannot
start another active container for an already active deployment on this worker.
Use a new request ID after a terminal failure; successful replay does not restart
an application that was subsequently stopped.

Commands execute off the asyncio event loop through a bounded queue and a single
consumer. Mutations, owner actions and admission checks share a runtime lock.
Heartbeats run independently of image pulls. Fatal journal/processor errors stop
the worker instead of leaving an unconsumed command queue hanging.

Health/lifecycle changes emit shared `container_status` events. `inspect_container`
returns typed `CommandResult.inspection` plus a human-readable message with
state, health, limits, memory usage and host ports. It never transmits raw Docker config/environment.
Application readiness is separate from a running container; the Control Plane
must verify readiness before marking a deployment healthy.

Logs are polled in bounded tails/byte budgets, decoded safely, deduplicated during
the process lifetime, and emitted as shared `container_logs`. Worker tokens are
redacted in local logs, tracebacks, failures and forwarded container logs. This
is best-effort bounded delivery, not an exactly-once durable log pipeline;
high-volume/disconnected periods can lose older lines. Applications must avoid
logging their own secrets. Docker's local log storage is rotated independently.

## Configuration reference

| Variable | Default / meaning |
| --- | --- |
| `CONTROL_PLANE_URL` | Required HTTP(S) or WS(S) base URL |
| `WORKER_TOKEN` | Required worker-specific secret |
| `WORKER_ID` | Provisioned ID, otherwise a generated persisted UUID |
| `STATE_DIR` | Private persistent directory described above |
| `MAX_CONTAINERS` | `4` |
| `MAX_CPU_CORES` | `2` |
| `MAX_RAM_GB` | `4` |
| `MAX_STORAGE_GB` | `16`, logical data budget |
| `DEPLOYMENT_STORAGE_GB` | `1`, local default per deployment |
| `DEPLOYMENT_STORAGE_LIMITS` | `{}`, JSON mapping of deployment UUIDs to GB |
| `HEARTBEAT_INTERVAL` | `5` seconds; also event/storage polling interval |
| `RECONNECT_MIN_SECONDS`, `RECONNECT_MAX_SECONDS` | `1`, `30` |
| `CONNECT_TIMEOUT`, `DOCKER_TIMEOUT` | `10`, `60` seconds |
| `IMAGE_PULL_POLICY` | `always`; `if_not_present` permits only immutable `@sha256` references and pulls missing images |
| `DISCONNECT_GRACE_SECONDS` | `10` |
| `STOP_ON_DISCONNECT` | `false` |
| `COMMAND_QUEUE_SIZE` | `32` |
| `LOG_TAIL_LINES`, `LOG_MAX_BYTES` | `50`, `16384` per container poll |
| `CONTAINER_USER` | `65532:65532`, numeric non-root UID:GID |
| `BIND_ADDRESS` | `127.0.0.1`; expose elsewhere only with an agreed network/routing design |
| `ALLOW_INSECURE_CONNECTION` | `false`; remote plaintext connections require opt-in |
| `SNAPSHOT_PATH` | Optional override; defaults to `/api/workers/{id}/snapshot` |
| `REQUIRE_CONTROL_PLANE_LEASE` | `true`; required by the integrated controller |
| `MAX_LEASE_SECONDS`, `MAX_CLOCK_SKEW_SECONDS` | `60`, `2`; coordinate controller fence grace when changing |
| `DOCKER_HOST` | Optional **local socket only**, `unix://` or `npipe://` |

Fields named GB/MB follow the shared binary units (GiB/MiB).

## Verification

From the repository root:

```bash
.venv/bin/python -m pytest
.venv/bin/ruff check backend/worker_agent
.venv/bin/ruff format --check backend/worker_agent
LATTICE_RUN_DOCKER_TESTS=1 .venv/bin/python -m pytest backend/worker_agent/tests/test_docker_integration.py
```

Default tests cover configuration, private state, telemetry, security options,
resource/storage admission, lifecycle adapters, inspection/logs, journal replay,
WebSocket authentication/reconnection, owner commands and shutdown. Docker tests
are explicitly opt-in and **fail**, rather than simulate execution, when the
daemon/image is unavailable. They use the public ECR Traefik image pinned to
`sha256:16acb89c6db341182970d6fdafece31303b0a380a8ed7aa51682e225229bf1d2`
with the explicit cache policy, pulling it if absent. They start real HTTP
servers, verify cgroup settings and reachability, provoke a real volume overrun,
and exercise WebSocket commands plus real pause/resume/stop. Cleanup touches only
resources with that test's unique worker ID; the pulled image remains cached.

See [the integration handoff](docs/integration.md) for the integration boundaries. Passing isolated tests does not establish public routing, production security certification, or a recovery SLA.

Recorded local results and their scope are in [verification.md](docs/verification.md).

Implementation references: [Docker SDK container options](https://docker-py.readthedocs.io/en/stable/containers.html)
and [websockets asyncio client](https://websockets.readthedocs.io/en/16.1/reference/asyncio/client.html).

## Pool joining and outbound HTTP relay candidate

An installable `lattice connect` command now enrolls this laptop in a named pool,
stores its own identity/token privately and runs the existing worker with a
separate outbound application WSS socket. Public requests resolve only to its
running, owned deployment containers while its lease is valid. Local controls
are also exposed as `lattice status/list/pause/resume/disconnect`.

See the [manual milestone](../../docs/backend-milestone.md)
for installation, real configured pool, live monitoring and read-only registry
credentials. Version 0.3.0 includes a native Windows worker candidate; see
[PowerShell setup](../../docs/windows-worker.md). It is not published on PyPI,
and native Windows operation has not yet been verified.

## Restart behavior

Disconnect stops owned workloads without adding a new persisted owner pause. Explicit pause and stop remain persistent until resumed. Status reports admission blockers, lease health, storage and Docker availability.
