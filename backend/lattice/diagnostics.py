"""Read-only, allowlisted contributor diagnostics; never dump private JSON."""

import json
import re
import sys
from importlib.metadata import version
from pathlib import Path
from types import SimpleNamespace

import httpx
from worker_agent.security.policy import open_local_docker
from worker_agent.state import StateDirectory

from lattice.cli import server_url


def doctor(args):
    origin = server_url(args.server)
    report = {
        "version": version("lattice"),
        "python": sys.executable,
        "package": str(Path(__file__).parent),
        "profiles": [],
    }
    root = Path.home() / ".lattice"
    candidates = {args.state_dir.expanduser().absolute()} if args.state_dir else set()
    pending = [(root, 0)]
    visited = 0
    while pending and visited < 100:
        path, depth = pending.pop(0)
        visited += 1
        if path.is_symlink() or not path.is_dir():
            continue
        if (path / "connection.json").is_file():
            candidates.add(path)
        if depth < 3:
            try:
                pending.extend(
                    (child, depth + 1)
                    for child in path.iterdir()
                    if child.is_dir() and not child.is_symlink()
                )
            except OSError:
                pass
    for path in sorted(candidates):
        item = {"state_dir": str(path)}
        try:
            saved = StateDirectory(path).read_json("connection.json")
            pool = saved.get("pool_name")
            item["pool"] = (
                pool
                if isinstance(pool, str) and re.fullmatch(r"[a-z][a-z0-9-]{2,47}", pool)
                else "invalid"
            )
            item["server"] = server_url(saved.get("server", ""))
            item["enrolled"] = saved.get("enrolled") is True
            item["control_endpoint_present"] = (path / "control.sock").exists() or (
                path / "control.json"
            ).is_file()
        except Exception as error:  # noqa: BLE001 -- raw private data must not enter diagnostics
            item["error_type"] = type(error).__name__
        report["profiles"].append(item)
    client = None
    try:
        client = open_local_docker(SimpleNamespace(docker_timeout=5))
        info = client.info()
        report["docker"] = {
            "available": True,
            "linux_engine": info.get("OSType") == "linux",
            "architecture": info.get("Architecture"),
            "cpu_cores": info.get("NCPU"),
            "ram_bytes": info.get("MemTotal"),
            "running_containers": len(client.containers.list()),
        }
    except Exception as error:  # noqa: BLE001 -- Docker/environment exception text can contain credentials
        report["docker"] = {"available": False, "error_type": type(error).__name__}
    finally:
        if client is not None:
            client.close()
    try:
        with httpx.Client(
            timeout=8, trust_env=False, follow_redirects=False
        ) as connection:
            response = connection.get(origin + "/health")
            report["controller"] = {
                "server": origin,
                "http_status": response.status_code,
                "healthy": response.is_success
                and response.headers.get("content-type", "").startswith(
                    "application/json"
                )
                and response.json().get("status") == "healthy",
            }
    except Exception as error:  # noqa: BLE001 -- only class names are safe here
        report["controller"] = {
            "server": origin,
            "healthy": False,
            "error_type": type(error).__name__,
        }
    print(json.dumps(report, indent=2))
    return 0
