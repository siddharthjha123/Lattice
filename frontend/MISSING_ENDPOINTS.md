# Frontend API mapping and remaining contract limits

The dashboard consumes the current backend rather than inventing new backend
schemas. Its same-origin Next.js transport forwards existing bearer authorization;
it does not grant new privileges or embed the controller's admin token.

| Workflow                      | Existing backend                               | Frontend behavior                                      |
| ----------------------------- | ---------------------------------------------- | ------------------------------------------------------ |
| Operator verification         | `GET /api/pools`                               | Verify bearer before opening a tab session             |
| Health                        | `GET /health`                                  | Explicit reachable/unavailable state                   |
| Pool list/create              | `GET`, `POST /api/pools`                       | Real records and returned code; errors stay errors     |
| Pool worker status            | `GET /api/pools/{id}/status`                   | Actual membership and both live channel flags          |
| Code rotation                 | `POST /api/pools/{id}/rotate-code`             | Explicit confirmation and new server-issued code       |
| Worker reads                  | `GET /api/workers`, `GET /api/workers/{id}`    | Authenticated snapshots and real capacity              |
| Worker drain                  | `POST /api/workers/{id}/disconnect`            | Existing admin-authorized drain with confirmation      |
| Box list/create/detail/delete | `/api/boxes`, `/api/boxes/{id}`                | Existing payload plus pool_id; no separate scheduler   |
| Deployment create/read        | `/api/deployments`, `/api/deployments/{id}`    | Actual repository/configuration and IDs                |
| Deployment status             | `GET /api/deployments/{id}/status`             | queued/building/deploying/running/failed/stopped       |
| Stored diagnostics            | `GET /api/deployments/{id}/logs`               | Bounded polling with search/copy/download              |
| Deployment stop/redeploy      | `POST /api/deployments/{id}/stop`, `/redeploy` | Confirmed actions; pending stop remains pending        |
| Application URL               | `public_url` in current running status         | Use verbatim after validating HTTP(S); no invented URL |

## Deliberate frontend adapters

- **Box pool filtering:** Box response models predate pool_id. The server enforces
  that every eligible worker belongs to the selected pool. The UI scopes listed
  Boxes by that complete eligible-worker membership; creation sends real pool_id.
- **Repository inspection:** no controller inspection endpoint exists. An isolated
  [GitHub adapter](src/lib/api/repoInspectionAdapter.ts) reads real repository,
  branch/commit and configuration responses. It never invents branches, commits,
  timestamps or Dockerfiles on errors. Suggestions are inferred from actual
  files; the deployment builder performs final validation. Explicit manual
  configuration remains available when GitHub is offline or rate limited.
- **Projects:** no project persistence API exists. The
  [project adapter](src/lib/api/projectsAdapter.ts) groups actual deployment
  records without fabricating production success.

## Not supplied by the backend

- **Browser events:** the worker sockets are reserved for authenticated workers.
  The frontend uses bounded query polling; it does not attach a browser to worker
  WSS or pretend a live SSE endpoint exists.
- **Extra metrics:** worker response contracts do not expose CPU/memory utilization,
  battery percentage, numeric health score or OS name. Missing fields show
  unavailable. Available CPU/RAM/storage are capacity values, not utilization.
  History contains only new received heartbeat snapshots in the current tab;
  no points are appended for repeated/stale/offline observations.
- **Commit metadata in deployment records:** the database stores a build commit,
  but public deployment responses do not expose it. GitHub inspection shows the
  queried branch's real commit; it is not asserted to be the deployed commit.
- **Accounts:** current auth is an operator bearer credential, not signup/password
  accounts or tenant RBAC. Display preferences do not create backend identities.
- **Unsupported installation/build features:** no official worker Docker image,
  Winget installer, GPU allocation, arbitrary build-command field, replicated
  application storage, Box-spanning workload, or application WebSocket/SSE relay
  is claimed. Existing backend CPU/RAM/storage/lease limits remain unchanged.

The dashboard's two-worker Box minimum follows the supplied frontend brief.
The existing CLI/backend can support a single worker with failover disabled;
this frontend policy does not change that backend contract.
