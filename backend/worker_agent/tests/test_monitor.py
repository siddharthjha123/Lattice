from types import SimpleNamespace
from unittest.mock import Mock

from worker_agent.telemetry.system_monitor import (
    GIB,
    SystemMonitor,
    make_heartbeat,
    make_snapshot,
)


def test_nonblocking_sampling_and_binary_units(tmp_path):
    system = Mock()
    system.cpu_count.return_value = 8
    system.cpu_percent.return_value = 25
    system.virtual_memory.return_value = SimpleNamespace(
        total=16 * GIB, available=8 * GIB
    )
    system.disk_usage.return_value = SimpleNamespace(total=128 * GIB, free=64 * GIB)
    system.net_io_counters.return_value = SimpleNamespace(
        bytes_sent=123, bytes_recv=456
    )
    reading = SystemMonitor(tmp_path, system).read()
    system.cpu_percent.assert_called_once_with(interval=None)
    snapshot = make_snapshot(
        "W-001",
        reading,
        active_container_count=1,
        max_containers=4,
        available_cpu_cores=2,
        available_ram_gb=4,
        available_storage_gb=8,
    )
    assert snapshot.total_ram_gb == 16
    assert snapshot.available_ram_gb == 4
    assert reading.network_sent_bytes == 123
    heartbeat = make_heartbeat(snapshot, reading, ["container-1"])
    assert heartbeat.running_containers == ["container-1"]
    assert heartbeat.cpu_usage_percent == 25
    assert heartbeat.timestamp.utcoffset().total_seconds() == 0
