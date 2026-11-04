"""Bounded HTTP multiplexing, correlated to a live control session and socket."""

import asyncio
from dataclasses import dataclass

from shared.relay import FRAME_LIMIT, RelayResponse


@dataclass
class RelaySocket:
    socket: object
    session_id: str
    send_lock: asyncio.Lock


class ApplicationRelay:
    def __init__(self, gateway):
        self.gateway = gateway
        self.sockets = {}
        self.pending = {}

    def connected(self, worker_id):
        record = self.sockets.get(worker_id)
        return bool(
            record
            and self.gateway.is_worker_connected(worker_id)
            and str(self.gateway.sessions.get(worker_id)) == record.session_id
        )

    async def attach(self, worker_id, session_id, socket):
        previous = self.sockets.get(worker_id)
        await socket.accept()
        record = RelaySocket(socket, session_id, asyncio.Lock())
        self.sockets[worker_id] = record
        if previous:
            await previous.socket.close(code=1000, reason="Application relay replaced")
        return record

    def detach(self, worker_id, record):
        if self.sockets.get(worker_id) is record:
            self.sockets.pop(worker_id, None)
        for key, (owner, bound, future) in list(self.pending.items()):
            if owner == worker_id and bound is record and not future.done():
                future.set_exception(ConnectionError("Application relay disconnected"))

    def receive(self, worker_id, record, raw):
        if self.sockets.get(worker_id) is not record or not self.connected(worker_id):
            raise PermissionError("Stale application relay")
        if len(raw.encode()) > FRAME_LIMIT:
            raise ValueError("Application response exceeds relay frame limit")
        response = RelayResponse.model_validate_json(raw)
        pending = self.pending.get(response.request_id)
        if pending is None:
            return  # Timed-out response; never associate it with another caller.
        owner, bound, future = pending
        if owner != worker_id or bound is not record:
            raise PermissionError("Application response belongs to another socket")
        if not future.done():
            future.set_result(response)

    async def request(self, worker_id, message, timeout=25):
        if not self.connected(worker_id):
            raise ConnectionError("Worker application relay is not connected")
        record = self.sockets[worker_id]
        if (
            sum(owner == worker_id for owner, _, _ in self.pending.values()) >= 16
            or len(self.pending) >= 256
        ):
            raise ConnectionError("Application relay is busy")
        future = asyncio.get_running_loop().create_future()
        self.pending[message.request_id] = (worker_id, record, future)
        try:
            async with record.send_lock:
                await asyncio.wait_for(
                    record.socket.send_text(message.model_dump_json()), timeout=5
                )
            return await asyncio.wait_for(future, timeout)
        finally:
            self.pending.pop(message.request_id, None)
            if not future.done():
                future.cancel()
            elif not future.cancelled():
                future.exception()

    async def close(self):
        for worker_id, record in list(self.sockets.items()):
            await record.socket.close(code=1001, reason="Controller shutting down")
            self.detach(worker_id, record)
