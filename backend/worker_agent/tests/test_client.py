import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from shared.contracts import WORKER_MESSAGE_ADAPTER, CommandResult
from websockets.asyncio.server import serve
from websockets.exceptions import InvalidStatus
from worker_agent.communication.client import GatewayClient
from worker_agent.communication.dispatcher import Execution
from worker_agent.security.auth import WorkerAuthenticationError
from worker_agent.tests.test_config import settings
from worker_agent.tests.test_security import run_command


async def test_real_websocket_authentication_and_command_result(tmp_path):
    stop = asyncio.Event()
    received = asyncio.Future()
    command = run_command()
    dispatcher = Mock()
    dispatcher.execute.return_value = Execution(
        CommandResult(
            request_id=command.request_id,
            success=True,
            container_id="container-1",
            message="Started",
        )
    )

    async def handler(socket):
        assert socket.request.path == "/ws/workers"
        assert socket.request.headers["Authorization"] == "Bearer test-token"
        assert socket.request.headers["X-Worker-ID"] == "W-001"
        await socket.send(command.model_dump_json())
        message = WORKER_MESSAGE_ADAPTER.validate_json(await socket.recv())
        received.set_result(message)
        await stop.wait()

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        client = GatewayClient(
            settings(tmp_path, control_plane_url=f"http://127.0.0.1:{port}"),
            "W-001",
            dispatcher,
        )
        task = asyncio.create_task(client.run(stop))
        try:
            message = await asyncio.wait_for(received, 5)
            assert message.request_id == command.request_id
            assert message.success
        finally:
            stop.set()
            await asyncio.wait_for(task, 5)
    dispatcher.execute.assert_called_once()


async def test_authentication_failure_does_not_retry(tmp_path):
    connector = Mock(side_effect=InvalidStatus(SimpleNamespace(status_code=401)))
    client = GatewayClient(settings(tmp_path), "W-001", Mock(), connector=connector)
    with pytest.raises(WorkerAuthenticationError):
        await client.run(asyncio.Event())
    assert connector.call_count == 1


async def test_stop_interrupts_reconnect_backoff(tmp_path):
    connector = Mock(side_effect=OSError("offline"))
    client = GatewayClient(settings(tmp_path), "W-001", Mock(), connector=connector)
    stop = asyncio.Event()
    task = asyncio.create_task(client.run(stop))
    await asyncio.sleep(0)
    stop.set()
    await asyncio.wait_for(task, 1)
    assert connector.call_count >= 1
