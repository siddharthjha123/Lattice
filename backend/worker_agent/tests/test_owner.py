import tempfile
import threading
from pathlib import Path
from unittest.mock import AsyncMock, Mock

from worker_agent.communication.control import ControlServer, send_control
from worker_agent.owner import OwnerControls
from worker_agent.state import StateDirectory


def test_pause_and_resume_are_real_operations_and_persist(tmp_path):
    runtime = Mock()
    runtime.lock = threading.RLock()
    running, paused = Mock(status="running", id="one"), Mock(status="paused", id="two")
    runtime.containers.return_value = [running, paused]
    state = StateDirectory(tmp_path)
    state.prepare()
    controls = OwnerControls(runtime, state, AsyncMock())
    assert controls.pause()["paused"]
    running.pause.assert_called_once()
    assert state.read_json("owner.json")["paused"]
    assert OwnerControls(runtime, state, AsyncMock()).runtime.paused
    assert controls.resume()["paused"] is False
    paused.unpause.assert_called_once()


async def test_local_owner_socket_is_private_and_returns_results():
    with tempfile.TemporaryDirectory(prefix="lattice-control-", dir="/tmp") as directory:
        state = StateDirectory(Path(directory))
        state.prepare()
        handler = AsyncMock(return_value={"paused": True})
        server = ControlServer(state, handler)
        await server.start()
        try:
            assert server.path.stat().st_mode & 0o777 == 0o600
            response = await send_control(state, "pause")
            assert response == {"success": True, "data": {"paused": True}}
            handler.assert_awaited_once_with("pause")
        finally:
            await server.close()
        assert not server.path.exists()


def test_status_reports_owner_state_when_docker_inspection_fails(tmp_path):
    from docker.errors import APIError

    state = StateDirectory(tmp_path)
    state.prepare()
    runtime = Mock(lease_valid=True, draining=False, storage_errors=[])
    runtime.admission_blockers.return_value = []
    runtime.containers.side_effect = APIError("private daemon error content")
    controls = OwnerControls(runtime, state, AsyncMock())
    result = controls.status()
    assert result["paused"] is False
    assert result["docker_available"] is False
    assert result["docker_error_type"] == "APIError"
    assert result["admission_blockers"] == ["docker_unavailable"]
    assert "private daemon error content" not in repr(result)
