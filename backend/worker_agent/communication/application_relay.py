"""Outbound HTTP relay restricted to this worker's running owned containers."""

import asyncio
import logging
from uuid import UUID

import httpx
from shared.relay import (
    BODY_LIMIT,
    FRAME_LIMIT,
    HOP_HEADERS,
    RelayRequest,
    RelayResponse,
    decode_body,
    encode_body,
)
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake

from worker_agent.security.auth import authentication_headers

LOGGER = logging.getLogger(__name__)


class WorkerApplicationRelay:
    def __init__(self, application):
        self.application = application
        self.runtime = application.runtime
        self.settings = application.settings

    async def exchange(self, message, client):
        if not self.runtime.lease_valid:
            raise PermissionError("Execution lease expired")
        inspection = await asyncio.to_thread(
            self.runtime.inspect, message.container_id, False
        )
        if (
            UUID(inspection.deployment_id) != message.deployment_id
            or inspection.status != "running"
        ):
            raise PermissionError("Relay target is not a running owned deployment")
        binding = next(
            (
                item
                for item in inspection.ports.get(f"{message.internal_port}/tcp", [])
                or []
                if item.get("HostIp") in {"127.0.0.1", "0.0.0.0", "::", "::1", ""}
            ),
            None,
        )
        if binding is None:
            raise PermissionError("No permitted local application binding")
        port = int(binding["HostPort"])
        if not 1 <= port <= 65535:
            raise ValueError("Invalid local application port")
        headers = [(k, v) for k, v in message.headers if k.lower() not in HOP_HEADERS]
        url = httpx.URL(
            scheme="http",
            host="127.0.0.1",
            port=port,
            path=message.path,
            query=message.query.encode() or None,
        )
        async with client.stream(
            message.method, url, headers=headers, content=decode_body(message.body)
        ) as response:
            body = bytearray()
            async for chunk in response.aiter_raw():
                body.extend(chunk)
                if len(body) > BODY_LIMIT:
                    raise ValueError("Application response exceeds 4 MiB relay limit")
            return RelayResponse(
                request_id=message.request_id,
                status=response.status_code,
                headers=[
                    (k, v)
                    for k, v in response.headers.multi_items()
                    if k.lower() not in HOP_HEADERS
                ],
                body=encode_body(bytes(body)),
            )

    async def session(self, socket, stop, session_id):
        tasks = set()
        send_lock = asyncio.Lock()
        async with httpx.AsyncClient(
            timeout=20, trust_env=False, follow_redirects=False
        ) as client:

            async def handle(message):
                try:
                    response = await self.exchange(message, client)
                except Exception:  # noqa: BLE001 -- return no Docker/credential/host details to visitors
                    response = RelayResponse(
                        request_id=message.request_id,
                        status=502,
                        headers=[("content-type", "text/plain")],
                        body=encode_body(b"Application unavailable"),
                    )
                async with send_lock:
                    await socket.send(response.model_dump_json())

            async def receive():
                async for raw in socket:
                    message = RelayRequest.model_validate_json(raw)
                    if len(tasks) >= 16:
                        response = RelayResponse(
                            request_id=message.request_id,
                            status=503,
                            body=encode_body(b"Application relay busy"),
                        )
                        async with send_lock:
                            await socket.send(response.model_dump_json())
                        continue
                    task = asyncio.create_task(handle(message))
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)
                    task.add_done_callback(
                        lambda done: done.exception() if not done.cancelled() else None
                    )

            async def watch_session():
                while not stop.is_set():
                    if (
                        not self.application.gateway.connected.is_set()
                        or str(self.application.lifecycle.lease_id) != session_id
                    ):
                        return
                    await asyncio.sleep(0.25)

            watching = asyncio.create_task(watch_session())
            reader = asyncio.create_task(receive())
            stopping = asyncio.create_task(stop.wait())
            try:
                done, _ = await asyncio.wait(
                    [reader, stopping, watching], return_when=asyncio.FIRST_COMPLETED
                )
                if reader in done:
                    await reader
            finally:
                watching.cancel()
                reader.cancel()
                stopping.cancel()
                for task in tasks:
                    task.cancel()
                await asyncio.gather(
                    reader, stopping, watching, *tasks, return_exceptions=True
                )

    async def run(self, stop):
        while not stop.is_set():
            app = self.application
            if (
                not app.gateway.connected.is_set()
                or not app.runtime.lease_valid
                or app.lifecycle.lease_id is None
            ):
                try:
                    await asyncio.wait_for(stop.wait(), 0.5)
                except TimeoutError:
                    pass
                continue
            session_id = str(app.lifecycle.lease_id)
            headers = authentication_headers(
                self.runtime.worker_id, self.settings.worker_token
            ) | {"X-Worker-Session": session_id}
            try:
                async with connect(
                    self.settings.websocket_url + "/apps",
                    additional_headers=headers,
                    max_size=FRAME_LIMIT,
                    max_queue=16,
                    compression=None,
                    proxy=None,
                    open_timeout=10,
                    close_timeout=3,
                    ping_interval=20,
                    ping_timeout=20,
                    logger=logging.getLogger("worker_agent.app_transport"),
                ) as socket:
                    LOGGER.info("Application relay connected")
                    await self.session(socket, stop, session_id)
            except (
                OSError,
                TimeoutError,
                ConnectionClosed,
                InvalidHandshake,
                ValueError,
            ):
                LOGGER.info("Application relay unavailable; reconnecting")
            if not stop.is_set():
                try:
                    await asyncio.wait_for(stop.wait(), 2)
                except TimeoutError:
                    pass
