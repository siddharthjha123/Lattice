"""Explicit FastAPI application factory for the integrated local backend."""

import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.trustedhost import TrustedHostMiddleware

from control_plane.api.application_relay import router as app_relay
from control_plane.api.boxes import router as boxes
from control_plane.api.deployments import router as deployments
from control_plane.api.downloads import router as downloads
from control_plane.api.pools import router as pools
from control_plane.api.proxy import router as proxy
from control_plane.api.websocket import router as websocket
from control_plane.api.workers import router as workers
from control_plane.config import settings
from control_plane.services.runtime import ServiceContext

LOGGER = logging.getLogger("control_plane")


def create_app(config=None, context=None):
    config = config or settings
    ctx = context or ServiceContext(config)

    @asynccontextmanager
    async def lifespan(app):
        await ctx.start()
        try:
            yield
        finally:
            await ctx.close()

    app = FastAPI(
        title="Lattice",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if config.EXPOSE_API_DOCS else None,
        redoc_url="/redoc" if config.EXPOSE_API_DOCS else None,
        openapi_url="/openapi.json" if config.EXPOSE_API_DOCS else None,
    )
    allowed_hosts = list(config.ALLOWED_HOSTS)
    if config.APP_DOMAIN:
        import re

        from control_plane.services.hostname_routing import (
            ApplicationHostnameMiddleware,
        )

        if not re.fullmatch(r"[a-z0-9]+(?:[a-z0-9.-]*[a-z0-9])?", config.APP_DOMAIN):
            raise ValueError("APP_DOMAIN must be a plain lowercase DNS name")
        allowed_hosts.append("*." + config.APP_DOMAIN)
        app.add_middleware(
            ApplicationHostnameMiddleware,
            domain=config.APP_DOMAIN,
            control_hosts=config.ALLOWED_HOSTS,
        )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    app.state.context = ctx
    if config.CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=config.CORS_ORIGINS,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, exc: RequestValidationError):
        # Do not echo enrollment codes or worker credentials from invalid bodies.
        return JSONResponse(
            {
                "detail": [
                    {"loc": list(e["loc"]), "type": e["type"]} for e in exc.errors()
                ]
            },
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def failed(request: Request, exc: Exception):
        LOGGER.error("Request failed (%s)", type(exc).__name__)
        return JSONResponse({"detail": "Internal server error"}, status_code=500)

    @app.get("/health")
    async def health():
        try:
            await ctx.db.run(lambda session: session.execute(text("SELECT 1")))
        except Exception:  # noqa: BLE001 -- no connection strings in health responses
            return JSONResponse(
                {
                    "status": "unhealthy",
                    "database": "unavailable",
                    "service": "control_plane",
                },
                status_code=503,
            )
        return {
            "status": "healthy",
            "database": "connected",
            "service": "control_plane",
            "connected_workers": len(ctx.gateway.active_connections),
            "timestamp": datetime.now(UTC).isoformat(),
        }

    for router in (
        pools,
        workers,
        boxes,
        deployments,
        websocket,
        app_relay,
        downloads,
        proxy,
    ):
        app.include_router(router)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.HOST, port=settings.PORT, access_log=False)
