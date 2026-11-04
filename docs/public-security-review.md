# Security and operational model

Management requests use an operator bearer. Workers use separate per-machine credentials stored as HMAC-SHA256 hashes in PostgreSQL. Pool join codes are scoped enrollment capabilities with expiry and usage limits; they do not authorize management. Protect the stable hashing secret and private state files. Do not log environment values or registry tokens.

The gateway binds each command result/event to the worker, current session and ownership context. Leases bound execution permission. An independent watchdog stops owned workloads after expiry while it and Docker remain operational. Controller fencing waits for confirmed stop or the configured lease/grace boundary before replacement. This is not external power fencing or a multi-controller consensus system.

Runtime containers use a non-root UID, CPU/RAM/PID limits, dropped capabilities, no-new-privileges, a read-only root and isolated networks. Writable named volumes are local. Storage is periodically measured and over-budget workloads are stopped; this is not a portable hard quota. Docker shares a kernel and is not a complete hostile-tenant security boundary.

Builds use the controller's local Docker daemon and require trusted repositories/Dockerfiles. Image digests prevent mutable-tag drift but do not prove image safety. Configure separate registry write credentials on the builder and read credentials on workers.

The relay limits HTTP bodies and headers, validates targets and strips hop-by-hop transport headers. Path-prefix routing has limited cookie/redirect adaptation but does not rewrite arbitrary HTML, JavaScript or absolute URLs. Shared path routes do not provide browser-origin isolation. App WebSocket upgrades and unlimited streaming are unsupported.

One controller process owns the PostgreSQL advisory lock. Local volumes are not replicated; failover does not preserve access to primary-local data. Logs are bounded best-effort delivery. No availability SLA, multi-tenant RBAC, automatic public DNS or automatic tunnel provisioning is claimed.
