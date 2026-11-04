"""Bounded command processing and authenticated, reconnecting WebSockets."""

import asyncio
import json
import logging
import random
import time
from uuid import UUID

from pydantic import ValidationError
from shared.contracts import CommandResult, LeaseGrant
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidStatus

from worker_agent.communication.protocol import decode_control_message, encode_message
from worker_agent.security.auth import WorkerAuthenticationError, authentication_headers

LOGGER = logging.getLogger(__name__)
AUTH_CLOSE_CODES = {1008, 4001, 4003, 4401, 4403}


class CommandProcessorError(RuntimeError):
    """The durable command processor failed; stop rather than hang or retry writes."""


class GatewayClient:
    def __init__(
        self, settings, worker_id, dispatcher, on_connect=None, connector=connect
    ):
        self.settings = settings
        self.worker_id = worker_id
        self.dispatcher = dispatcher
        self.on_connect = on_connect
        self.connector = connector
        self.connected = asyncio.Event()
        self.queue = asyncio.Queue(maxsize=settings.command_queue_size)
        self.socket = None
        self.send_lock = asyncio.Lock()
        self.consumer = None
        self.on_lease = None

    async def send(self, message):
        payload = encode_message(message)
        async with self.send_lock:
            socket = self.socket
            if socket is None:
                raise ConnectionError("Control Plane is disconnected")
            await socket.send(payload)

    async def _consume(self):
        while True:
            command = await self.queue.get()
            try:
                if command is None:
                    return
                execution = await asyncio.to_thread(self.dispatcher.execute, command)
                try:
                    await self.send(execution.result)
                    for event in execution.events:
                        await self.send(event)
                except (ConnectionError, ConnectionClosed):
                    LOGGER.info(
                        "Command result persisted for replay after reconnection"
                    )
            finally:
                self.queue.task_done()

    async def _invalid(self, raw):
        try:
            payload = json.loads(raw)
            request_id = UUID(payload["request_id"])
        except (ValueError, TypeError, KeyError):
            return
        await self.send(
            CommandResult(
                request_id=request_id,
                success=False,
                message="Invalid or unsupported command",
            )
        )

    async def _receive(self, socket):
        invalid_count = 0
        async for raw in socket:
            try:
                command = decode_control_message(raw)
            except ValidationError:
                invalid_count += 1
                LOGGER.warning("Rejected invalid gateway command")
                await self._invalid(raw)
                if invalid_count >= 3:
                    await socket.close(
                        code=1008, reason="Invalid command limit reached"
                    )
                    return
                continue
            if isinstance(command, LeaseGrant):
                if command.worker_id != self.worker_id:
                    raise WorkerAuthenticationError("Lease belongs to another worker")
                if self.on_lease is not None:
                    await self.on_lease(command)
                continue
            await self.queue.put(command)

    async def _session(self, socket, stop):
        self.socket = socket
        self.connected.set()
        receiver = None
        stopping = None
        try:
            if self.on_connect:
                await self.on_connect()
            receiver = asyncio.create_task(self._receive(socket))
            stopping = asyncio.create_task(stop.wait())
            await asyncio.wait(
                [receiver, stopping, self.consumer], return_when=asyncio.FIRST_COMPLETED
            )
            if self.consumer.done():
                raise CommandProcessorError(
                    "Command processor failed"
                ) from self.consumer.exception()
            if receiver.done():
                await receiver
            if socket.close_code in AUTH_CLOSE_CODES:
                raise WorkerAuthenticationError(
                    "Gateway rejected worker authentication or policy"
                )
        finally:
            for task in (receiver, stopping):
                if task is not None:
                    task.cancel()
            await asyncio.gather(
                *(task for task in (receiver, stopping) if task), return_exceptions=True
            )
            self.socket = None
            self.connected.clear()

    async def run(self, stop):
        consumer = asyncio.create_task(self._consume())
        self.consumer = consumer
        delay = self.settings.reconnect_min_seconds
        try:
            while not stop.is_set():
                if consumer.done():
                    raise CommandProcessorError(
                        "Command processor failed"
                    ) from consumer.exception()
                started = time.monotonic()
                try:
                    async with self.connector(
                        self.settings.websocket_url,
                        additional_headers=authentication_headers(
                            self.worker_id, self.settings.worker_token
                        )
                        | {
                            "X-Worker-Lease-Enforced": str(
                                self.settings.require_control_plane_lease
                            ).lower()
                        },
                        open_timeout=self.settings.connect_timeout,
                        close_timeout=5,
                        ping_interval=20,
                        ping_timeout=20,
                        max_size=65536,
                        max_queue=16,
                        compression=None,
                        proxy=None,
                        logger=logging.getLogger("worker_agent.transport"),
                    ) as socket:
                        LOGGER.info("Authenticated gateway connection established")
                        await self._session(socket, stop)
                except InvalidStatus as exc:
                    if exc.response.status_code in {401, 403}:
                        raise WorkerAuthenticationError(
                            "Worker authentication was rejected"
                        ) from None
                    LOGGER.warning(
                        "Gateway handshake rejected (HTTP %s)", exc.response.status_code
                    )
                except ConnectionClosed as exc:
                    if exc.rcvd is not None and exc.rcvd.code in AUTH_CLOSE_CODES:
                        raise WorkerAuthenticationError(
                            "Gateway rejected worker authentication or policy"
                        ) from None
                    LOGGER.info("Gateway connection lost; reconnecting")
                except (OSError, TimeoutError, InvalidHandshake):
                    LOGGER.info("Gateway unavailable; retrying with bounded backoff")
                if time.monotonic() - started >= 2 * self.settings.heartbeat_interval:
                    delay = self.settings.reconnect_min_seconds
                if not stop.is_set():
                    try:
                        await asyncio.wait_for(
                            stop.wait(), timeout=random.uniform(0.8, 1.0) * delay
                        )
                    except TimeoutError:
                        pass
                    delay = min(self.settings.reconnect_max_seconds, delay * 2)
        finally:
            # Drain accepted commands. Never cancel an in-flight Docker thread and
            # then start a conflicting operation while it is still running.
            joining = asyncio.create_task(self.queue.join())
            try:
                await asyncio.wait(
                    [joining, consumer], return_when=asyncio.FIRST_COMPLETED
                )
                if consumer.done():
                    while not self.queue.empty():
                        self.queue.get_nowait()
                        self.queue.task_done()
                    raise CommandProcessorError(
                        "Command processor failed"
                    ) from consumer.exception()
                await self.queue.put(None)
                await consumer
            finally:
                joining.cancel()
                await asyncio.gather(joining, return_exceptions=True)
