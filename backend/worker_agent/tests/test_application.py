import asyncio
import threading
from unittest.mock import AsyncMock, Mock

from worker_agent.application import WorkerApplication
from worker_agent.main import main
from worker_agent.state import StateDirectory
from worker_agent.tests.test_config import settings


async def test_disconnect_notifies_before_stopping_and_is_idempotent(tmp_path):
    runtime = Mock(
        settings=settings(tmp_path, disconnect_grace_seconds=0, stop_on_disconnect=True)
    )
    runtime.lock = threading.RLock()
    runtime.worker_id = "W-001"
    runtime.containers.return_value = []
    lifecycle = Mock(notify_disconnect=AsyncMock())
    state = StateDirectory(tmp_path)
    state.prepare()
    app = WorkerApplication(runtime, Mock(), lifecycle, state)
    await app.request_disconnect()
    first = app.shutdown_task
    await app.request_disconnect()
    assert app.shutdown_task is first
    await asyncio.wait_for(first, 1)
    lifecycle.notify_disconnect.assert_awaited_once()
    assert app.stop.is_set()
    assert runtime.paused


def test_identity_command_does_not_need_credentials(tmp_path, capsys):
    assert main(["identity", "--state-dir", str(tmp_path)]) == 0
    first = capsys.readouterr().out.strip()
    assert first
    assert main(["identity", "--state-dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out.strip() == first


async def test_supervisor_shutdown_fences_leased_workloads_despite_retention(tmp_path):
    runtime = Mock(
        settings=settings(
            tmp_path, require_control_plane_lease=True, stop_on_disconnect=False
        )
    )
    runtime.paused = False
    runtime.worker_id = "W-001"
    state = StateDirectory(tmp_path)
    state.prepare()
    app = WorkerApplication(runtime, Mock(), Mock(), state)
    app.control.start = AsyncMock()
    app.control.close = AsyncMock()
    app.gateway.run = AsyncMock()
    app.stop.set()
    await app.run(install_signals=False)
    runtime.fence.assert_called_once()
    assert runtime.lease_valid is False
    app.control.close.assert_awaited_once()


async def test_intentional_disconnect_does_not_pause_next_worker_start(tmp_path):
    runtime = Mock(
        settings=settings(tmp_path, disconnect_grace_seconds=0, stop_on_disconnect=True)
    )
    runtime.lock = threading.RLock()
    runtime.worker_id = "W-001"
    runtime.containers.return_value = []
    state = StateDirectory(tmp_path)
    state.prepare()
    app = WorkerApplication(runtime, Mock(), Mock(notify_disconnect=AsyncMock()), state)
    await app.request_disconnect()
    await app.shutdown_task
    # Reconstruct owner policy exactly as a new worker process would.
    from worker_agent.owner import OwnerControls

    restarted = Mock()
    OwnerControls(restarted, state, AsyncMock())
    assert restarted.paused is False
    assert runtime.paused is True  # Current process remains drained until exit.


async def test_disconnect_preserves_an_explicit_owner_pause(tmp_path):
    runtime = Mock(
        settings=settings(tmp_path, disconnect_grace_seconds=0, stop_on_disconnect=True)
    )
    runtime.lock = threading.RLock()
    runtime.worker_id = "W-001"
    runtime.containers.return_value = []
    state = StateDirectory(tmp_path)
    state.prepare()
    app = WorkerApplication(runtime, Mock(), Mock(notify_disconnect=AsyncMock()), state)
    app.owner.pause()
    await app.request_disconnect()
    await app.shutdown_task
    from worker_agent.owner import OwnerControls

    restarted = Mock()
    OwnerControls(restarted, state, AsyncMock())
    assert restarted.paused is True
