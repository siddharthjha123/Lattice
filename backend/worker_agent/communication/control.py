"""Private owner controls: Unix socket or authenticated Windows loopback TCP."""

import asyncio
import hmac
import json
import os
import secrets
import stat
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict


class ControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: Literal["pause", "resume", "stop", "list", "status", "disconnect"]


class UnixControlServer:
    def __init__(self, state, handler):
        self.path = state.path / "control.sock"
        self.handler = handler
        self.server = None
        self.inode = None

    async def start(self):
        if len(os.fsencode(self.path)) > 100:
            raise ValueError(
                "STATE_DIR is too long for a local control socket; use a shorter path"
            )
        if self.path.exists() or self.path.is_symlink():
            info = self.path.lstat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
                raise PermissionError(
                    "Refusing to replace a non-worker control socket path"
                )
            self.path.unlink()
        self.server = await asyncio.start_unix_server(
            self._handle, path=self.path, limit=16384
        )
        self.path.chmod(0o600)
        self.inode = self.path.lstat().st_ino

    async def _handle(self, reader, writer):
        try:
            raw = await asyncio.wait_for(reader.readline(), 5)
            request = ControlRequest.model_validate_json(raw)
            data = await self.handler(request.command)
            response = {"success": True, "data": data}
        except Exception as exc:  # noqa: BLE001 -- sanitize the local RPC boundary
            response = {
                "success": False,
                "error": f"Control request failed ({type(exc).__name__})",
            }
        try:
            writer.write(json.dumps(response).encode() + b"\n")
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def close(self):
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
            try:
                info = self.path.lstat()
                if info.st_ino == self.inode and stat.S_ISSOCK(info.st_mode):
                    self.path.unlink()
            except FileNotFoundError:
                pass


async def _send_unix_control(state, command):
    request = ControlRequest(command=command)
    reader, writer = await asyncio.open_unix_connection(
        state.path / "control.sock", limit=1048576
    )
    try:
        writer.write(request.model_dump_json().encode() + b"\n")
        await writer.drain()
        return json.loads(await asyncio.wait_for(reader.readline(), timeout=120))
    finally:
        writer.close()
        await writer.wait_closed()


class WindowsControlServer:
    """Loopback-only RPC; an ACL-protected random capability guards every call."""

    def __init__(self, state, handler):
        self.state = state
        self.handler = handler
        self.server = None
        self.token = secrets.token_urlsafe(32)
        self.instance = uuid4().hex

    async def start(self):
        self.server = await asyncio.start_server(
            self._handle, host="127.0.0.1", port=0, limit=16384, start_serving=False
        )
        try:
            port = self.server.sockets[0].getsockname()[1]
            self.state.write_json(
                "control.json",
                {"port": port, "token": self.token, "instance": self.instance},
            )
            await self.server.start_serving()
        except BaseException:
            await self.close()
            raise

    async def _handle(self, reader, writer):
        try:
            value = json.loads(await asyncio.wait_for(reader.readline(), 5))
            if not isinstance(value, dict) or set(value) != {"token", "request"}:
                raise PermissionError("Invalid owner request")
            token = value["token"]
            if not isinstance(token, str) or not hmac.compare_digest(token, self.token):
                raise PermissionError("Owner authentication required")
            request = ControlRequest.model_validate(value["request"])
            response = {"success": True, "data": await self.handler(request.command)}
        except Exception as error:  # noqa: BLE001 -- never echo local capability/input
            response = {
                "success": False,
                "error": "Control request failed (" + type(error).__name__ + ")",
            }
        try:
            writer.write(json.dumps(response).encode() + b"\n")
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def close(self):
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
        try:
            saved = self.state.read_json("control.json")
            if saved.get("instance") == self.instance:
                (self.state.path / "control.json").unlink(missing_ok=True)
        except FileNotFoundError:
            pass


ControlServer = WindowsControlServer if os.name == "nt" else UnixControlServer


async def send_control(state, command):
    if os.name != "nt":
        return await _send_unix_control(state, command)
    state.prepare()
    endpoint = state.read_json("control.json")
    port, token = endpoint.get("port"), endpoint.get("token")
    if (
        type(port) is not int
        or not 1 <= port <= 65535
        or not isinstance(token, str)
        or len(token) < 40
    ):
        raise ValueError("Invalid private owner endpoint")
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection("127.0.0.1", port, limit=1048576), 10
    )
    try:
        writer.write(
            json.dumps(
                {
                    "token": token,
                    "request": ControlRequest(command=command).model_dump(),
                }
            ).encode()
            + b"\n"
        )
        await writer.drain()
        return json.loads(await asyncio.wait_for(reader.readline(), 120))
    finally:
        writer.close()
        await writer.wait_closed()
