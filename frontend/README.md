# Lattice frontend

Next.js 14 App Router dashboard for the existing Control Plane. The original
Lattice logo, assets and animated loader are preserved. Framer Motion adds
160 ms route/step entry and 200 ms dialog transitions, using transform/opacity
with reduced-motion support. Tables and live readings do not slide around.

## Run locally

Use Node.js 20+ (verification used Node 24) and pnpm. From `frontend/`:

```bash
pnpm install --frozen-lockfile
cp .env.example .env.local
pnpm dev
```

Open `http://localhost:3000`. Set server-only `CONTROL_PLANE_URL` to the existing
controller origin (local `http://127.0.0.1:8000` or public
`https://api.example.com`). Set `NEXT_PUBLIC_WORKER_SERVER` to the public
origin spare laptops should connect to. Restart Next.js after configuration changes.
Do not replace the backend's private `.env`, copy database/publisher secrets into
the frontend, or set `NEXT_PUBLIC_ADMIN_TOKEN`.

Sign in with the controller's existing management bearer token from your local
private configuration. The protected pool endpoint verifies it before a session
opens. The token is stored only in this browser tab's session storage; it is not
compiled into JavaScript or saved in local storage. Sign out clears operator
data/cache. Display name/workspace are local preferences, not backend accounts.
An explicit empty preview is available without authentication; it cannot create
resources or manufacture live data/success.

Browser requests use same-origin `/api/control/*`. A restricted Next.js handler
forwards permitted operations to the configured controller, preserves backend
status codes and avoids caching/redirecting credentials. No backend CORS or
authentication bypass is required. The frontend is not automatically published
through the existing backend Cloudflare tunnel by this change.

## Connected workflows

- Pools: real list/create/status/rotation endpoints and server-confirmed IDs.
  Codes are shown only after create/rotate and retained in tab memory. Existing
  codes cannot be recovered from the server's HMAC hash. Rotation is confirmed
  explicitly; it does not revoke existing worker credentials.
- Joining: real `lattice connect --server ... --pool-name ...` syntax. The default
  command prompts for the code; including it in the copied command is optional.
  Install instructions use the actual controller-served 0.3.2 Python wheel;
  no Winget/curl installer or worker service Docker image is fabricated.
- Workers: pool-scoped status, channels, capacity and container counts refresh
  from authenticated snapshots. Admin draining uses the existing disconnect API
  with confirmation. Worker-local pause/resume remains in the owner CLI.
- Boxes: select a real pool; the dashboard preserves its specified two-connected-
  worker minimum, sends `pool_id`, and validates that the full resource request
  fits on a primary and optionally a standby. The controller remains authoritative
  for reservation accounting, placement and admission. Storage is local/monitored.
- Deployment: public GitHub repository/branch, available Box, JSON startup
  arguments, runtime, internal port, relative readiness path and environment map.
  Backend-confirmed IDs drive navigation, status and stored log polling. Stop and
  redeploy require confirmation. A pending stop is not presented as completed.
- App links: only the current backend `running` status with an actual public URL
  enables access. No frontend-origin URL is invented. Redeployment produces a
  new deployment identity/URL according to the backend contract.
- Projects: group actual deployment records by repository. A failed/latest
  record is never substituted for a running production deployment.

See [API mapping and remaining limits](MISSING_ENDPOINTS.md) and
[verification evidence](../docs/frontend-integration.md).

## Checks

```bash
pnpm typecheck
pnpm test
pnpm format:check
pnpm build
```

The 46 focused tests cover operator rejection, API/error transport, pool scoping,
enrollment code handling, payload validation, URL gating and truthful metrics.
They mock HTTP boundaries only in tests. `tests/backend_fixture.py` is an isolated
browser-validation server, not a backend replacement or a real deployment demo.
Use its explicit fixture token only for local UI testing; no cloud writes are made.

Browser checks cover pool/Box/deployment forms and keyboard dialogs with fixture
resources. Separate real-controller verification exercised read-only endpoints
through the Next.js proxy. The existing running Docker/Cloudflare services are
not restarted, and no new real application is deployed by this frontend change.

For the current cloud-pool trial and short safe diagnostics, see [cloud connection recovery](../docs/cloud-pool-connection.md). Pool pages now copy platform-specific executable paths and separate state directories per pool.
