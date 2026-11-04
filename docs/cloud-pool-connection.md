# Connecting a remote worker pool

Provision your own HTTPS controller origin and set `PUBLIC_BASE_URL`, `ALLOWED_HOSTS` and the dashboard's `NEXT_PUBLIC_WORKER_SERVER` accordingly. A tunnel can expose the loopback controller without opening inbound laptop ports. Configure it separately from Lattice.

Create a pool in the authenticated dashboard. Install Lattice and Docker on each worker. Run `lattice connect --server https://api.example.com --pool-name development --state-dir ~/.lattice/pools/development`, replacing the example domain with your origin. Enter the short-lived join code privately. The worker opens authenticated outbound control and application relay connections.

Configure private image pull access on each worker before submitting a deployment. Check both channels, a fresh snapshot and nonzero available capacity. A pool groups eligible machines; it does not sum them into a single execution machine. Preserve identity/state on reconnect and use fresh state for a new enrollment.
