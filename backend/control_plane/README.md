# Control Plane

The central service authenticates management requests and workers, persists
state, calls Orchestrator, builds/publishes real images, dispatches Worker Service commands,
verifies readiness, and proxies traffic to the current primary. It never uses a
worker's Docker socket; its own local Docker connection is only for builds.

See the root [walkthrough](../../WALKTHROUGH.md) and
[integration review](../../docs/integration-review.md).

## Configuration and startup

Use root `requirements.txt` in the Python 3.12 virtual environment. Export these
variables before starting; `.env` is not read automatically:

| Variable | Meaning/default |
| --- | --- |
| `DATABASE_URL` | Explicit PostgreSQL URL; accepts `postgres://` / `postgresql://` and normalizes to psycopg 3. TLS options belong in the URL for an external database. No embedded cloud credentials. |
| `DATABASE_CA_FILE` | Optional service CA path; when supplied, enforces `sslmode=verify-full` and hostname validation. |
| `DATABASE_DIRECT_DNS` | `false`; optional bounded per-connection DNS lookup for system-resolver problems, preserving TLS hostname and refreshing addresses on reconnect. |
| `ALLOWED_HOSTS` | Exact allowed request hosts; configure the public API hostname plus intended loopback names. |
| `EXPOSE_API_DOCS` | `true` for local development; public deployment sets `false`. |
| `SECRET_KEY` | Required stable random HMAC secret, at least 32 characters; changing it invalidates worker tokens. |
| `ADMIN_TOKEN` | Required different random management bearer secret, at least 32 characters. This is team administration, not a user/account system. |
| `REGISTRY_URL` | Required for deployment; `host[:port][/namespace]` without scheme. All execution daemons must reach it. |
| `REGISTRY_USERNAME`, `REGISTRY_PASSWORD` | Optional publisher credentials; private-image pull credentials must also be configured locally on workers. |
| `PUBLIC_BASE_URL` | `http://127.0.0.1:8000`; advertised reachable controller URL, not a fabricated domain. |
| `BUILD_DIR` | `/tmp/lattice-builds`; private per-deployment checkout directory, removed after each job. |
| `PYTHON_BASE_IMAGE`, `NODE_BASE_IMAGE` | `python:3.12-slim`, `node:22-alpine`; use compatible registry images, preferably pinned digests in deployment. |
| `ALLOWED_REPOSITORY_HOSTS` | JSON list, default `["github.com"]`; public HTTPS owner/repository URLs only. |
| `ALLOW_LOCAL_REPOSITORIES` | `false`; explicit loopback Git HTTP exception for tests/local development. |
| `CORS_ORIGINS` | JSON list, default empty; configure actual frontend origins. |
| `COMMAND_TIMEOUT`, `DOCKER_TIMEOUT`, `GIT_TIMEOUT`, `READINESS_TIMEOUT` | `60`, `60`, `180`, `30` seconds. |
| `HEARTBEAT_TIMEOUT`, `MONITOR_INTERVAL` | `20`, `1` seconds. |
| `LEASE_SECONDS`, `FENCE_GRACE_SECONDS` | `15`, `75` seconds. Heartbeats must arrive before lease expiry. Keep grace at least worker maximum lease + maximum clock skew; tests explicitly reduce both sides together. |
| `AUTO_MIGRATE` | `false`; opt-in migration on startup, otherwise run the migration command first. |

```bash
PYTHONPATH=backend python -m control_plane.database.init_db
PYTHONPATH=backend python -m control_plane.run --env-file .env
```

Migrations are versioned under `database/migrations`. The initial revision is for
a fresh database. The original unversioned prototype schema can be adopted with the guarded tool
below. It validates the expected shape/data, permits only reviewed additive
operations and widening, fingerprints every original field before/after, and
stamps the revision only after schema/data checks pass. It refuses duplicates or
unexpected changes and runs atomically under database/table locks. It is never
invoked automatically at service startup.

