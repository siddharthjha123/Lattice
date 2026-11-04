"""Public HTTP routing to the current verified primary via its outbound relay."""

from http.cookies import SimpleCookie
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from shared.relay import BODY_LIMIT, HOP_HEADERS, decode_body

from control_plane.database.models import Deployment, Replica, Worker
from control_plane.services.application_http import application_http

router = APIRouter()


@router.api_route(
    "/apps/{deployment_id}", methods=["GET", "HEAD"], include_in_schema=False
)
async def application_slash(deployment_id: UUID, request: Request):
    suffix = "?" + request.url.query if request.url.query else ""
    return RedirectResponse(f"/apps/{deployment_id}/" + suffix, status_code=307)


@router.api_route(
    "/apps/{deployment_id}/{path:path}",
    methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    include_in_schema=False,
)
async def application_proxy(deployment_id: UUID, path: str, request: Request):
    ctx = request.app.state.context

    def target(session):
        deployment = session.get(Deployment, deployment_id)
        if deployment is None:
            raise HTTPException(404, "Application not found")
        if deployment.status != "running" or deployment.stop_requested:
            raise HTTPException(503, "Application is not ready")
        replica = (
            session.query(Replica)
            .filter_by(deployment_id=deployment_id, role="primary", status="running")
            .order_by(Replica.created_at.desc())
            .first()
        )
        if replica is None:
            raise HTTPException(503, "No healthy primary")
        worker = session.get(Worker, replica.worker_id)
        if (
            worker is None
            or worker.draining
            or worker.status != "online"
            or not ctx.gateway.is_worker_connected(worker.worker_id)
        ):
            raise HTTPException(503, "Primary worker is unavailable")
        binding = next(
            (
                item
                for item in replica.port_bindings
                if item["internal_port"] == replica.internal_port
                and item["protocol"] == "tcp"
            ),
            None,
        )
        if binding is None or not replica.container_id:
            raise HTTPException(503, "No verified application binding")
        return (
            worker.worker_id,
            worker.application_transport,
            worker.address,
            binding["host_port"],
            replica.container_id,
            replica.internal_port,
        )

    worker_id, transport, address, port, container_id, internal_port = await ctx.db.run(
        target
    )
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > BODY_LIMIT:
            raise HTTPException(413, "Application request exceeds 4 MiB")
    connection_headers = {
        name.strip().lower()
        for name in request.headers.get("connection", "").split(",")
    }
    excluded = (
        HOP_HEADERS
        | connection_headers
        | {
            "x-worker-id",
            "x-worker-token",
            "x-worker-session",
            "x-worker-lease-id",
            "x-forwarded-for",
            "x-forwarded-host",
            "x-forwarded-proto",
            "x-forwarded-prefix",
        }
    )
    headers = [
        (key, value)
        for key, value in request.headers.items()
        if key.lower() not in excluded
        and not (
            key.lower() == "authorization"
            and value == "Bearer " + ctx.config.ADMIN_TOKEN.get_secret_value()
        )
    ]
    prefix = (
        "" if request.scope.get("lattice.app_hostname") else f"/apps/{deployment_id}"
    )
    headers += [
        ("x-forwarded-prefix", prefix),
        (
            "x-forwarded-proto",
            "https" if ctx.config.PUBLIC_BASE_URL.startswith("https:") else "http",
        ),
        ("x-forwarded-host", request.headers.get("host", "")),
    ]
    try:
        result = await application_http(
            ctx,
            worker_id,
            transport,
            address,
            port,
            deployment_id,
            container_id,
            internal_port,
            request.method,
            "/" + path,
            request.url.query,
            headers,
            bytes(body),
        )
    except TimeoutError:
        raise HTTPException(504, "Application relay timed out") from None
    except Exception:  # noqa: BLE001 -- never expose worker addresses or credentials to visitors
        raise HTTPException(502, "Application connection failed") from None
    response = Response(content=decode_body(result.body), status_code=result.status)
    response_headers = []
    connection_tokens = {
        name.strip().lower()
        for k, v in result.headers
        if k.lower() == "connection"
        for name in v.split(",")
    }
    for key, value in result.headers:
        lower = key.lower()
        if lower in HOP_HEADERS | connection_tokens | {"content-length"}:
            continue
        if (
            lower == "location"
            and prefix
            and value.startswith("/")
            and not value.startswith("//")
        ):
            value = prefix + value
        if lower == "set-cookie":
            cookies = SimpleCookie()
            try:
                cookies.load(value)
                for cookie in cookies.values():
                    cookie["domain"] = ""
                    cookie["path"] = prefix + "/" if prefix else "/"
                    if ctx.config.PUBLIC_BASE_URL.startswith("https:"):
                        cookie["secure"] = True
                    response_headers.append(
                        (b"set-cookie", cookie.OutputString().encode("latin-1"))
                    )
            except (ValueError, UnicodeError):
                pass
            continue
        response_headers.append((key.encode("ascii"), value.encode("latin-1")))
    response.raw_headers = response_headers + [
        (b"content-length", str(len(response.body)).encode())
    ]
    return response
