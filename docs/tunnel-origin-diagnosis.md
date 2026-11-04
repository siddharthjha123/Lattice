# Tunnel and origin diagnosis

Trace each hop independently: client DNS/TLS, Cloudflare edge, tunnel connector, loopback FastAPI origin, database, worker control channel, worker application relay, then container HTTP binding.

A healthy tunnel process does not prove the application is healthy. First request the local `/health` endpoint and verify database reachability. Then request the configured public `/health`. A 502 typically needs origin/connector investigation; an authorized API returning 401 needs credential investigation. Never print bearer values in diagnostic output.

Configure the public hostname to forward to the intended local port (default 8000). Match `PUBLIC_BASE_URL` and `ALLOWED_HOSTS`. Preserve TLS verification for external PostgreSQL. Optional direct DNS/HTTPS DNS paths do not justify disabling certificate validation or hard-coding database IPs.

Worker connection health and application readiness are separate. Check the current worker session/lease, relay presence, image pull access and verified container binding. The HTTP relay cannot forward application WebSocket upgrades. Wildcard app hosts require their own DNS/tunnel/certificate configuration.
