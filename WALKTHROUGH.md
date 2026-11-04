# Local setup walkthrough

## Prerequisites

Use Python 3.12, Git, PostgreSQL and a Linux-container Docker Engine. Run the controller on Linux/macOS or WSL: its leadership-lock module imports POSIX `fcntl`. Native Windows instructions below apply to workers. Install Node.js and pnpm for the dashboard.

## Install and configure

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install --no-deps -e .
cp .env.example .env
```

Replace all placeholder secrets in `.env`. Generate independent random values for `POSTGRES_PASSWORD`, `SECRET_KEY` and `ADMIN_TOKEN`. The password in `DATABASE_URL` must match PostgreSQL. Keep `SECRET_KEY` stable: changing it changes worker token hashes. Restrict private file permissions (`chmod 600 .env` on POSIX). The private runner rejects insecure file permissions. Never source an environment file from an untrusted source; shell sourcing executes code.

## Database and local registry

```bash
docker compose up -d
```

Compose loads `.env` for interpolation. PostgreSQL binds loopback port 5432. The development registry uses daemon host networking on port 5050; Docker Desktop host-network support must be configured where required. This is a local convenience, not a registry reachable from arbitrary remote laptops. Remote workers need a reachable authenticated registry such as GHCR.

Export the intended database settings before running migrations. Python migration entry points do not implicitly load `.env`:

```bash
set -a
source .env
set +a
PYTHONPATH=backend python -m control_plane.database.init_db
PYTHONPATH=backend python -m control_plane.run --env-file .env
```

Use a fresh database for fresh setup. Existing schemas require reviewed backups/migration; do not drop data or stamp revisions to suppress errors. One controller process owns a database. Leave `AUTO_MIGRATE=false` unless you deliberately want startup migrations.

## Dashboard

```bash
cd frontend
pnpm install --frozen-lockfile
cp .env.example .env.local
pnpm dev
```

Set server-only `CONTROL_PLANE_URL` to the controller. Set `NEXT_PUBLIC_WORKER_SERVER` to the reachable origin used in copied enrollment commands. Enter the operator bearer in the dashboard login flow. Public environment variables must never contain secrets.

## Worker enrollment

Install this source in a worker's virtual environment, or build and serve its wheel from the controller's configured `WORKER_RELEASE_DIR`. The download endpoint returns 404 until an actual wheel exists. Create a pool from the dashboard, then:

```bash
lattice connect --server https://api.example.com --pool-name development --state-dir ~/.lattice/pools/development
```

The domain is a placeholder. Supply the generated join code privately when prompted. Workers require their own registry pull access. Keep worker state across restarts; use separate state for separate enrollments. See [Windows setup](docs/windows-worker.md).

## Deploy and inspect

Create a Box that fits entirely on an eligible worker. For failover, reserve a distinct compatible standby. Submit a public repository/branch and optional `application_config`. A repository can provide `lattice.json` with `start_command`, `internal_port`, `readiness_path` and `environment_variables`.

The controller clones, builds, publishes and records an immutable image digest, then dispatches execution. A running container is insufficient: verified port bindings and HTTP readiness must pass before the route is enabled. Review deployment status and logs for the failed stage. `/apps/<deployment-id>/` is the default path route. Optional `APP_DOMAIN` requires wildcard DNS, certificates, tunnel routing and allowed hosts.

## Owner controls

```bash
lattice status
lattice pause
lattice resume
lattice disconnect
```

Use the same state directory for owner controls when one was supplied at enrollment. Disconnect acknowledgment does not mean recovery has finished. Local data volumes are not replicated. Avoid broad Docker prune or state deletion as troubleshooting.
