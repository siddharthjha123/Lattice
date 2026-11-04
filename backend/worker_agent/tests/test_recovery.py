import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from shared.contracts import WORKER_MESSAGE_ADAPTER
from websockets.asyncio.server import serve
from worker_agent.communication.client import CommandProcessorError, GatewayClient
from worker_agent.tests.test_config import settings
from worker_agent.tests.test_security import run_command


async def test_gateway_reconnects_after_server_connection_loss(tmp_path):
    stop = asyncio.Event()
    reconnected = asyncio.Future()
    visits = 0

    async def handler(socket):
        nonlocal visits
        visits += 1
        if visits == 1:
            await socket.close(code=1012, reason="Test restart")
        else:
            reconnected.set_result(True)
            await stop.wait()

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        config = settings(
            tmp_path,
            control_plane_url=f"http://127.0.0.1:{port}",
            reconnect_min_seconds=0.05,
            reconnect_max_seconds=0.1,
        )
        reconcile = AsyncMock()
        client = GatewayClient(config, "W-001", Mock(), on_connect=reconcile)
        task = asyncio.create_task(client.run(stop))
        try:
            await asyncio.wait_for(reconnected, 3)
        finally:
            stop.set()
            await asyncio.wait_for(task, 3)
    assert reconcile.await_count >= 2


async def test_journal_failure_terminates_processor_without_hanging_queued_commands(
    tmp_path,
):
    dispatcher = Mock()
    dispatcher.execute.side_effect = OSError("disk full")

    async def handler(socket):
        await socket.send(run_command().model_dump_json())
        await socket.send(run_command().model_dump_json())
        await socket.wait_closed()

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        client = GatewayClient(
            settings(tmp_path, control_plane_url=f"http://127.0.0.1:{port}"),
            "W-001",
            dispatcher,
        )
        with pytest.raises(CommandProcessorError):
            await asyncio.wait_for(client.run(asyncio.Event()), 3)


async def test_malformed_command_is_rejected_without_runtime_execution(tmp_path):
    stop = asyncio.Event()
    response = asyncio.Future()
    command = run_command()
    dispatcher = Mock()

    async def handler(socket):
        await socket.send(
            '{"type":"execute_shell","request_id":"' + str(command.request_id) + '"}'
        )
        response.set_result(WORKER_MESSAGE_ADAPTER.validate_json(await socket.recv()))
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
            result = await asyncio.wait_for(response, 3)
            assert not result.success
        finally:
            stop.set()
            await asyncio.wait_for(task, 3)
    dispatcher.execute.assert_not_called()
