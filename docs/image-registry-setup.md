# Container registry setup

A Git repository stores source and history. A container registry stores built images. GHCR is GitHub's container registry at `ghcr.io`; creating a source repository does not automatically publish an application image.

Configure the controller with `REGISTRY_URL=ghcr.io/siddharthjha123` and private publisher credentials through its ignored environment file. It builds `lattice-app-<deployment-id>:build`, pushes it, validates the returned SHA-256 digest and persists a `repository@sha256:...` reference.

Workers must independently authenticate Docker with credentials allowed to read the package. Grant only required package permissions and use `docker login ghcr.io --username <account> --password-stdin` through a private input source. Do not put a token in a command argument, README or copied enrollment command. The controller's write credential is not distributed to workers.

After configuration, verify a push and a worker pull by exact digest using a non-sensitive test image. Check registry permissions and architecture independently. An unauthorized pull can appear as a worker startup timeout; inspect the worker's safe diagnostics. Never make a private package public as an implicit troubleshooting step.

See [GitHub's current Container registry documentation](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry) for supported credentials and scopes. The local Compose registry is development-only and its loopback binding is not reachable from a remote laptop.
