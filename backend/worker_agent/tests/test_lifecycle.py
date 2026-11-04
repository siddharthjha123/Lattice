import io
import json
import logging
from datetime import UTC, datetime

import httpx
import pytest
from shared.contracts import WorkerSnapshot
from worker_agent.communication.lifecycle import (
    ControlPlaneLifecycle,
    ControlPlaneUnavailable,
)
from worker_agent.logging import configure_logging
from worker_agent.security.auth import WorkerAuthenticationError
from worker_agent.tests.test_config import settings


@pytest.mark.asyncio
async def test_snapshot_uses_shared_payload_and_auth_headers(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(204)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    lifecycle = ControlPlaneLifecycle(
        settings(tmp_path, snapshot_path="/worker-snapshots"), "W-001", client
    )
    snapshot = WorkerSnapshot(
        worker_id="W-001",
        hostname="worker",
        status="online",
        cpu_cores=2,
        available_cpu_cores=1,
        total_ram_gb=4,
        available_ram_gb=2,
        total_storage_gb=16,
        available_storage_gb=8,
        active_container_count=0,
        max_containers=4,
        architecture="arm64",
        supported_runtimes=["python"],
        last_heartbeat=datetime.now(UTC),
    )
    assert await lifecycle.publish_snapshot(snapshot)
    assert json.loads(requests[0].content) == snapshot.model_dump(mode="json")
    assert requests[0].headers["Authorization"] == "Bearer test-token"
    assert requests[0].headers["X-Worker-ID"] == "W-001"
    await lifecycle.notify_disconnect()
    assert requests[1].url.path == "/api/workers/W-001/disconnect"
    await lifecycle.close()


@pytest.mark.parametrize(
    "status, error",
    [
        (401, WorkerAuthenticationError),
        (403, WorkerAuthenticationError),
        (503, ControlPlaneUnavailable),
    ],
)
async def test_lifecycle_failure_classification(tmp_path, status, error):
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(status))
    )
    lifecycle = ControlPlaneLifecycle(settings(tmp_path), "W-001", client)
    with pytest.raises(error):
        await lifecycle.notify_disconnect()
    await lifecycle.close()


def test_structured_logs_redact_tokens_in_messages_and_tracebacks(tmp_path):
    stream = io.StringIO()
    configure_logging(settings(tmp_path).worker_token, stream)
    logger = logging.getLogger("worker_agent.test")
    try:
        raise RuntimeError("test-token")
    except RuntimeError:
        logger.exception("Credential must be redacted: %s", "test-token")
    output = stream.getvalue()
    assert "test-token" not in output
    assert "[REDACTED]" in output
    assert json.loads(output)["level"] == "error"
