"""Conservative admission against owner budgets and the execution daemon."""

from dataclasses import dataclass

from worker_agent.security.policy import WORKER_LABEL
from worker_agent.telemetry.system_monitor import GIB, MIB

ACTIVE_STATES = {"created", "running", "paused", "restarting", "removing"}


@dataclass(frozen=True)
class Capacity:
    cpu_cores: float
    ram_gb: float
    container_slots: int


def calculate_capacity(settings, worker_id, reading, daemon, containers) -> Capacity:
    active = [item for item in containers if item.status in ACTIVE_STATES]
    owned = [item for item in active if item.labels.get(WORKER_LABEL) == worker_id]
    daemon_cpu = int(daemon["NCPU"])
    daemon_ram = int(daemon["MemTotal"]) / GIB

    def cpu(item):
        host = item.attrs.get("HostConfig", {})
        return host.get("NanoCpus", 0) / 1e9 or daemon_cpu

    def ram(item):
        return item.attrs.get("HostConfig", {}).get("Memory", 0) / GIB or daemon_ram

    return Capacity(
        cpu_cores=max(
            0,
            min(
                settings.max_cpu_cores - sum(map(cpu, owned)),
                daemon_cpu - sum(map(cpu, active)),
            ),
        ),
        ram_gb=max(
            0,
            min(
                settings.max_ram_gb - sum(map(ram, owned)),
                daemon_ram - sum(map(ram, active)),
                reading.available_ram_bytes / GIB,
            ),
        ),
        container_slots=max(0, settings.max_containers - len(owned)),
    )


def check_admission(command, capacity: Capacity) -> None:
    if capacity.container_slots < 1:
        raise ValueError("Worker container capacity is exhausted")
    if command.cpu_limit_cores > capacity.cpu_cores + 1e-9:
        raise ValueError("Insufficient available CPU cores")
    if command.ram_limit_mb * MIB > capacity.ram_gb * GIB:
        raise ValueError("Insufficient available RAM")
