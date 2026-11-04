"""One authenticated, session-bound gateway connection per worker."""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from control_plane.services.auth import bearer

router = APIRouter()
LOGGER = logging.getLogger(__name__)


@router.websocket("/ws/workers")
async def worker_websocket_endpoint(socket: WebSocket):
    gateway = socket.app.state.context.gateway
    worker_id = await gateway.authenticate_worker(
        bearer(socket.headers), socket.headers.get("x-worker-id")
    )
    if worker_id is None or socket.headers.get("x-worker-lease-enforced") != "true":
        await socket.close(
            code=1008, reason="Worker authentication or lease policy rejected"
        )
        return
    try:
        await gateway.connect(worker_id, socket)
        while True:
            raw = await socket.receive_text()
            if len(raw.encode()) > 1048576:
                raise ValueError("Worker message exceeds size limit")
            await gateway.handle_worker_message(worker_id, raw, socket)
    except WebSocketDisconnect:
        pass
    except (ValueError, PermissionError, ValidationError):
        await socket.close(code=1008, reason="Invalid or unauthorized worker message")
    except Exception as exc:  # noqa: BLE001 -- contain per-session transport failures
        LOGGER.warning("Worker session failed (%s)", type(exc).__name__)
    finally:
        await gateway.disconnect(worker_id, socket)
