"""Synchronous Docker adapter. Async callers run operations off the event loop."""

import threading

from docker.errors import APIError, ImageNotFound, NotFound
from shared.enums import WorkerStatus

from worker_agent.docker_runtime.inspection import inspect_container
from worker_agent.docker_runtime.limits import (
    ACTIVE_STATES,
    calculate_capacity,
    check_admission,
)
from worker_agent.docker_runtime.storage import StorageMonitor
from worker_agent.security.policy import (
    DEPLOYMENT_LABEL,
    FINGERPRINT_LABEL,
    REQUEST_LABEL,
    STORAGE_LABEL,
    WORKER_LABEL,
    assert_owned,
    container_options,
    fingerprint,
    resource_name,
)
from worker_agent.telemetry.system_monitor import GIB, make_heartbeat, make_snapshot


class DockerManager:
    def __init__(self, settings, worker_id, client, monitor):
        self.settings = settings
        self.worker_id = worker_id
        self.client = client
        self.monitor = monitor
        self.lock = threading.RLock()
        self.paused = False
        self.draining = False
        self.lease_valid = not settings.require_control_plane_lease
        self.daemon = {}
        self.storage = StorageMonitor(client, worker_id, settings.max_storage_gb)
        self.storage_errors = []

    def initialize(self) -> None:
        self.client.ping()
        self.daemon = self.client.info()
        if self.daemon.get("OSType") != "linux":
            raise ValueError(
                "Worker requires Linux containers (Docker Desktop is supported)"
            )
        if self.daemon.get("NCPU", 0) < 1 or self.daemon.get("MemTotal", 0) < 1:
            raise ValueError("Docker daemon did not report its CPU and RAM capacity")

    def containers(self, all_containers=True):
        return self.client.containers.list(
            all=all_containers, filters={"label": f"{WORKER_LABEL}={self.worker_id}"}
        )

    def capacity(self):
        return calculate_capacity(
            self.settings,
            self.worker_id,
            self.monitor.read(),
            self.daemon,
            self.client.containers.list(all=True),
        )

    def _resources(self, command, storage_gb):
        labels = {
            WORKER_LABEL: self.worker_id,
            DEPLOYMENT_LABEL: str(command.deployment_id),
            STORAGE_LABEL: str(storage_gb),
        }
        volume_name = resource_name(self.worker_id, str(command.deployment_id), "data")
        network_name = resource_name(self.worker_id, str(command.deployment_id), "net")
        try:
            volume = self.client.volumes.get(volume_name)
            volume_labels = volume.attrs.get("Labels") or {}
            if any(
                volume_labels.get(key) != labels[key]
                for key in (WORKER_LABEL, DEPLOYMENT_LABEL)
            ):
                raise PermissionError("Data volume is not owned by this deployment")
            if volume.attrs.get("Driver") != "local" or volume.attrs.get("Options"):
                raise PermissionError(
                    "Data volume must use the plain local driver without host bindings"
                )
            if float(volume_labels.get(STORAGE_LABEL, "nan")) != storage_gb:
                raise ValueError("Existing data volume has a different storage policy")
        except NotFound:
            self.client.volumes.create(name=volume_name, driver="local", labels=labels)
        try:
            network = self.client.networks.get(network_name)
            network_labels = network.attrs.get("Labels") or {}
            if any(
                network_labels.get(key) != labels[key]
                for key in (WORKER_LABEL, DEPLOYMENT_LABEL)
            ):
                raise PermissionError("Network is not owned by this deployment")
            if network.attrs.get("Driver") != "bridge":
                raise PermissionError("Deployment network must use an isolated bridge")
        except NotFound:
            self.client.networks.create(
                name=network_name, driver="bridge", labels=labels
            )
        return network_name, volume_name

    def _admit(self, command, exclude_container_id=None):
        if not self.lease_valid:
            raise ValueError("No valid Control Plane execution lease")
        if self.paused or self.draining:
            raise ValueError(
                "Worker is paused or draining and cannot accept new workloads"
            )
        containers = [
            item
            for item in self.client.containers.list(all=True)
            if item.id != exclude_container_id
        ]
        reading = self.monitor.read()
        capacity = calculate_capacity(
            self.settings, self.worker_id, reading, self.daemon, containers
        )
        check_admission(command, capacity)
        active = {
            item.labels.get(DEPLOYMENT_LABEL)
            for item in containers
            if item.labels.get(WORKER_LABEL) == self.worker_id
            and item.status in ACTIVE_STATES
        }
        storage_gb = (
            command.storage_limit_gb
            or self.settings.deployment_storage_limits.get(
                command.deployment_id, self.settings.deployment_storage_gb
            )
        )
        if storage_gb > self.settings.max_storage_gb:
            raise ValueError("Deployment storage exceeds the owner's worker budget")
        self.storage.admit(
            str(command.deployment_id),
            storage_gb,
            active,
            reading.available_storage_bytes,
        )
        return storage_gb

    def _existing_request(self, command):
        for item in self.containers():
            if item.labels.get(REQUEST_LABEL) == str(command.request_id):
                if item.labels.get(FINGERPRINT_LABEL) != fingerprint(command):
                    raise ValueError("Request ID was reused with different parameters")
                if item.status == "created":
                    storage_gb = self._admit(command, exclude_container_id=item.id)
                    self._resources(command, storage_gb)
                    item.start()
                    item.reload()
                if item.status not in {"running", "paused"}:
                    raise RuntimeError(
                        "Previous run request exists but its container is not running"
                    )
                return item.id
        return None

    def run(self, command) -> str:
        with self.lock:
            existing = self._existing_request(command)
            if existing:
                return existing
            if any(
                item.labels.get(DEPLOYMENT_LABEL) == str(command.deployment_id)
                and item.status in ACTIVE_STATES
                for item in self.containers()
            ):
                raise ValueError(
                    "Deployment already has an active container on this worker"
                )
            storage_gb = self._admit(command)
            network = resource_name(self.worker_id, str(command.deployment_id), "net")
            volume = resource_name(self.worker_id, str(command.deployment_id), "data")
            options = container_options(
                command, self.settings, self.worker_id, network, volume, storage_gb
            )
            # Pull before create: a Control Plane image must exist in a registry.
            if self.settings.image_pull_policy == "always":
                self.client.images.pull(command.image_reference)
            else:
                try:
                    self.client.images.get(command.image_reference)
                except ImageNotFound:
                    self.client.images.pull(command.image_reference)
            self._admit(command)  # Capacity and owner intent may change during a pull.
            self._resources(command, storage_gb)
            container = self.client.containers.create(**options)
            try:
                self._admit(command, exclude_container_id=container.id)
                container.start()
                container.reload()
                if container.status != "running":
                    raise RuntimeError("Container exited before startup completed")
            except Exception:
                container.remove(force=True)
                raise
            return container.id

    def owned_container(self, container_id, deployment_id=None):
        container = self.client.containers.get(container_id)
        assert_owned(container, self.worker_id, deployment_id)
        return container

    def stop(self, container_id, deployment_id=None) -> str:
        with self.lock:
            try:
                container = self.owned_container(container_id, deployment_id)
            except NotFound:
                return (
                    container_id  # Stop of an already removed container is idempotent.
                )
            if container.status == "paused":
                container.unpause()
            if container.status == "created":
                container.remove()
                return container.id
            if container.status in ACTIVE_STATES:
                container.stop(timeout=10)
            return container.id

    def close(self) -> None:
        self.client.close()

    def inspect(self, container_id, include_stats=True):
        return inspect_container(self.owned_container(container_id), include_stats)

    def admission_blockers(self):
        result = []
        if self.paused:
            result.append("paused")
        if self.draining:
            result.append("draining")
        if not self.lease_valid:
            result.append("lease_expired")
        if self.storage_errors:
            result.append("storage_unavailable")
        return result

    def telemetry(self):
        reading = self.monitor.read()
        containers = self.client.containers.list(all=True)
        owned = [
            item
            for item in containers
            if item.labels.get(WORKER_LABEL) == self.worker_id
        ]
        active = [item for item in owned if item.status in ACTIVE_STATES]
        capacity = calculate_capacity(
            self.settings, self.worker_id, reading, self.daemon, containers
        )
        deployments = {item.labels.get(DEPLOYMENT_LABEL) for item in active}
        available_storage = self.storage.available_gb(deployments)
        unavailable = bool(self.admission_blockers())
        snapshot = make_snapshot(
            self.worker_id,
            reading,
            active_container_count=len(active),
            max_containers=self.settings.max_containers,
            available_cpu_cores=0 if unavailable else capacity.cpu_cores,
            available_ram_gb=0 if unavailable else capacity.ram_gb,
            available_storage_gb=0 if unavailable else available_storage,
            total_cpu_cores=int(self.daemon["NCPU"]),
            total_ram_gb=self.daemon["MemTotal"] / GIB,
            status=WorkerStatus.UNHEALTHY if unavailable else WorkerStatus.ONLINE,
        )
        snapshot.architecture = self.daemon.get("Architecture", reading.architecture)
        return snapshot, make_heartbeat(
            snapshot, reading, [item.id for item in active if item.status == "running"]
        )

    def enforce_storage(self) -> list[tuple[str, str, str]]:
        """Stop workloads after a measured overrun; retain data for the owner."""
        with self.lock:
            violations = self.storage.violations()
            self.storage_errors = list(violations.values())
            stopped = []
            for container in self.containers():
                deployment = container.labels.get(DEPLOYMENT_LABEL)
                if deployment in violations and container.status in ACTIVE_STATES:
                    self.stop(container.id, deployment)
                    stopped.append((container.id, deployment, violations[deployment]))
            return stopped

    def fence(self):
        """Stop serving after lease expiry; do not wait behind an image pull lock."""
        for container in self.containers():
            try:
                if container.status == "paused":
                    container.unpause()
                if container.status == "created":
                    container.remove(force=True)
                elif container.status in ACTIVE_STATES:
                    container.kill()
            except NotFound:
                continue
            except APIError as exc:
                # An acknowledged stop may race the independent watchdog.
                if exc.status_code != 409:
                    raise
                try:
                    container.reload()
                except NotFound:
                    continue
                if container.status in ACTIVE_STATES:
                    raise
