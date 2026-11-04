# Worker capacity and connectivity

Capacity is allocatable CPU/RAM/storage/slots; utilization is observed activity. Do not treat low CPU utilization as a guaranteed free-core reservation. Docker Desktop executes inside a VM, so the daemon's resources and architecture constrain execution even if the host laptop has more capacity.

The worker considers owner budgets, daemon capacity, host free memory, existing containers and retained volumes. Unknown foreign allocations are handled conservatively. The scheduler subtracts idle reservations but must not subtract an allocation twice once execution is reflected in the snapshot. Always pass a complete ledger and active reservation IDs.

A worker can be enrolled yet offline, connected yet stale, or connected with no safe remaining capacity. Check current session, lease, fresh snapshot, drain/pause state and both control/application relay channels. A cold standby must fit the full workload and its image architecture on another worker identity. Separate identities on one host are not physical redundancy.

Use a distinct state directory for a new controller/pool. Reusing an identity from a different enrollment is rejected; deleting state while execution is live bypasses recovery information and is unsafe.
