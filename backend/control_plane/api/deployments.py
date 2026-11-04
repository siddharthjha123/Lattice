"""Versioned deployments, bounded logs and truthful stop/redeploy actions."""

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict
from shared.contracts import BoxCreationRequest
from shared.contracts import Deployment as DeploymentContract
from shared.enums import ApplicationType

from control_plane.database.models import (
    Box,
    Deployment,
    DeploymentEvent,
    DeploymentLog,
    Replica,
    ResourceReservation,
)
from control_plane.services.auth import require_admin
from control_plane.services.contracts import aware, scheduling_context
from control_plane.services.git_builder import (
    ApplicationConfig,
    validate_repository_url,
)
from control_plane.services.orchestrator_client import orchestrator_client

router = APIRouter(
    prefix="/api/deployments",
    tags=["deployments"],
    dependencies=[Depends(require_admin)],
)


class DeploymentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    repository_url: str
    branch: str = "main"
    application_type: ApplicationType
    box_id: UUID
    application_config: dict = {}


def contract(row):
    return DeploymentContract(
        deployment_id=row.deployment_id,
        box_id=row.box_id,
        repository_url=row.repository_url,
        branch=row.branch,
        application_type=row.application_type,
        image_reference=row.image_reference,
        status=row.status,
        public_url=row.public_url,
        created_at=aware(row.created_at),
    )


async def enqueue(payload, ctx, previous=None):
    try:
        validate_repository_url(payload.repository_url, ctx.config)
        ApplicationConfig.model_validate(payload.application_config)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    if not ctx.config.REGISTRY_URL:
        raise HTTPException(
            503, "Configure REGISTRY_URL for actual worker image distribution"
        )
    identity = uuid4()

    def create(session):
        workers, reservations, active_ids = scheduling_context(session, lock=True)
        box = session.get(Box, payload.box_id)
        if box is None or box.deleted_at is not None:
            raise HTTPException(404, "Box not found")
        if box.deployment_id is not None:
            raise HTTPException(409, "Box is already claimed by another deployment")
        own = [item for item in reservations if item.box_id == box.box_id]
        if not own:
            request = BoxCreationRequest(
                **{
                    field: getattr(box, field)
                    for field in BoxCreationRequest.model_fields
                }
            )
            try:
                plan = orchestrator_client.create_box_placement(
                    request,
                    workers,
                    reservations,
                    box_id=box.box_id,
                    active_reservation_ids=active_ids,
                    application_type=payload.application_type,
                )
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from None
            box.primary_worker_id, box.standby_worker_id = (
                plan.primary_worker_id,
                plan.standby_worker_id,
            )
            for hold in plan.reservations:
                session.add(ResourceReservation(**hold.model_dump()))
        deployment = Deployment(
            deployment_id=identity,
            box_id=box.box_id,
            repository_url=payload.repository_url,
            branch=payload.branch,
            application_type=payload.application_type.value,
            application_config=payload.application_config,
            previous_deployment_id=previous,
            image_reference=ctx.builder.distribution_tag(identity),
            status="queued",
        )
        box.deployment_id = identity
        session.add(deployment)
        session.flush()
        session.add(
            DeploymentEvent(
                deployment_id=identity,
                event_type="status_transition",
                to_status="queued",
                message="Deployment queued",
            )
        )
        return contract(deployment)

    result = await ctx.db.run(create)
    ctx.manager.schedule(identity)
    return result


@router.post("", response_model=DeploymentContract, status_code=201)
async def create_deployment(payload: DeploymentCreateRequest, request: Request):
    return await enqueue(payload, request.app.state.context)


@router.get("", response_model=list[DeploymentContract])
async def list_deployments(request: Request):
    return await request.app.state.context.db.run(
        lambda session: [
            contract(row)
            for row in session.query(Deployment).order_by(Deployment.created_at.desc())
        ]
    )


def find(session, identity):
    row = session.get(Deployment, identity)
    if row is None:
        raise HTTPException(404, "Deployment not found")
    return row


@router.get("/{deployment_id}", response_model=DeploymentContract)
async def get_deployment(deployment_id: UUID, request: Request):
    return await request.app.state.context.db.run(
        lambda session: contract(find(session, deployment_id))
    )


@router.get("/{deployment_id}/logs")
async def get_logs(deployment_id: UUID, request: Request, limit: int = 500):
    if not 1 <= limit <= 2000:
        raise HTTPException(422, "Log limit must be between 1 and 2000")

    def logs(session):
        find(session, deployment_id)
        rows = (
            session.query(DeploymentLog)
            .filter_by(deployment_id=deployment_id)
            .order_by(DeploymentLog.id.desc())
            .limit(limit)
            .all()
        )
        return {
            "deployment_id": str(deployment_id),
            "logs": [
                {
                    "timestamp": aware(row.timestamp),
                    "log_level": row.log_level,
                    "message": row.message,
                    "container_id": row.container_id,
                }
                for row in reversed(rows)
            ],
        }

    return await request.app.state.context.db.run(logs)


@router.get("/{deployment_id}/status")
async def get_status(deployment_id: UUID, request: Request):
    def status(session):
        deployment = find(session, deployment_id)
        return {
            "deployment_id": deployment_id,
            "status": deployment.status,
            "public_url": deployment.public_url,
            "stop_requested": deployment.stop_requested,
            "failure_message": deployment.failure_message,
            "created_at": aware(deployment.created_at),
            "updated_at": aware(deployment.updated_at),
            "replicas": [
                {
                    "replica_id": row.replica_id,
                    "worker_id": row.worker_id,
                    "container_id": row.container_id,
                    "role": row.role,
                    "status": row.status,
                    "container_status": row.container_status,
                    "health": row.health,
                    "internal_port": row.internal_port,
                    "port_bindings": row.port_bindings,
                }
                for row in session.query(Replica).filter_by(deployment_id=deployment_id)
            ],
        }

    return await request.app.state.context.db.run(status)


@router.post("/{deployment_id}/stop")
async def stop(deployment_id: UUID, request: Request, response: Response):
    ctx = request.app.state.context
    await ctx.db.run(lambda session: find(session, deployment_id))
    complete = await ctx.manager.stop_deployment(deployment_id)
    response.status_code = 200 if complete else 202
    return {
        "deployment_id": str(deployment_id),
        "status": "stopped" if complete else "stopping",
    }


@router.post("/{deployment_id}/redeploy", status_code=201)
async def redeploy(deployment_id: UUID, request: Request):
    ctx = request.app.state.context

    def previous(session):
        row = find(session, deployment_id)
        return DeploymentCreateRequest(
            repository_url=row.repository_url,
            branch=row.branch,
            application_type=row.application_type,
            box_id=row.box_id,
            application_config=row.application_config,
        )

    payload = await ctx.db.run(previous)
    if not await ctx.manager.stop_deployment(deployment_id):
        raise HTTPException(409, "Previous version has not confirmed shutdown yet")
    return await enqueue(payload, ctx, previous=deployment_id)
