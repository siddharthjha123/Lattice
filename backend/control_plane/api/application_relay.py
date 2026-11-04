"""Worker-initiated application socket, independent of the command channel."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from control_plane.services.auth import bearer

router = APIRouter()


@router.websocket("/ws/workers/apps")
async def application_socket(socket: WebSocket):
    ctx = socket.app.state.context
    worker_id = await ctx.gateway.authenticate_worker(
        bearer(socket.headers), socket.headers.get("x-worker-id")
    )
    session_id = socket.headers.get("x-worker-session", "")
    if (
        worker_id is None
        or not ctx.gateway.is_worker_connected(worker_id)
        or not session_id
        or str(ctx.gateway.sessions.get(worker_id)) != session_id
    ):
        await socket.close(code=1008, reason="Current worker session required")
        return
    record = await ctx.relay.attach(worker_id, session_id, socket)
    try:
        while True:
            ctx.relay.receive(worker_id, record, await socket.receive_text())
    except WebSocketDisconnect:
        pass
    except (ValueError, PermissionError):
        await socket.close(code=1008, reason="Invalid application relay response")
    finally:
        ctx.relay.detach(worker_id, record)