```bash
# First create and restore-test an owner-only custom-format pg_dump backup.
PYTHONPATH=backend python -m control_plane.database.adopt_legacy --env-file .env
PYTHONPATH=backend python -m control_plane.database.adopt_legacy --env-file .env --apply --backup /private/path/cloud-before.dump --report /private/path/adoption-result.json
```

Existing application data is retained. PostgreSQL schema changes roll back
if a consistency check fails. Keep the backup outside Git. The controller's
normal monitor will mark legacy worker records offline until real clients
reconnect; database rows alone do not prove live capacity.
Destructive downgrade is disabled. No external database was changed during tests.
One controller owns a PostgreSQL session advisory lock; this is not multi-node HA.

## API

All `/api` management routes require `Authorization: Bearer <ADMIN_TOKEN>`,
except snapshot publication, which requires that worker's bearer token, ID and
current lease ID. Disconnect permits either the administrator or that worker.

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/health` | Live DB reachability and connected worker count |
| POST | `/api/workers/register` | Provision a unique ID/token, initially offline; duplicate ID 409 |
| GET | `/api/workers`, `/api/workers/{worker_id}` | Latest canonical snapshots, no tokens/hashes |
| POST | `/api/workers/{worker_id}/rotate-token` | Admin-only offline credential recovery; refuses active workloads/connections/unexpired fencing windows |
| POST | `/api/workers/{worker_id}/snapshot` | Worker/session-authenticated full `WorkerSnapshot` |
| POST | `/api/workers/{worker_id}/disconnect` | Mark draining and initiate verified handoff; acknowledgment is not completion |
| POST, GET | `/api/boxes` | Transactional reservations via the real Orchestrator service; list Boxes |
| GET, DELETE | `/api/boxes/{box_id}` | Details or soft deletion after confirmed stop; retains history |
| POST, GET | `/api/deployments` | Queue a version / list historical versions |
| GET | `/api/deployments/{id}` | Shared deployment contract |
| GET | `/api/deployments/{id}/status` | Runtime replicas, health, bindings and failure reason |
| GET | `/api/deployments/{id}/logs` | Build/runtime logs; `limit` 1–2000, default 500 |
| POST | `/api/deployments/{id}/stop` | 200 once stopped; 202 while confirmation/fencing remains pending |
| POST | `/api/deployments/{id}/redeploy` | Stop previous version then create a new UUID/version (201); 409 while old shutdown is pending |
| WS | `/ws/workers` | Authenticated, session-scoped commands/results/telemetry plus execution leases |
| HTTP | `/apps/{id}/{path}` | Real route to verified primary; preserves method/body/query/status; unavailable apps return 503 |

Worker WebSockets use bearer + `X-Worker-ID` + `X-Worker-Lease-Enforced: true`.
Tokens in query strings are rejected. The gateway validates sender/session,
heartbeat identity and container event ownership. One worker disconnect cannot
resolve or fail another worker's pending commands.

Deployments accept the original request fields plus optional
`application_config`. A repository may contain `lattice.json`:

```json
{
  "start_command": ["python", "server.py"],
  "internal_port": 8000,
  "readiness_path": "/health",
  "environment_variables": {"APP_MODE": "demo"}
}
```

API values override repository configuration. FastAPI `main:app` / `app:app`
and Node start scripts/common entry files are detected when unambiguous;
otherwise supply the command. Existing Dockerfiles are respected. Images must
run as worker UID 65532 with a read-only root and writable `/data` and `/tmp`.
Only successful typed inspection plus actual HTTP readiness enables routing.
Build/publication/startup/readiness failures stay failed with no public URL.
A newly built local tag is never treated as a published remote image.

The HTTP path proxy supports prefix-aware apps. It does not implement app
WebSocket upgrades, rewrite root-relative links/cookies/redirects, provide
per-app browser origin isolation, or configure DNS/TLS. Do not treat these paths
as isolated origins for mutually untrusted public applications.
