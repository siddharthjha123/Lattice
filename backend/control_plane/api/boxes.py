"""Transactional Box reservations using the real Orchestrator service."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from shared.contracts import Box as BoxContract
from shared.contracts import BoxCreationRequest

from control_plane.database.models import Box, Pool, ResourceReservation, Worker
from control_plane.services.auth import require_admin
from control_plane.services.contracts import box_contract, scheduling_context
from control_plane.services.orchestrator_client import orchestrator_client

router = APIRouter(
    prefix="/api/boxes", tags=["boxes"], dependencies=[Depends(require_admin)]
)


class PoolBoxCreationRequest(BoxCreationRequest):
    pool_id: UUID | None = None


@router.post("", response_model=BoxContract, status_code=201)
async def create_box(payload: PoolBoxCreationRequest, request: Request):
    identity = uuid4()

    def create(session):
        if payload.pool_id is not None:
            pool = (
                session.query(Pool)
                .filter_by(pool_id=payload.pool_id)
                .with_for_update()
                .first()
            )
            if pool is None or pool.deleted_at is not None:
                raise HTTPException(404, "Pool not found")
        members = (
            session.query(Worker)
            .filter(
                Worker.worker_id.in_(payload.eligible_worker_ids),
                Worker.deleted_at.is_(None),
            )
            .all()
        )
        if len(members) != len(payload.eligible_worker_ids) or any(
            w.pool_id != payload.pool_id for w in members
        ):
            raise HTTPException(
                400, "Every eligible worker must belong to the selected pool"
            )
        if payload.pool_id is not None and any(
            not request.app.state.context.gateway.is_worker_connected(w.worker_id)
            or not request.app.state.context.relay.connected(w.worker_id)
            for w in members
        ):
            raise HTTPException(
                400,
                "Selected pool workers must have live control and application relay connections",
            )
        workers, reservations, active_ids = scheduling_context(
            session, lock=True, pool_id=payload.pool_id
        )
        try:
            decision = orchestrator_client.create_box_placement(
                payload,
                workers,
                reservations,
                box_id=identity,
                active_reservation_ids=active_ids,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        box = Box(
            box_id=identity,
            **payload.model_dump(),
            status="available",
            primary_worker_id=decision.primary_worker_id,
            standby_worker_id=decision.standby_worker_id,
        )
        session.add(box)
        session.flush()
        for reservation in decision.reservations:
            session.add(ResourceReservation(**reservation.model_dump()))
        session.flush()
        return box_contract(box)

    return await request.app.state.context.db.run(create)


@router.get("", response_model=list[BoxContract])
async def list_boxes(request: Request):
    return await request.app.state.context.db.run(
        lambda session: [
            box_contract(row)
            for row in session.query(Box).filter(Box.deleted_at.is_(None))
        ]
    )


@router.get("/{box_id}", response_model=BoxContract)
async def get_box(box_id: UUID, request: Request):
    def read(session):
        box = session.get(Box, box_id)
        if box is None or box.deleted_at is not None:
            raise HTTPException(404, "Box not found")
        return box_contract(box)

    return await request.app.state.context.db.run(read)


@router.delete("/{box_id}")
async def delete_box(box_id: UUID, request: Request):
    def remove(session):
        scheduling_context(session, lock=True)
        box = session.get(Box, box_id)
        if box is None or box.deleted_at is not None:
            raise HTTPException(404, "Box not found")
        if box.deployment_id is not None:
            raise HTTPException(
                409, "Stop and confirm the deployment before deleting its Box"
            )
        session.query(ResourceReservation).filter_by(box_id=box_id).delete()
        box.deleted_at = datetime.now(UTC)
        return {"box_id": str(box_id), "status": "deleted"}

    return await request.app.state.context.db.run(remove)
