# Worker integration

The worker uses `shared` Pydantic contracts and authenticates with a worker-specific token. The control channel binds worker identity, current socket/session and an execution lease. Snapshot publication must use the active lease.

The controller sends run, stop and inspect commands with stable request IDs. A local SQLite journal rejects changed payloads under an existing ID and returns recorded terminal results on replay. Docker ownership labels support reconciliation after an interrupted command.

The worker enforces final local admission even after scheduling. Host capacity, Docker capacity, owner budgets, running allocations and retained storage all matter. The orchestrator subtracts idle holds while avoiding double counting running allocations.

Container running status is separate from application readiness. The controller inspects bindings and performs an actual HTTP probe before routing. Pool enrollment can open a separate authenticated outbound application relay. That relay supports bounded HTTP, not application WebSocket upgrades.

The independent lease watchdog stops owned workloads after expiry while it and Docker remain operational. Preserve private state across normal restarts and coordinate fencing timing with the controller.
