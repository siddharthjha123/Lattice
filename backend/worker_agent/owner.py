"""Owner controls persist admission state and operate only on owned containers."""

import asyncio

from docker.errors import DockerException

from worker_agent.docker_runtime.limits import ACTIVE_STATES


class OwnerControls:
    def __init__(self, runtime, state, disconnect):
        self.runtime = runtime
        self.state = state
        self.disconnect = disconnect
        try:
            paused = state.read_json("owner.json")["paused"]
        except FileNotFoundError:
            paused = False
        if not isinstance(paused, bool):
            raise TypeError("Stored owner pause state is invalid")
        self.runtime.paused = paused

    def _set_paused(self, value):
        self.state.write_json("owner.json", {"paused": value})
        self.runtime.paused = value

    def pause(self):
        # Gate new starts immediately even while a long pull owns the runtime lock.
        self.runtime.paused = True
        with self.runtime.lock:
            self._set_paused(True)
            changed = []
            for container in self.runtime.containers():
                if container.status == "running":
                    container.pause()
                    changed.append(container.id)
            return {"paused": True, "containers": changed}

    def resume(self):
        with self.runtime.lock:
            changed = []
            for container in self.runtime.containers():
                if container.status == "paused":
                    container.unpause()
                    changed.append(container.id)
            self._set_paused(False)
            return {"paused": False, "containers": changed}

    def stop(self, *, persist_pause=True):
        self.runtime.paused = True
        with self.runtime.lock:
            if persist_pause:
                self._set_paused(True)
            stopped = [
                self.runtime.stop(item.id)
                for item in self.runtime.containers()
                if item.status in ACTIVE_STATES
            ]
            return {"paused": True, "stopped": stopped}

    def status(self):
        result = {
            "worker_id": self.runtime.worker_id,
            "paused": self.runtime.paused,
            "draining": self.runtime.draining,
            "lease_valid": self.runtime.lease_valid,
            "storage_errors": list(self.runtime.storage_errors),
            "admission_blockers": self.runtime.admission_blockers(),
        }
        try:
            result["containers"] = [
                self.runtime.inspect(item.id, False).as_dict()
                for item in self.runtime.containers()
            ]
            result["docker_available"] = True
        except DockerException as error:
            result["containers"] = []
            result["docker_available"] = False
            result["docker_error_type"] = type(error).__name__
            result["admission_blockers"].append("docker_unavailable")
        return result

    async def handle(self, command):
        if command == "disconnect":
            return await self.disconnect()
        if command in {"list", "status"}:
            return await asyncio.to_thread(self.status)
        return await asyncio.to_thread(getattr(self, command))
