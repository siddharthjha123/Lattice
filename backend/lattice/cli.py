"""Pool enrollment, local worker controls and authenticated operator commands."""

import argparse
import asyncio
import getpass
import json
import secrets
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

DEFAULT_SERVER = "http://127.0.0.1:8000"
DEFAULT_STATE = Path.home() / ".lattice/worker"


class CLIError(ValueError):
    """An operator-facing error containing only deliberately safe text."""


class ControllerRequestError(RuntimeError):
    """Status metadata only; never retain response bodies or credentials."""

    def __init__(self, status_code):
        super().__init__("Controller request failed")
        self.status_code = status_code


def deployment_application(args):
    try:
        parsed = urlsplit(args.github_url)
        valid = (
            parsed.scheme == "https"
            and parsed.hostname
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
            and len(parsed.path.strip("/").split("/")) == 2
        )
    except ValueError:
        valid = False
    if not valid:
        raise CLIError(
            "Use a plain HTTPS repository URL with owner/repository; copy the command from the code block without Markdown link formatting or credentials"
        )
    application = {"internal_port": args.port, "readiness_path": "/"}
    if args.start_command:
        try:
            start = json.loads(args.start_command)
        except json.JSONDecodeError:
            raise CLIError(
                '--start-command must be a JSON array, for example \'["gunicorn","app:app","--bind","0.0.0.0:8000"]\''
            ) from None
        if (
            not isinstance(start, list)
            or not start
            or any(
                not isinstance(part, str) or not part or "\x00" in part
                for part in start
            )
        ):
            raise CLIError(
                "--start-command must be a nonempty JSON array of nonempty strings without null characters"
            )
        application["start_command"] = start
    return application


def server_url(value):
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or parsed.scheme == "http"
        and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
    ):
        raise CLIError(
            "Use an HTTPS controller origin; HTTP is permitted only on loopback"
        )
    return value.rstrip("/")


