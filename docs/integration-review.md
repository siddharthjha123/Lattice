# Verification scope

The default Python suite covers shared contracts, API authorization, database adapters, scheduling, admission, lifecycle, command replay, owner controls and relay boundaries. Run `python -m pytest` from the repository root with its Python 3.12 dependencies installed.

Real execution is opt-in. `LATTICE_RUN_DOCKER_TESTS=1` enables worker Docker integration. `LATTICE_RUN_INTEGRATION_TESTS=1` enables the full-stack suite, which needs a POSIX host, Docker, Git, available ports and permission to run isolated PostgreSQL/registry containers. Inspect each test's prerequisites before running. The FastAPI fixture can download Linux wheels; `LATTICE_FASTAPI_WHEEL_DIR` can point to prepared wheels.

Two logical workers on one Docker Engine exercise protocol and lifecycle behavior but do not establish physical host independence. Verify remote registry pull, NAT traversal, architecture compatibility, intentional handoff and abrupt failure on separate machines before relying on recovery.

Use `pnpm typecheck`, `pnpm test` and `pnpm build` in `frontend/`. A build or mocked API test does not establish a successful real deployment. This document makes no assertion of current test counts or live infrastructure health.
