# Backend operations

Follow the root walkthrough for installation and private configuration. `lattice --help` lists the current commands; use each subcommand's `--help` for exact flags.

The operator can create/monitor pools, rotate enrollment codes and submit deployments. A worker enrolls with `lattice connect --server <reachable-origin> --pool-name development` and a private join code. Optional contribution limits bound CPU, RAM, storage and container count. Registry access must be provisioned independently.

Use the dashboard or deployment status/log APIs to distinguish cloning, building, publication, worker startup and HTTP readiness failures. Reinstall or rebuild the wheel after source changes; a running process does not automatically load a new checkout. No configured public endpoint or completed physical-machine trial is implied by this guide.
