"""Low-cost host readings and canonical snapshots, with binary resource units."""

import platform
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import psutil
from shared.contracts import Heartbeat, WorkerSnapshot
from shared.enums import ApplicationType, WorkerStatus

GIB = 1024**3
MIB = 1024**2


@dataclass(frozen=True)
class SystemReading:
    cpu_cores: int
    cpu_usage_percent: float
    total_ram_bytes: int
    available_ram_bytes: int
    total_storage_bytes: int
    available_storage_bytes: int
    network_sent_bytes: int
    network_received_bytes: int
    architecture: str


class SystemMonitor:
    def __init__(self, storage_path: Path, system=psutil):
        self.storage_path = storage_path
        self.system = system

    def read(self) -> SystemReading:
        memory = self.system.virtual_memory()
        disk = self.system.disk_usage(str(self.storage_path))
        network = self.system.net_io_counters()
        return SystemReading(
            cpu_cores=self.system.cpu_count(logical=True) or 1,
            cpu_usage_percent=self.system.cpu_percent(interval=None),
            total_ram_bytes=memory.total,
            available_ram_bytes=memory.available,
            total_storage_bytes=disk.total,
            available_storage_bytes=disk.free,
            network_sent_bytes=network.bytes_sent if network else 0,
            network_received_bytes=network.bytes_recv if network else 0,
            architecture=platform.machine().lower(),
        )


def make_snapshot(
    worker_id: str,
    reading: SystemReading,
    *,
    active_container_count: int,
    max_containers: int,
    available_cpu_cores: float,
    available_ram_gb: float,
    available_storage_gb: float,
    total_cpu_cores: int | None = None,
    total_ram_gb: float | None = None,
    status: WorkerStatus = WorkerStatus.ONLINE,
) -> WorkerSnapshot:
    cpu = total_cpu_cores or reading.cpu_cores
    ram = total_ram_gb or reading.total_ram_bytes / GIB
    return WorkerSnapshot(
        worker_id=worker_id,
        hostname=socket.gethostname(),
        status=status,
        cpu_cores=cpu,
        available_cpu_cores=min(cpu, max(0, available_cpu_cores)),
        total_ram_gb=ram,
        available_ram_gb=min(ram, max(0, available_ram_gb)),
        total_storage_gb=reading.total_storage_bytes / GIB,
        available_storage_gb=min(
            reading.available_storage_bytes / GIB, max(0, available_storage_gb)
        ),
        active_container_count=active_container_count,
        max_containers=max_containers,
        architecture=reading.architecture,
        supported_runtimes=[ApplicationType.PYTHON, ApplicationType.NODE],
        last_heartbeat=datetime.now(UTC),
    )


def make_heartbeat(
    snapshot: WorkerSnapshot, reading: SystemReading, running_containers: list[str]
) -> Heartbeat:
    return Heartbeat(
        worker_id=snapshot.worker_id,
        cpu_usage_percent=reading.cpu_usage_percent,
        available_ram_gb=snapshot.available_ram_gb,
        available_storage_gb=snapshot.available_storage_gb,
        active_container_count=snapshot.active_container_count,
        running_containers=running_containers,
        timestamp=datetime.now(UTC),
    )