def request(client, method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    if response.status_code == 204:
        return {"deleted": True}
    if response.status_code >= 400:
        detail = (
            response.json().get("detail", "Request rejected")
            if "application/json" in response.headers.get("content-type", "")
            else "Controller request rejected"
        )
        # Server validation errors contain no input values; never dump raw bodies.
        print(
            f"Controller returned HTTP {response.status_code}: {detail}",
            file=sys.stderr,
        )
        raise ControllerRequestError(response.status_code)
    return response.json()


def admin_client(args):
    from control_plane.environment import load_settings_file

    try:
        config = load_settings_file(args.env_file.expanduser())
    except (OSError, ValueError):
        raise CLIError(
            "Cannot load the private --env-file; check its path, owner-only permissions and configuration values"
        ) from None
    if len(config.ADMIN_TOKEN.get_secret_value()) < 32:
        raise CLIError("Private operator configuration needs ADMIN_TOKEN")
    server = server_url(args.server or config.PUBLIC_BASE_URL)
    return httpx.Client(
        base_url=server,
        headers={"Authorization": "Bearer " + config.ADMIN_TOKEN.get_secret_value()},
        timeout=30,
        trust_env=False,
        follow_redirects=False,
    )


def find_pool(client, name):
    pool = next(
        (p for p in request(client, "GET", "/api/pools") if p["name"] == name), None
    )
    if pool is None:
        raise CLIError("Pool does not exist; create it first")
    return pool


def connect_worker(args):
    from worker_agent.config import Settings
    from worker_agent.docker_runtime.manager import DockerManager
    from worker_agent.main import main as worker_main
    from worker_agent.security.policy import open_local_docker
    from worker_agent.state import StateDirectory
    from worker_agent.telemetry.system_monitor import SystemMonitor

    state = StateDirectory(args.state_dir)
    state.prepare()
    server = server_url(args.server)
    worker_id = state.identity()
    config_path = state.path / "worker.json"
    with state.lock("enrollment.lock"):
        try:
            saved = state.read_json("connection.json")
        except FileNotFoundError:
            saved = None
        if saved is not None:
            if saved["server"] != server or saved["pool_name"] != args.pool_name:
                raise CLIError(
                    "State directory belongs to another server/pool; use a different --state-dir"
                )
            enrolled = saved.get("enrolled", False)
            data = state.read_json("worker.json")
        else:
            token = "lattice_wk_" + secrets.token_urlsafe(32)
            data = {
                "control_plane_url": server,
                "worker_id": worker_id,
                "worker_token": token,
                "state_dir": str(state.path),
                "application_relay": True,
                "max_ram_gb": args.max_ram_gb,
                "max_cpu_cores": args.max_cpu_cores,
                "max_storage_gb": args.max_storage_gb,
                "max_containers": args.max_containers,
                "stop_on_disconnect": True,
            }
            state.write_json("worker.json", data)
            state.write_json(
                "connection.json",
                {"server": server, "pool_name": args.pool_name, "enrolled": False},
            )
            enrolled = False
        config = Settings(**data)
        if not enrolled:
            code = args.pool_code or getpass.getpass("Pool join code: ")
            docker = open_local_docker(config)
            runtime = DockerManager(
                config, worker_id, docker, SystemMonitor(state.path)
            )
            try:
                runtime.initialize()
                snapshot, _ = runtime.telemetry()
                fields = {
                    k: v
                    for k, v in snapshot.model_dump(mode="json").items()
                    if k not in {"status", "last_heartbeat", "active_container_count"}
                }
                with httpx.Client(
                    base_url=server, timeout=30, trust_env=False, follow_redirects=False
                ) as client:
                    enrollment = request(
                        client,
                        "POST",
                        "/api/pools/join",
                        json={
                            "pool_name": args.pool_name,
                            "pool_code": code,
                            "worker_token": data["worker_token"],
                            "worker": fields,
                        },
                    )
            finally:
                runtime.close()
            state.write_json(
                "connection.json",
                {
                    "server": server,
                    "pool_name": args.pool_name,
                    "pool_id": enrollment["pool_id"],
                    "enrolled": True,
                },
            )
    print(
        f"Worker {worker_id} enrolled in {args.pool_name}. Keep this terminal open; Ctrl-C drains/disconnects.",
        flush=True,
    )
    return worker_main(
        ["run", "--config", str(config_path), "--state-dir", str(state.path)]
    )


def local_control(args):
    from worker_agent.communication.control import send_control
    from worker_agent.state import StateDirectory

    state = StateDirectory(args.state_dir)
    try:
        result = asyncio.run(send_control(state, args.command))
    except (FileNotFoundError, ConnectionRefusedError):
        raise CLIError(
            "No running worker control endpoint in this state directory. Keep the connect terminal open and use the same --state-dir for status/list/resume/disconnect."
        ) from None
    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


def monitor(args):
    with admin_client(args) as client:
        pool = None
        failures = 0
        while True:
            try:
                if pool is None:
                    pool = find_pool(client, args.pool_name)
                status = request(client, "GET", f"/api/pools/{pool['pool_id']}/status")
            except (ControllerRequestError, httpx.TransportError) as error:
                if args.once or (
                    isinstance(error, ControllerRequestError)
                    and error.status_code not in {500, 502, 503, 504}
                ):
                    raise
                failures += 1
                delay = min(30, max(1, args.interval) * 2 ** min(failures - 1, 5))
                reason = (
                    f"HTTP {error.status_code}"
                    if isinstance(error, ControllerRequestError)
                    else "network/timeout"
                )
                if sys.stdout.isatty():
                    print("\033[2J\033[H", end="")
                print(
                    f"{datetime.now(UTC).isoformat(timespec='seconds')}  Pool: {args.pool_name}\n"
                    f"Monitoring interrupted ({reason}). Current worker availability is unknown; "
                    f"retrying in {delay:g}s. Ctrl-C stops monitoring.",
                    flush=True,
                )
                time.sleep(delay)
                continue
            if sys.stdout.isatty():
                print("\033[2J\033[H", end="")
            if failures:
                print(
                    "Controller reachable again; showing a fresh snapshot.", flush=True
                )
            failures = 0
            print(
                f"{datetime.now(UTC).isoformat(timespec='seconds')}  Pool: {pool['name']}",
                flush=True,
            )
            if not status["workers"]:
                print("No laptops joined yet.")
            for worker in status["workers"]:
                print(
                    f"{worker['worker_id']}  {worker['hostname']}  {worker['status']}  control={worker['control_connected']} relay={worker['application_relay_connected']}  containers={worker['active_container_count']}  free_RAM={worker['available_ram_gb']:.2f}GiB  arch={worker['architecture']}"
                )
                for container in worker["running_container_ids"]:
                    print("  container: " + container)
            for deployment in status["deployments"]:
                print(
                    f"Deployment {deployment['deployment_id']}  {deployment['status']}  {deployment['public_url'] or ''}"
                )
                for container in deployment["containers"]:
                    print(
                        f"  {container['worker_id']}  {container['container_id'] or 'waiting for container'}  {container['status']}"
                    )
                if deployment["failure_message"]:
                    print("  " + deployment["failure_message"])
            if args.once:
                return 0
            time.sleep(args.interval)


def deploy(args):
    application = deployment_application(args)
    with admin_client(args) as client:
        pool = find_pool(client, args.pool_name)
        status = request(client, "GET", f"/api/pools/{pool['pool_id']}/status")
        workers = [
            w["worker_id"]
            for w in status["workers"]
            if w["status"] == "online"
            and w["control_connected"]
            and w["application_relay_connected"]
        ]
        if not workers:
            raise CLIError(
                "No online pool workers with an application relay; connect a laptop first"
            )
        if args.failover and len(workers) < 2:
            raise CLIError("Failover needs two online pool workers")
        box = request(
            client,
            "POST",
            "/api/boxes",
            json={
                "name": args.name,
                "pool_id": pool["pool_id"],
                "eligible_worker_ids": workers,
                "ram_limit_gb": args.ram_gb,
                "cpu_limit_cores": args.cpu_cores,
                "storage_limit_gb": args.storage_gb,
                "failover_enabled": args.failover,
            },
        )
        print("Box: " + box["box_id"], flush=True)
        try:
            deployment = request(
                client,
                "POST",
                "/api/deployments",
                json={
                    "box_id": box["box_id"],
                    "repository_url": args.github_url,
                    "branch": args.branch,
                    "application_type": args.app_type,
                    "application_config": application,
                },
            )
        except Exception:
            print(
                "Deployment submission failed; the created Box remains reserved. Delete it explicitly after reviewing its state: "
                + box["box_id"],
                file=sys.stderr,
            )
            raise
        identity = deployment["deployment_id"]
        print("Deployment: " + identity, flush=True)
        if args.no_wait:
            return 0
        deadline = time.monotonic() + args.timeout
        last = None
        while time.monotonic() < deadline:
            observed = request(client, "GET", f"/api/deployments/{identity}/status")
            if observed["status"] != last:
                print("Status: " + observed["status"], flush=True)
                last = observed["status"]
            if last == "running":
                print("Public URL: " + observed["public_url"], flush=True)
                return 0
            if last in {"failed", "stopped"}:
                print(
                    observed.get("failure_message") or "Deployment stopped",
                    file=sys.stderr,
                )
                return 1
            time.sleep(2)
        print(
            "Still pending. Use lattice logs --deployment-id "
            + identity
            + " --env-file <private-env-file>",
            file=sys.stderr,
        )
        return 1


def registry_login(args):
    from worker_agent.security.private_files import private_reader

    with private_reader(args.token_file.expanduser()) as stream:
        token = stream.read(4096).strip()
    if not token or "\n" in token:
        raise CLIError("Expected one plain-text read-only registry token")
    try:
        result = subprocess.run(
            [
                "docker",
                "login",
                "ghcr.io",
                "--username",
                args.username,
                "--password-stdin",
            ],
            input=token,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
    except FileNotFoundError:
        raise CLIError(
            "Docker CLI is unavailable; start Docker Desktop and check PATH"
        ) from None
    except subprocess.TimeoutExpired:
        raise CLIError(
            "Docker registry login timed out; check network access to ghcr.io"
        ) from None
    if result.returncode:
        # Classify only: Docker/credential-helper stderr can contain private data.
        detail = ((result.stderr or "") + " " + (result.stdout or "")).lower()
        if "error storing credentials" in detail or "keychain" in detail:
            message = "Docker could not save registry credentials; unlock the local credential store and check Docker Desktop's credential helper"
        elif "unauthorized" in detail or "denied" in detail:
            message = "GHCR rejected the credentials; verify the token owner, expiry and classic read:packages permission"
        elif "no such host" in detail or "lookup " in detail:
            message = "Docker cannot resolve the registry hostname; check DNS and network access"
        else:
            message = "Docker registry login failed; run docker login ghcr.io with --password-stdin and the same private token file to see Docker's diagnostic"
        raise CLIError(message)
    print(
        "Registry credentials saved by Docker locally. No publishing token is supplied by the controller."
    )
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="lattice", description="Lattice worker and operator CLI"
    )
    from importlib.metadata import version

    parser.add_argument(
        "--version", action="version", version="%(prog)s " + version("lattice")
    )
    commands = parser.add_subparsers(dest="command", required=True)
    connection = commands.add_parser("connect")
    connection.add_argument("--server", default=DEFAULT_SERVER)
    connection.add_argument("--pool-name", required=True)
    connection.add_argument(
        "--pool-code",
        help="Omit to enter privately; command arguments may be visible in process lists",
    )
    connection.add_argument("--state-dir", type=Path, default=DEFAULT_STATE)
    connection.add_argument("--max-ram-gb", type=float, default=2)
    connection.add_argument("--max-cpu-cores", type=float, default=2)
    connection.add_argument("--max-storage-gb", type=float, default=8)
    connection.add_argument("--max-containers", type=int, default=4)
    for name in ("status", "list", "pause", "resume", "stop", "disconnect"):
        command = commands.add_parser(name)
        command.add_argument("--state-dir", type=Path, default=DEFAULT_STATE)
    diagnostic = commands.add_parser(
        "doctor",
        help="Read-only safe installation, pool-state, Docker and public-health diagnostics",
    )
    diagnostic.add_argument("--server", default=DEFAULT_SERVER)
    diagnostic.add_argument("--state-dir", type=Path)
    protect = commands.add_parser("protect-file")
    protect.add_argument("--path", type=Path, required=True)
    login = commands.add_parser("registry-login")
    login.add_argument("--username", required=True)
    login.add_argument("--token-file", type=Path, required=True)
    for name in (
        "pool-create",
        "pool-rotate",
        "monitor",
        "deploy",
        "logs",
        "deployment-status",
        "deployment-stop",
        "box-delete",
    ):
        command = commands.add_parser(name)
        command.add_argument("--env-file", type=Path, required=True)
        command.add_argument("--server")
        if name in {"pool-create", "pool-rotate", "monitor", "deploy"}:
            command.add_argument("--pool-name", required=True)
        if name == "pool-create":
            command.add_argument("--expires-hours", type=int, default=24)
            command.add_argument("--max-joins", type=int, default=10)
        if name == "monitor":
            command.add_argument("--interval", type=float, default=2)
            command.add_argument("--once", action="store_true")
        if name in {"logs", "deployment-status", "deployment-stop"}:
            command.add_argument("--deployment-id", required=True)
        if name == "box-delete":
            command.add_argument("--box-id", required=True)
        if name == "deploy":
            command.add_argument("--github-url", required=True)
            command.add_argument("--name", default="milestone-demo")
            command.add_argument("--branch", default="main")
            command.add_argument(
                "--app-type", choices=["python", "node"], default="python"
            )
            command.add_argument(
                "--start-command", help="JSON array of executable and arguments"
            )
            command.add_argument("--port", type=int, default=8000)
            command.add_argument("--ram-gb", type=float, default=0.5)
            command.add_argument("--cpu-cores", type=float, default=0.5)
            command.add_argument("--storage-gb", type=float, default=1)
            command.add_argument("--failover", action="store_true")
            command.add_argument("--no-wait", action="store_true")
            command.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            from lattice.diagnostics import doctor

            return doctor(args)
        if args.command == "connect":
            return connect_worker(args)
        if args.command in {"status", "list", "pause", "resume", "stop", "disconnect"}:
            return local_control(args)
        if args.command == "protect-file":
            from worker_agent.security.private_files import make_private

            if not args.path.expanduser().is_file():
                raise CLIError("Choose an existing regular token file")
            make_private(args.path.expanduser())
            print("File restricted to its owner (and SYSTEM on Windows).")
            return 0
        if args.command == "registry-login":
            return registry_login(args)
        if args.command == "monitor":
            if not 0.5 <= args.interval <= 60:
                raise CLIError("Monitor interval must be between 0.5 and 60 seconds")
            return monitor(args)
        if args.command == "deploy":
            return deploy(args)
        with admin_client(args) as client:
            if args.command == "pool-create":
                result = request(
                    client,
                    "POST",
                    "/api/pools",
                    json={
                        "name": args.pool_name,
                        "expires_hours": args.expires_hours,
                        "max_joins": args.max_joins,
                    },
                )
            elif args.command == "pool-rotate":
                pool = find_pool(client, args.pool_name)
                result = request(
                    client, "POST", f"/api/pools/{pool['pool_id']}/rotate-code"
                )
            elif args.command == "box-delete":
                result = request(client, "DELETE", f"/api/boxes/{args.box_id}")
            else:
                suffix = {
                    "logs": "/logs",
                    "deployment-status": "/status",
                    "deployment-stop": "/stop",
                }[args.command]
                result = request(
                    client,
                    "POST" if args.command == "deployment-stop" else "GET",
                    f"/api/deployments/{args.deployment_id}" + suffix,
                )
            print(json.dumps(result, indent=2))
        return 0
    except KeyboardInterrupt:
        return 130
    except CLIError as error:
        print("Lattice stopped: " + str(error), file=sys.stderr)
        return 2
    except Exception as error:  # noqa: BLE001 -- no credential-bearing exception input at the CLI boundary
        print(
            "Lattice stopped: "
            + type(error).__name__
            + ". Check server availability, Docker, private configuration and the preceding safe error message.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
