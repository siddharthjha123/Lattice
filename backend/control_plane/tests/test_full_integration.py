"""Opt-in: real Git HTTP, PostgreSQL, registry, Control Plane and Docker workers.

LATTICE_RUN_INTEGRATION_TESTS=1 pytest backend/control_plane/tests/test_full_integration.py
Creates only uniquely labeled local resources and removes those in teardown.
Two logical workers share one Docker Engine; this does not validate two hosts.
"""

import asyncio
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
import uvicorn
from alembic import command
from docker.errors import ImageNotFound
from worker_agent.application import WorkerApplication
from worker_agent.communication.control import send_control
from worker_agent.communication.dispatcher import CommandDispatcher
from worker_agent.communication.journal import RequestJournal
from worker_agent.communication.lifecycle import ControlPlaneLifecycle
from worker_agent.config import Settings as WorkerSettings
from worker_agent.docker_runtime.manager import DockerManager
from worker_agent.security.policy import WORKER_LABEL, open_local_docker
from worker_agent.state import StateDirectory
from worker_agent.telemetry.system_monitor import SystemMonitor

from control_plane.config import Settings
from control_plane.database.init_db import init_db, migration_config
from control_plane.database.models import (
    Deployment,
    FailoverRecord,
    Replica,
    ResourceReservation,
)
from control_plane.database.session import Database
from control_plane.main import create_app
from control_plane.services.runtime import ServiceContext

pytestmark = pytest.mark.skipif(
    os.environ.get("LATTICE_RUN_INTEGRATION_TESTS") != "1",
    reason="Set LATTICE_RUN_INTEGRATION_TESTS=1 for full real-stack execution",
)
PYTHON = "public.ecr.aws/docker/library/python:3.12-alpine"
NODE = "public.ecr.aws/docker/library/node:22-alpine"


def git(*args, cwd=None):
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    ).stdout


@pytest.fixture
def git_server(tmp_path):
    root = tmp_path / "git"
    root.mkdir()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.backend()

        def do_POST(self):
            self.backend()

        def log_message(self, *args):
            pass

        def backend(self):
            path, _, query = self.path.partition("?")
            length = int(self.headers.get("Content-Length", "0"))
            env = os.environ | {
                "GIT_PROJECT_ROOT": str(root),
                "GIT_HTTP_EXPORT_ALL": "1",
                "PATH_INFO": path,
                "QUERY_STRING": query,
                "REQUEST_METHOD": self.command,
                "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                "CONTENT_LENGTH": str(length),
                "REMOTE_USER": "integration",
                "SERVER_PROTOCOL": "HTTP/1.1",
            }
            process = subprocess.run(
                ["git", "http-backend"],
                input=self.rfile.read(length),
                env=env,
                stdout=subprocess.PIPE,
                check=True,
            )
            header, body = process.stdout.split(b"\r\n\r\n", 1)
            headers = [line.decode().split(": ", 1) for line in header.split(b"\r\n")]
            status = next(
                (int(v.split()[0]) for k, v in headers if k.lower() == "status"), 200
            )
            self.send_response(status)
            for key, value in headers:
                if key.lower() != "status":
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def repository(name, files):
        source = tmp_path / name
        source.mkdir()
        git("init", "-b", "main", cwd=source)
        for filename, value in files.items():
            target = source / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(value, bytes):
                target.write_bytes(value)
            else:
                target.write_text(value)
        git("add", ".", cwd=source)
        git(
            "-c",
            "user.name=Integration Test",
            "-c",
            "user.email=integration@example.invalid",
            "commit",
            "-m",
            "test fixture",
            cwd=source,
        )
        git("clone", "--bare", str(source), str(root / (source.name + ".git")))
        return f"http://127.0.0.1:{server.server_port}/{source.name}.git"

    yield repository
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.fixture
def infrastructure(tmp_path):
    client = open_local_docker(type("Config", (), {"docker_timeout": 60})())
    label = {"lattice.integration": str(uuid4())}
    resources = []
    password = secrets.token_urlsafe(32)
    try:
        for image in [
            PYTHON,
            NODE,
            "public.ecr.aws/docker/library/postgres:17-alpine",
            "public.ecr.aws/docker/library/registry:2",
        ]:
            try:
                client.images.get(image)
            except ImageNotFound:
                client.images.pull(image)
        pg = client.containers.run(
            "public.ecr.aws/docker/library/postgres:17-alpine",
            detach=True,
            environment={
                "POSTGRES_USER": "lattice_test",
                "POSTGRES_DB": "lattice_test",
                "POSTGRES_PASSWORD": password,
            },
            ports={"5432/tcp": ("127.0.0.1", None)},
            labels=label,
            nano_cpus=250_000_000,
            mem_limit="256m",
        )
        resources.append(pg)
        registry_port = 35000 + secrets.randbelow(15000)
        registry = client.containers.run(
            "public.ecr.aws/docker/library/registry:2",
            detach=True,
            network_mode="host",
            environment={"REGISTRY_HTTP_ADDR": f"127.0.0.1:{registry_port}"},
            labels=label,
            nano_cpus=250_000_000,
            mem_limit="256m",
        )
        resources.append(registry)
        pg.reload()
        pgport = pg.attrs["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostPort"]
        regport = registry_port
        for _ in range(120):
            if (
                pg.exec_run(
                    ["pg_isready", "-h", "127.0.0.1", "-U", "lattice_test"]
                ).exit_code
                == 0
            ):
                break
            time.sleep(0.1)
        yield (
            f"postgresql+psycopg://lattice_test:{password}@127.0.0.1:{pgport}/lattice_test",
            f"127.0.0.1:{regport}",
            client,
        )
    finally:
        for container in resources:
            container.remove(force=True, v=True)
        client.close()


