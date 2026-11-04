# Frontend integration

The dashboard uses typed adapters for the control-plane APIs. A restricted Next.js `/api/control` proxy forwards supported operations to server-only `CONTROL_PLANE_URL`, preserves structured errors and disables caching. The operator bearer remains a session credential and must never be placed in public environment variables.

Pools, worker capacity, Box creation, deployment submission/status/logs and guarded deletion map to backend contracts. Repository inspection reads public source metadata and optional `lattice.json`; actual execution and readiness remain controller responsibilities.

`NEXT_PUBLIC_WORKER_SERVER` controls copied enrollment commands and wheel links. Configure a reachable origin and serve actual built wheels before advertising installation.

Use `pnpm typecheck`, `pnpm test` and `pnpm build` for local checks, then follow the manual verification guide against real configured services. Fixtures do not establish cloud writes or real container execution. See the frontend README and MISSING_ENDPOINTS.md for contract boundaries.
