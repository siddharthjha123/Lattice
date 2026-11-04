"""Admin pool management, capability-based joining and live pool inventory."""

import hmac
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from control_plane.api.workers import WorkerRegisterRequest
from control_plane.database.models import Box, Deployment, Pool, Worker
from control_plane.services.auth import hash_token, require_admin
from control_plane.services.contracts import aware, worker_snapshot
from control_plane.services.pools import code_hash, create_pool, new_code, pool_record

router = APIRouter(prefix="/api/pools", tags=["pools"])


class PoolCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=r"^[a-z][a-z0-9-]{2,47}$")
    expires_hours: int = Field(default=24, ge=1, le=168)
    max_joins: int = Field(default=10, ge=1, le=100)


class PoolJoin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pool_name: str = Field(pattern=r"^[a-z][a-z0-9-]{2,47}$")
    pool_code: SecretStr = Field(min_length=16, max_length=128)
    worker_token: SecretStr = Field(min_length=40, max_length=128)
    worker: WorkerRegisterRequest


@router.post("", status_code=201, dependencies=[Depends(require_admin)])
async def make_pool(payload: PoolCreate, request: Request):
    ctx = request.app.state.context
    return await ctx.db.run(
        lambda s: create_pool(
            s,
            payload.name,
            ctx.config,
            hours=payload.expires_hours,
            max_joins=payload.max_joins,
        )
    )


@router.get("", dependencies=[Depends(require_admin)])
async def list_pools(request: Request):
    return await request.app.state.context.db.run(
        lambda s: [
            pool_record(p)
            for p in s.query(Pool).filter(Pool.deleted_at.is_(None)).order_by(Pool.name)
        ]
    )


@router.post("/{pool_id}/rotate-code", dependencies=[Depends(require_admin)])
async def rotate_code(pool_id: UUID, request: Request):
    ctx = request.app.state.context
    code = new_code()

    def rotate(session):
        pool = session.query(Pool).filter_by(pool_id=pool_id).with_for_update().first()
        if pool is None or pool.deleted_at is not None:
            raise HTTPException(404, "Pool not found")
        pool.code_hash = code_hash(pool.name, code, ctx.config)
        pool.code_expires_at = datetime.now(UTC) + timedelta(hours=24)
        pool.joins_used = 0
        return pool_record(pool) | {"pool_code": code}

    return await ctx.db.run(rotate)


@router.post("/join")
async def join_pool(payload: PoolJoin, request: Request):
    ctx = request.app.state.context
    ctx.join_limiter.check(request.client.host if request.client else "unknown")
    token = payload.worker_token.get_secret_value()
    if any(not 33 <= ord(c) <= 126 for c in token):
        raise HTTPException(422, "Invalid worker credential")
    try:
        snapshot = payload.worker.snapshot()
    except ValueError:
        raise HTTPException(422, "Invalid worker hardware or limits") from None

    def enroll(session):
        pool = (
            session.query(Pool)
            .filter_by(name=payload.pool_name)
            .with_for_update()
            .first()
        )
        expected = code_hash(
            payload.pool_name, payload.pool_code.get_secret_value(), ctx.config
        )
        if (
            pool is None
            or pool.deleted_at is not None
            or not hmac.compare_digest(pool.code_hash, expected)
            or aware(pool.code_expires_at) <= datetime.now(UTC)
        ):
            raise HTTPException(403, "Invalid or expired pool name/code")
        digest = hash_token(token, ctx.config)
        old = session.get(Worker, snapshot.worker_id)
        if old is not None:
            if old.deleted_at is not None:
                raise HTTPException(
                    409,
                    "Worker enrollment was deleted; use a new state directory to enroll a new identity",
                )
            if old.pool_id != pool.pool_id or not hmac.compare_digest(
                old.token_hash, digest
            ):
                raise HTTPException(
                    409, "Worker identity already belongs to another enrollment"
                )
            return {
                "pool_id": str(pool.pool_id),
                "pool_name": pool.name,
                "worker_id": old.worker_id,
            }
        if pool.joins_used >= pool.max_joins:
            raise HTTPException(
                403, "Pool join-code limit reached; ask its administrator"
            )
        values = snapshot.model_dump(mode="json", exclude={"last_heartbeat"})
        session.add(
            Worker(
                **values,
                token_hash=digest,
                address="127.0.0.1",
                pool_id=pool.pool_id,
                application_transport="relay",
            )
        )
        pool.joins_used += 1
        session.flush()
        return {
            "pool_id": str(pool.pool_id),
            "pool_name": pool.name,
            "worker_id": snapshot.worker_id,
        }

    return await ctx.db.run(enroll)


@router.get("/{pool_id}/status", dependencies=[Depends(require_admin)])
async def pool_status(pool_id: UUID, request: Request):
    ctx = request.app.state.context

    def read(session):
        pool = session.get(Pool, pool_id)
        if pool is None or pool.deleted_at is not None:
            raise HTTPException(404, "Pool not found")
        workers = (
            session.query(Worker)
            .filter_by(pool_id=pool_id, deleted_at=None)
            .order_by(Worker.worker_id)
            .all()
        )
        boxes = session.query(Box).filter_by(pool_id=pool_id).all()
        box_ids = [b.box_id for b in boxes]
        deployments = (
            session.query(Deployment)
            .filter(Deployment.box_id.in_(box_ids))
            .order_by(Deployment.created_at.desc())
            .limit(20)
            .all()
            if box_ids
            else []
        )
        return pool_record(pool) | {
            "workers": [
                worker_snapshot(w).model_dump(mode="json")
                | {
                    "control_connected": ctx.gateway.is_worker_connected(w.worker_id),
                    "application_relay_connected": ctx.relay.connected(w.worker_id),
                    "running_container_ids": w.running_containers,
                }
                for w in workers
            ],
            "deployments": [
                {
                    "deployment_id": str(d.deployment_id),
                    "status": d.status,
                    "public_url": d.public_url,
                    "failure_message": d.failure_message,
                    "containers": [
                        {
                            "container_id": x.container_id,
                            "worker_id": x.worker_id,
                            "status": x.container_status,
                        }
                        for x in d.replicas
                    ],
                }
                for d in deployments
            ],
        }

    return await ctx.db.run(read)


@router.delete("/{pool_id}", status_code=204, dependencies=[Depends(require_admin)])
async def delete_pool(pool_id: UUID, request: Request):
    ctx = request.app.state.context

    def retire(session):
        pool = session.query(Pool).filter_by(pool_id=pool_id).with_for_update().first()
        if pool is None or pool.deleted_at is not None:
            raise HTTPException(404, "Pool not found")
        if session.query(Worker).filter_by(pool_id=pool_id, deleted_at=None).first():
            raise HTTPException(
                409, "Delete this pool's workers before deleting the pool"
            )
        if session.query(Box).filter_by(pool_id=pool_id, deleted_at=None).first():
            raise HTTPException(
                409, "Stop deployments and delete this pool's Boxes first"
            )
        pool.deleted_at = datetime.now(UTC)
        pool.code_expires_at = pool.deleted_at
        pool.code_hash = code_hash(pool.name, new_code(), ctx.config)

    await ctx.db.run(retire)