async def eventually(operation, predicate=lambda value: bool(value), timeout=60):
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        result = await operation()
        if predicate(result):
            return result
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(
                f"Condition did not become true; final value: {result}"
            )
        await asyncio.sleep(0.15)


@pytest.fixture
def short_path():
    with tempfile.TemporaryDirectory(prefix="lattice-it-", dir="/tmp") as directory:
        yield Path(directory)


@pytest.fixture
def framework_wheels(infrastructure, tmp_path):
    supplied = os.environ.get("LATTICE_FASTAPI_WHEEL_DIR")
    if supplied:
        directory = Path(supplied)
    else:
        directory = tmp_path / "framework-wheels"
        directory.mkdir()
        arch = infrastructure[2].info()["Architecture"]
        arch = {"arm64": "aarch64", "amd64": "x86_64"}.get(arch, arch)
        with (tmp_path / "wheel-download.log").open("wb") as output:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "download",
                    "--only-binary=:all:",
                    "--platform",
                    f"musllinux_1_2_{arch}",
                    "--platform",
                    f"musllinux_1_1_{arch}",
                    "--implementation",
                    "cp",
                    "--python-version",
                    "3.12",
                    "--abi",
                    "cp312",
                    "--dest",
                    str(directory),
                    "fastapi==0.115.12",
                    "uvicorn==0.34.2",
                    "pydantic==2.11.10",
                ],
                check=True,
                timeout=120,
                stdout=output,
                stderr=subprocess.STDOUT,
            )
    assert list(directory.glob("*.whl")), (
        "Provide Linux wheels or allow the pip download"
    )
    return directory


