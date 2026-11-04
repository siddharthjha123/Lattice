from unittest.mock import Mock
from uuid import uuid4

from worker_agent.docker_runtime.inspection import inspect_container
from worker_agent.docker_runtime.logs import LogCollector
from worker_agent.security.policy import DEPLOYMENT_LABEL
from worker_agent.tests.test_config import settings


def test_inspection_reports_health_and_never_exposes_environment():
    container = Mock()
    container.id = "container-1"
    container.labels = {DEPLOYMENT_LABEL: str(uuid4())}
    container.status = "running"
    container.attrs = {
        "State": {"Status": "running", "Health": {"Status": "unhealthy"}},
        "HostConfig": {"NanoCpus": 1_000_000_000, "Memory": 512},
        "Config": {"Env": ["SECRET=do-not-send"]},
        "NetworkSettings": {"Ports": {"8000/tcp": [{"HostPort": "12345"}]}},
    }
    container.stats.return_value = {"memory_stats": {"usage": 128}}
    inspection = inspect_container(container)
    assert inspection.event().status.value == "unhealthy"
    assert inspection.cpu_limit_cores == 1
    assert inspection.memory_usage_bytes == 128
    assert "SECRET" not in inspection.summary()
    assert inspection.ports["8000/tcp"][0]["HostPort"] == "12345"


def test_log_polling_is_bounded_redacted_and_deduplicated(tmp_path):
    container = Mock()
    container.id = "container-1"
    container.labels = {DEPLOYMENT_LABEL: str(uuid4())}
    container.logs.side_effect = lambda **kwargs: (
        b"2026-10-31T12:00:00.123456789Z test-token ready\n"
        if kwargs["stdout"]
        else b""
    )
    collector = LogCollector(settings(tmp_path))
    events = collector.collect(container)
    assert len(events) == 1
    assert events[0].message == "[REDACTED] ready"
    assert collector.collect(container) == []
    collector.retain(set())
    assert not collector.seen
