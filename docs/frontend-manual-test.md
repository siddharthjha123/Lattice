# Dashboard manual verification

Start the intended controller and frontend with private configuration. Verify login failure/success, health errors, pool creation/code rotation, generated platform commands and empty states. Do not expose an admin token through public environment variables.

Enroll a real worker and verify fresh capacity and pool scoping. Create a Box that fits, submit a trusted test repository, follow each build/start/readiness stage and open the resulting HTTP URL. Confirm a failed deployment has an actionable safe error and does not receive a healthy route.

Check deployment logs/history, intentional stop/redeploy, worker pause/resume/drain and guarded deletion. For failover, use compatible physical machines, verify old execution is stopped/fenced before standby activation, and treat local application data separately. Test path-prefix links/cookies as well as optional app-host routing if configured.

Mocked frontend tests and tab-local charts do not prove remote execution or durable metrics history. Document the actual environment and observed results without claiming unsupported infrastructure health.
