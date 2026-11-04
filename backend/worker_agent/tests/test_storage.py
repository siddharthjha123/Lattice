from unittest.mock import Mock

import pytest
from worker_agent.docker_runtime.storage import StorageMonitor
from worker_agent.security.policy import DEPLOYMENT_LABEL, STORAGE_LABEL, WORKER_LABEL
from worker_agent.telemetry.system_monitor import GIB


def volume(deployment="deployment-1", size=0, limit=1, worker="W-001"):
    return {
        "Name": "data-volume",
        "Labels": {
            WORKER_LABEL: worker,
            DEPLOYMENT_LABEL: deployment,
            STORAGE_LABEL: str(limit),
        },
        "UsageData": {"Size": size},
    }


def test_active_reservations_and_retained_data_are_not_double_counted():
    client = Mock()
    client.df.return_value = {
        "Volumes": [volume(size=GIB // 2), volume(deployment="stopped", size=GIB // 4)]
    }
    storage = StorageMonitor(client, "W-001", 2)
    assert storage.available_gb({"deployment-1"}) == 0.75
    storage.admit("deployment-1", 1, set(), 10 * GIB)


def test_admission_rejects_reserved_and_actual_disk_exhaustion():
    client = Mock()
    client.df.return_value = {"Volumes": [volume()]}
    storage = StorageMonitor(client, "W-001", 1)
    with pytest.raises(ValueError, match="storage budget"):
        storage.admit("deployment-2", 1, {"deployment-1"}, 10 * GIB)
    client.df.return_value = {"Volumes": []}
    with pytest.raises(ValueError, match="host storage"):
        storage.admit("deployment-1", 1, set(), GIB // 2)


def test_overrun_reports_and_unknown_sizes_fail_closed():
    client = Mock()
    client.df.return_value = {
        "Volumes": [volume(size=2 * GIB), volume(worker="foreign")]
    }
    storage = StorageMonitor(client, "W-001", 4)
    assert storage.violations() == {
        "deployment-1": "Deployment data storage limit exceeded"
    }
    client.df.return_value = {"Volumes": [volume(size=-1)]}
    with pytest.raises(RuntimeError, match="reliably measure"):
        storage.volumes()