async def test_real_deploy_route_logs_reconnect_failover_redeploy_stop(
    infrastructure, git_server, tmp_path, short_path, framework_wheels
):
    database_url, registry, docker = infrastructure
    app_source = """from http.server import BaseHTTPRequestHandler,HTTPServer
import os
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200);self.end_headers();self.wfile.write(("python-real:"+self.path).encode())
 def do_POST(self):
  data=self.rfile.read(int(self.headers.get("Content-Length",0)))
  self.send_response(201);self.end_headers();self.wfile.write(data)
 def log_message(self,*args): print("request",self.path,flush=True)
print("real-python-started",flush=True)
HTTPServer(("0.0.0.0",int(os.environ["PORT"])),Handler).serve_forever()
"""
    python_url = git_server(
        "python-app",
        {
            "server.py": app_source,
            "lattice.json": json.dumps({"start_command": ["python", "server.py"]}),
        },
    )
    node_url = git_server(
        "node-app",
        {
            "package.json": json.dumps(
                {
                    "name": "integration",
                    "version": "1.0.0",
                    "scripts": {"start": "node server.js"},
                }
            ),
            "server.js": "const http=require('http');console.log('real-node-started');http.createServer((q,r)=>{r.end('node-real:'+q.url)}).listen(process.env.PORT,'0.0.0.0');",
        },
    )
    fastapi_files = {
        "main.py": 'from fastapi import FastAPI\napp=FastAPI()\n@app.get("/")\ndef root():return {"framework":"fastapi-real"}\n',
        "requirements.txt": "--no-index\n--find-links=./wheels\nfastapi==0.115.12\nuvicorn==0.34.2\npydantic==2.11.10\n",
    }
    fastapi_files.update(
        {
            "wheels/" + path.name: path.read_bytes()
            for path in framework_wheels.glob("*.whl")
        }
    )
    fastapi_url = git_server("fastapi-app", fastapi_files)
    bad_url = git_server(
        "bad-app",
        {
            "server.py": 'raise RuntimeError("intentional startup failure")',
            "Dockerfile": f'FROM {PYTHON}\nCMD ["/intentional-missing-executable"]\n',
            "lattice.json": json.dumps({"start_command": ["python", "server.py"]}),
        },
    )
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    admin = secrets.token_urlsafe(40)
    config = Settings(
        DATABASE_URL=database_url,
        ADMIN_TOKEN=admin,
        SECRET_KEY=secrets.token_urlsafe(40),
        REGISTRY_URL=registry,
        BUILD_DIR=tmp_path / "build",
        ALLOW_LOCAL_REPOSITORIES=True,
        PUBLIC_BASE_URL=base,
        PYTHON_BASE_IMAGE=PYTHON,
        NODE_BASE_IMAGE=NODE,
        MONITOR_INTERVAL=0.15,
        HEARTBEAT_TIMEOUT=1.5,
        LEASE_SECONDS=1,
        FENCE_GRACE_SECONDS=1.5,
        READINESS_TIMEOUT=15,
        COMMAND_TIMEOUT=15,
    )
    db = Database(database_url)
    init_db(db.engine)
    with db.engine.begin() as connection:
        command.check(migration_config(connection))
    ctx = ServiceContext(config, db)
    server = uvicorn.Server(
        uvicorn.Config(create_app(config, ctx), log_level="error", access_log=False)
    )
    server_task = asyncio.create_task(server.serve(sockets=[sock]))
    workers = []
    created_images = []
    http = httpx.AsyncClient(
        base_url=base,
        headers={"Authorization": "Bearer " + admin},
        timeout=30,
        trust_env=False,
    )

    async def request(method, path, **kwargs):
        response = await http.request(method, path, **kwargs)
        assert response.status_code < 400, (response.status_code, response.text)
        return response.json()

    async def status(identity):
        return await request("GET", f"/api/deployments/{identity}/status")

    async def running(identity):
        state = await eventually(
            lambda: status(identity),
            lambda v: v["status"] in {"running", "failed"},
            timeout=180,
        )
        if state["status"] != "running":
            logs = await request("GET", f"/api/deployments/{identity}/logs")
            raise AssertionError((state, logs))
        return state

    async def deploy(url, failover=False):
        box = await request(
            "POST",
            "/api/boxes",
            json={
                "name": "Real integration Box",
                "cpu_limit_cores": 0.25,
                "ram_limit_gb": 0.125,
                "storage_limit_gb": 0.0625,
                "eligible_worker_ids": [
                    w[0].runtime.worker_id for w in workers if not w[1].done()
                ],
                "failover_enabled": failover,
            },
        )
        dep = await request(
            "POST",
            "/api/deployments",
            json={
                "repository_url": url,
                "application_type": "node" if url == node_url else "python",
                "box_id": box["box_id"],
            },
        )
        created_images.append(dep["image_reference"])
        return box, dep

    try:
        await eventually(lambda: asyncio.sleep(0.02, result=server.started), timeout=10)
        async with httpx.AsyncClient(trust_env=False) as unauthenticated:
            assert (await unauthenticated.get(base + "/api/workers")).status_code == 401
        for index in range(2):
            worker_id = "integration-" + uuid4().hex
            provision = await request(
                "POST",
                "/api/workers/register",
                json={
                    "worker_id": worker_id,
                    "hostname": "local-integration",
                    "cpu_cores": 2,
                    "total_ram_gb": 1,
                    "total_storage_gb": 1,
                    "max_containers": 4,
                    "architecture": "arm64",
                    "supported_runtimes": ["python", "node"],
                },
            )
            state = StateDirectory(short_path / f"w{index}")
            state.prepare()
            state.identity(worker_id)
            settings = WorkerSettings(
                control_plane_url=base,
                worker_token=provision["token"],
                worker_id=worker_id,
                state_dir=state.path,
                max_cpu_cores=1,
                max_ram_gb=0.5,
                max_storage_gb=0.5,
                deployment_storage_gb=0.0625,
                heartbeat_interval=0.2,
                reconnect_min_seconds=0.1,
                reconnect_max_seconds=0.2,
                disconnect_grace_seconds=0.2,
                require_control_plane_lease=True,
                max_lease_seconds=1,
                max_clock_skew_seconds=0.2,
            )
            runtime = DockerManager(
                settings,
                worker_id,
                open_local_docker(settings),
                SystemMonitor(state.path),
            )
            runtime.initialize()
            journal = RequestJournal(state)
            lifecycle = ControlPlaneLifecycle(settings, worker_id)
            worker = WorkerApplication(
                runtime, CommandDispatcher(runtime, journal, settings), lifecycle, state
            )
            task = asyncio.create_task(worker.run(install_signals=False))
            workers.append((worker, task, journal, lifecycle))
        await eventually(
            lambda: request("GET", "/api/workers"),
            lambda v: len(v) == 2 and all(w["status"] == "online" for w in v),
            timeout=15,
        )
        duplicate = ServiceContext(config, db)
        with pytest.raises(RuntimeError, match="Another Control Plane"):
            await duplicate.start()
        await duplicate.close()
        # Concurrent transactions cannot reserve the same remaining capacity twice.
        concurrent_box = {
            "name": "Concurrent reservation",
            "cpu_limit_cores": 0.75,
            "ram_limit_gb": 0.125,
            "storage_limit_gb": 0.0625,
            "eligible_worker_ids": [workers[0][0].runtime.worker_id],
            "failover_enabled": False,
        }
        reservations = await asyncio.gather(
            *(http.post("/api/boxes", json=concurrent_box) for _ in range(2))
        )
        assert sorted(row.status_code for row in reservations) == [201, 400]
        claimed = next(row.json() for row in reservations if row.status_code == 201)
        await request("DELETE", "/api/boxes/" + claimed["box_id"])
        box, dep = await deploy(python_url, True)
        identity = dep["deployment_id"]
        state = await running(identity)
        replica = next(r for r in state["replicas"] if r["status"] == "running")
        primary = replica["worker_id"]
        old_container = replica["container_id"]
        route = f"/apps/{identity}/nested?q=1"
        response = await http.get(route)
        assert response.text == "python-real:/nested?q=1", response.text
        response = await http.post(f"/apps/{identity}/echo", content=b"actual-payload")
        assert response.status_code == 201 and response.content == b"actual-payload"
        container = docker.containers.get(old_container)
        assert container.attrs["HostConfig"]["NanoCpus"] == 250000000
        assert container.attrs["HostConfig"]["Memory"] == 128 * 1024**2
        with db.session() as session:
            assert "@sha256:" in session.get(Deployment, UUID(identity)).image_reference
        await eventually(
            lambda: request("GET", f"/api/deployments/{identity}/logs"),
            lambda v: any("real-python-started" in row["message"] for row in v["logs"]),
        )
        # Restart the real controller against its persisted database. Workers
        # reconnect and reconcile without a second application container.
        server.should_exit = True
        await asyncio.wait_for(server_task, 20)
        restarted_socket = socket.socket()
        restarted_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        restarted_socket.bind(("127.0.0.1", port))
        ctx = ServiceContext(config, db)
        server = uvicorn.Server(
            uvicorn.Config(create_app(config, ctx), log_level="error", access_log=False)
        )
        server_task = asyncio.create_task(server.serve(sockets=[restarted_socket]))
        await eventually(lambda: asyncio.sleep(0.01, result=server.started), timeout=10)
        await eventually(
            lambda: request("GET", "/api/workers"),
            lambda v: all(w["status"] == "online" for w in v),
            timeout=15,
        )
        assert (await http.get(f"/apps/{identity}/")).text == "python-real:/"
        assert (
            len(docker.containers.list(filters={"label": f"{WORKER_LABEL}={primary}"}))
            == 1
        )
        # Transport-only reconnect preserves a single running replica and stable run request.
        original_socket = ctx.gateway.active_connections[primary]
        await original_socket.close(code=1012, reason="integration reconnect")
        await eventually(
            lambda: asyncio.sleep(
                0, result=ctx.gateway.active_connections.get(primary)
            ),
            lambda v: v is not None and v is not original_socket,
            timeout=10,
        )
        await asyncio.sleep(0.4)
        assert (await status(identity))["status"] == "running"
        assert (
            len(docker.containers.list(filters={"label": f"{WORKER_LABEL}={primary}"}))
            == 1
        )
        # Disable reconnect while the independent lease task continues: a network partition.
        failed = next(w for w in workers if w[0].runtime.worker_id == primary)
        failed[0].gateway.settings.control_plane_url = "http://127.0.0.1:1"
        await ctx.gateway.active_connections[primary].close(
            code=1012, reason="integration network partition"
        )
        await eventually(
            lambda: asyncio.to_thread(
                lambda: docker.containers.get(old_container).status
            ),
            lambda v: v == "exited",
            timeout=10,
        )
        await eventually(
            lambda: status(identity),
            lambda v: (
                v["status"] == "running"
                and any(
                    r["worker_id"] != primary and r["status"] == "running"
                    for r in v["replicas"]
                )
            ),
            timeout=40,
        )
        assert (await http.get(f"/apps/{identity}/")).text == "python-real:/"
        with db.session() as session:
            record = session.query(FailoverRecord).one()
            assert record.state == "recovered"
            assert (
                session.query(ResourceReservation)
                .filter_by(box_id=UUID(box["box_id"]))
                .count()
                == 1
            )
        # Graceful owner disconnect is tested after a fresh two-worker connection below.
        failed[0].stop.set()
        await asyncio.wait_for(failed[1], 10)
        await request("POST", f"/api/deployments/{identity}/stop")
        await eventually(
            lambda: status(identity), lambda v: v["status"] == "stopped", timeout=15
        )
        assert (await http.get(f"/apps/{identity}/")).status_code == 503
        await request("DELETE", "/api/boxes/" + box["box_id"])
        # Restart the same worker identity and journal, then exercise an active
        # intentional handoff. The replacement must follow a confirmed stop.
        failed[0].runtime.settings.control_plane_url = base
        restarted = WorkerApplication(
            failed[0].runtime,
            CommandDispatcher(failed[0].runtime, failed[2], failed[0].runtime.settings),
            failed[3],
            failed[0].state,
        )
        restarted_task = asyncio.create_task(restarted.run(install_signals=False))
        workers[workers.index(failed)] = (
            restarted,
            restarted_task,
            failed[2],
            failed[3],
        )
        await eventually(
            lambda: request("GET", "/api/workers"),
            lambda v: all(w["status"] == "online" for w in v),
            timeout=15,
        )
        handoff_box, handoff = await deploy(python_url, True)
        handoff_id = handoff["deployment_id"]
        handoff_status = await running(handoff_id)
        handoff_replica = next(
            r for r in handoff_status["replicas"] if r["status"] == "running"
        )
        source = next(
            w for w in workers if w[0].runtime.worker_id == handoff_replica["worker_id"]
        )
        assert (await send_control(source[0].state, "disconnect"))["success"]
        await asyncio.wait_for(source[1], 15)
        await eventually(
            lambda: status(handoff_id),
            lambda v: (
                v["status"] == "running"
                and any(
                    r["status"] == "running"
                    and r["worker_id"] != source[0].runtime.worker_id
                    for r in v["replicas"]
                )
            ),
            timeout=40,
        )
        assert docker.containers.get(handoff_replica["container_id"]).status == "exited"
        assert (await http.get(f"/apps/{handoff_id}/")).text == "python-real:/"
        await request("POST", f"/api/deployments/{handoff_id}/stop")
        await eventually(
            lambda: status(handoff_id), lambda v: v["status"] == "stopped", timeout=15
        )
        await request("DELETE", "/api/boxes/" + handoff_box["box_id"])
        _node_box, node = await deploy(node_url)
        node_id = node["deployment_id"]
        await running(node_id)
        assert (await http.get(f"/apps/{node_id}/")).text == "node-real:/"
        version = await request("POST", f"/api/deployments/{node_id}/redeploy")
        assert version["deployment_id"] != node_id
        await running(version["deployment_id"])
        assert (await status(node_id))["status"] == "stopped"
        assert (
            await http.get(f"/apps/{version['deployment_id']}/")
        ).text == "node-real:/"
        live = next(w for w in workers if not w[1].done())
        assert (await send_control(live[0].state, "pause"))["success"]
        assert (await send_control(live[0].state, "resume"))["success"]
        await request("POST", f"/api/deployments/{version['deployment_id']}/stop")
        await eventually(
            lambda: status(version["deployment_id"]),
            lambda v: v["status"] == "stopped",
            timeout=15,
        )
        framework_box, framework = await deploy(fastapi_url)
        await running(framework["deployment_id"])
        assert (await http.get(f"/apps/{framework['deployment_id']}/")).json() == {
            "framework": "fastapi-real"
        }
        await request("POST", f"/api/deployments/{framework['deployment_id']}/stop")
        await eventually(
            lambda: status(framework["deployment_id"]),
            lambda v: v["status"] == "stopped",
            timeout=15,
        )
        await request("DELETE", "/api/boxes/" + framework_box["box_id"])
        bad_box, bad = await deploy(bad_url)
        bad_state = await eventually(
            lambda: status(bad["deployment_id"]),
            lambda v: v["status"] == "failed",
            timeout=180,
        )
        assert bad_state["public_url"] is None
        await eventually(
            lambda: request("GET", "/api/boxes/" + bad_box["box_id"]),
            lambda v: v["deployment_id"] is None,
            timeout=15,
        )
        with db.session() as session:
            assert session.query(ResourceReservation).count() == 0
            assert (
                session.query(Replica).filter(Replica.status != "stopped").count() == 0
            )
        assert (await send_control(live[0].state, "disconnect"))["success"]
        await asyncio.wait_for(live[1], 10)
    finally:
        for worker, task, journal, lifecycle in workers:
            worker.stop.set()
            await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 20)
            await lifecycle.close()
            journal.close()
            for container in worker.runtime.containers():
                container.remove(force=True)
            filters = {"label": f"{WORKER_LABEL}={worker.runtime.worker_id}"}
            for network in docker.networks.list(filters=filters):
                network.remove()
            for volume in docker.volumes.list(filters=filters):
                volume.remove()
            worker.runtime.close()
        server.should_exit = True
        await asyncio.wait_for(server_task, 30)
        await http.aclose()
        # Only images built by this test, identified by registry prefix, are removed.
        for image in docker.images.list():
            for tag in image.tags:
                if tag.startswith(registry + "/lattice-app-"):
                    try:
                        docker.images.remove(tag, force=True)
                    except ImageNotFound:
                        pass
        db.close()
