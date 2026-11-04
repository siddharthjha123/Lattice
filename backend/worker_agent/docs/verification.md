# Worker verification

Run `python -m pytest backend/worker_agent/tests` for isolated checks of configuration, state, admission, telemetry, transport, security, ownership, journal replay and shutdown. Tests use fakes where explicitly scoped; they are not evidence of a live deployment.

Set `LATTICE_RUN_DOCKER_TESTS=1` for real Docker integration. This requires a compatible Linux-container daemon and access to the pinned fixture image. The suite creates owned resources and tests real execution, inspection, limits and local lifecycle controls.

Native Windows worker behavior must be validated with Docker Desktop on the intended machine. POSIX full-stack tests do not prove Windows support. See the root verification guide for broader integration prerequisites.
