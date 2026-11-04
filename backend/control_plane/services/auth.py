"""Management authorization and worker-scoped token verification."""

import hashlib
import hmac
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

management_bearer = HTTPBearer(auto_error=False, scheme_name="ManagementBearer")


def generate_worker_token():
    return "lattice_wk_" + secrets.token_urlsafe(32)


def hash_token(token, config=None):
    if config is None:
        from control_plane.config import settings

        config = settings
    if len(config.SECRET_KEY) < 32:
        raise RuntimeError("SECRET_KEY must contain at least 32 characters")
    return hmac.new(
        config.SECRET_KEY.encode(), token.encode(), hashlib.sha256
    ).hexdigest()


def verify_token(token, stored_hash, config=None):
    return hmac.compare_digest(hash_token(token, config), stored_hash)


def bearer(headers):
    value = headers.get("authorization", "")
    if value.lower().startswith("bearer "):
        return value[7:].strip()
    return headers.get("x-worker-token", "")


def require_admin(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(management_bearer)
    ],
):
    configured = request.app.state.context.config.ADMIN_TOKEN.get_secret_value()
    if len(configured) < 32:
        raise HTTPException(
            503, "Configure a strong ADMIN_TOKEN before management access"
        )
    token = credentials.credentials if credentials is not None else ""
    if not hmac.compare_digest(token, configured):
        raise HTTPException(401, "Management authorization required")


def authorize_worker(session, worker_id, headers, config, *, allow_admin=False):
    from control_plane.database.models import Worker

    worker = session.get(Worker, worker_id)
    if worker is None or worker.deleted_at is not None:
        raise HTTPException(404, "Worker not found")
    token = bearer(headers)
    admin = config.ADMIN_TOKEN.get_secret_value()
    if allow_admin and len(admin) >= 32 and hmac.compare_digest(token, admin):
        return worker
    if (
        headers.get("x-worker-id") != worker_id
        or not token
        or not verify_token(token, worker.token_hash, config)
    ):
        raise HTTPException(401, "Worker authentication rejected")
    return worker
