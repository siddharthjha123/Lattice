"""Run with `python -m worker_agent.main` from the backend source directory."""

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path

from pydantic import ValidationError

from worker_agent.application import WorkerApplication
from worker_agent.communication.control import send_control
from worker_agent.communication.dispatcher import CommandDispatcher
from worker_agent.communication.journal import RequestJournal
from worker_agent.communication.lifecycle import ControlPlaneLifecycle
from worker_agent.config import Settings, load_settings, read_config
from worker_agent.docker_runtime.manager import DockerManager
from worker_agent.logging import configure_logging
from worker_agent.security.auth import WorkerAuthenticationError
from worker_agent.security.policy import open_local_docker
from worker_agent.state import StateDirectory
from worker_agent.telemetry.system_monitor import SystemMonitor


def parser():
    result = argparse.ArgumentParser(description="Lattice Worker Service")
    result.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=[
            "run",
            "identity",
            "snapshot",
            "check",
            "pause",
            "resume",
            "stop",
            "list",
            "status",
            "disconnect",
        ],
    )
    result.add_argument(
        "--config",
        type=Path,
        help="Local JSON configuration (environment takes precedence)",
    )
    result.add_argument(
        "--state-dir", type=Path, help="Override private local state directory"
    )
    return result


def local_state(args):
    data = read_config(args.config)
    default = Settings.model_fields["state_dir"].default
    path = (
        args.state_dir or os.environ.get("STATE_DIR") or data.get("state_dir", default)
    )
    state = StateDirectory(Path(path))
    state.prepare()
    return state, os.environ.get("WORKER_ID") or data.get("worker_id")


async def serve_worker(config, state, worker_id):
    client = await asyncio.to_thread(open_local_docker, config)
    runtime = DockerManager(config, worker_id, client, SystemMonitor(state.path))
    journal = None
    lifecycle = None
    try:
        await asyncio.to_thread(runtime.initialize)
        journal = RequestJournal(state)
        lifecycle = ControlPlaneLifecycle(config, worker_id)
        dispatcher = CommandDispatcher(runtime, journal, config)
        await WorkerApplication(runtime, dispatcher, lifecycle, state).run()
    finally:
        if lifecycle is not None:
            await lifecycle.close()
        if journal is not None:
            journal.close()
        await asyncio.to_thread(runtime.close)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        state, requested_id = local_state(args)
        if args.command in {"pause", "resume", "stop", "list", "status", "disconnect"}:
            response = asyncio.run(send_control(state, args.command))
            print(json.dumps(response, indent=2))
            return 0 if response["success"] else 1
        worker_id = state.identity(requested_id)
        if args.command == "identity":
            print(worker_id)
            return 0
        config = load_settings(args.config)
        if args.state_dir is not None:
            config.state_dir = args.state_dir
        # Configuration may contain WORKER_ID even when local_state read none.
        worker_id = state.identity(config.worker_id)
        configure_logging(config.worker_token)
        if args.command in {"snapshot", "check"}:
            client = open_local_docker(config)
            runtime = DockerManager(
                config, worker_id, client, SystemMonitor(state.path)
            )
            try:
                runtime.initialize()
                snapshot, _ = runtime.telemetry()
                print(snapshot.model_dump_json(indent=2))
            finally:
                runtime.close()
            return 0
        with state.lock():
            asyncio.run(serve_worker(config, state, worker_id))
        return 0
    except ValidationError as exc:
        fields = {
            str(error["loc"][0])
            if error["loc"] and error["loc"][0] in Settings.model_fields
            else "configuration policy or unknown field"
            for error in exc.errors(include_input=False, include_context=False)
        }
        logging.getLogger("worker_agent").error(
            "Invalid configuration; check: %s", ", ".join(sorted(fields))
        )
        return 2
    except WorkerAuthenticationError:
        logging.getLogger("worker_agent").error(
            "Worker authentication rejected; check the provisioned ID/token"
        )
        return 2
    except Exception as exc:  # noqa: BLE001 -- CLI must not print credential-bearing validation input
        logging.getLogger("worker_agent").error(
            "Worker stopped (%s)", type(exc).__name__
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
