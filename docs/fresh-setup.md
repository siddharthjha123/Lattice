# Fresh Lattice setup

This source uses the `lattice` distribution, `lattice.json` application configuration, `LATTICE_*` integration-test switches, and `io.lattice.*` Docker ownership labels. Build downloadable wheels from this source; old wheel filenames are not compatible with the renamed download routes. No wheel is bundled by this repository.

The default worker state is `~/.local/share/lattice/worker`. Use a new explicit state directory for a new controller/pool and enroll with a new identity. Never point a fresh setup at a running worker's state or remove live state to bypass a lock.

Docker resources bearing older ownership labels are not adopted by the renamed runtime. Stop and inspect them using the installation that created them before starting a fresh runtime. Existing application data is not migrated or deleted by this source change. Failover decision identities also use the Lattice namespace.

The local Compose database user/database is `lattice`; use matching credentials in `.env`. Existing database volumes are not reinitialized by changing environment variables. Use a fresh development volume or plan an explicit migration; do not delete a volume containing data you need.

No external domain, registry, database, DNS record, tunnel, running worker, or GitHub repository content is changed by these local source changes. Configure your own origins and credentials before running. The controller requires a POSIX environment; Windows workers use Docker Desktop in Linux-container mode.
