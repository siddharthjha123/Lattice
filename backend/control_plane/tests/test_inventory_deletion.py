"""Retirement must not orphan live work or erase deployment history."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import inspect, text
from starlette.websockets import WebSocketDisconnect

from control_plane.database.init_db import init_db
from control_plane.database.models import (
    Box,
    Deployment,
    Pool,
    Replica,
    ResourceReservation,
    Worker,
)
from control_plane.database.session import Database
from control_plane.services.contracts import scheduling_context

from .conftest import PAYLOAD


def pool_and_worker(client, name="delete-trial"):
    pool = client.post("/api/pools", json={"name": name}).json()
    token = "lattice_wk_" + "z" * 43
    response = client.post(
        "/api/pools/join",
        json={
            "pool_name": name,
            "pool_code": pool["pool_code"],
            "worker_token": token,
            "worker": PAYLOAD,
        },
    )
    assert response.status_code == 200
    return pool, token


def test_delete_unused_worker_revokes_identity_but_preserves_row(client, context):
    pool, token = pool_and_worker(client)
    response = client.delete("/api/workers/worker-1")
    assert response.status_code == 204 and response.content == b""
    assert client.get("/api/workers").json() == []
    assert client.get("/api/workers/worker-1").status_code == 404
    assert client.get(f"/api/pools/{pool['pool_id']}/status").json()["workers"] == []
    assert client.delete("/api/workers/worker-1").status_code == 404
    assert client.post("/api/workers/worker-1/rotate-token").status_code == 404
    headers = {
        "Authorization": "Bearer " + token,
        "X-Worker-ID": "worker-1",
        "X-Worker-Lease-Enforced": "true",
    }
    assert (
        client.post("/api/workers/worker-1/disconnect", headers=headers).status_code
        == 404
    )
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws/workers", headers=headers),
    ):
        pass
    rejoin = client.post(
        "/api/pools/join",
        json={
            "pool_name": pool["name"],
            "pool_code": pool["pool_code"],
            "worker_token": token,
            "worker": PAYLOAD,
        },
    )
    assert rejoin.status_code == 409 and "new state directory" in rejoin.text
    with context.db.session() as session:
        worker = session.get(Worker, "worker-1")
        assert worker.deleted_at is not None
        assert scheduling_context(session)[0] == []


@pytest.mark.parametrize("channel", ["control", "relay"])
def test_delete_connected_worker_is_rejected(client, context, monkeypatch, channel):
    pool_and_worker(client)
    if channel == "control":
        monkeypatch.setattr(
            context.gateway, "is_worker_connected", lambda identity: True
        )
    else:
        monkeypatch.setattr(context.relay, "connected", lambda identity: True)
    assert client.delete("/api/workers/worker-1").status_code == 409
    assert len(client.get("/api/workers").json()) == 1


@pytest.mark.parametrize(
    "blocker", ["lease", "count", "running", "box", "reservation", "replica"]
)
def test_worker_delete_requires_fencing_and_release(client, context, blocker):
    pool_and_worker(client)
    with context.db.session() as session:
        worker = session.get(Worker, "worker-1")
        if blocker == "lease":
            worker.lease_expires_at = datetime.now(UTC) + timedelta(seconds=15)
        if blocker == "count":
            worker.active_container_count = 1
        if blocker == "running":
            worker.running_containers = ["container-1"]
        if blocker in {"box", "reservation", "replica"}:
            box = Box(
                box_id=uuid4(),
                pool_id=worker.pool_id,
                name="reference",
                ram_limit_gb=1,
                cpu_limit_cores=1,
                storage_limit_gb=1,
                eligible_worker_ids=["worker-1"] if blocker == "box" else [],
                status="available",
                deleted_at=None if blocker == "box" else datetime.now(UTC),
            )
            session.add(box)
            session.flush()
            if blocker == "reservation":
                session.add(
                    ResourceReservation(
                        box_id=box.box_id,
                        worker_id=worker.worker_id,
                        role="primary",
                        ram_limit_gb=1,
                        cpu_limit_cores=1,
                        storage_limit_gb=1,
                    )
                )
            if blocker == "replica":
                deployment = Deployment(
                    deployment_id=uuid4(),
                    box_id=box.box_id,
                    repository_url="https://github.com/example/app",
                    application_type="python",
                    image_reference="image",
                    status="running",
                )
                session.add(deployment)
                session.flush()
                session.add(
                    Replica(
                        deployment_id=deployment.deployment_id,
                        worker_id=worker.worker_id,
                        role="primary",
                        status="running",
                        container_status="running",
                    )
                )
    assert client.delete("/api/workers/worker-1").status_code == 409
    assert client.get("/api/workers/worker-1").status_code == 200


def test_stopped_history_survives_worker_and_pool_delete(client, context):
    pool, _ = pool_and_worker(client)
    with context.db.session() as session:
        worker = session.get(Worker, "worker-1")
        worker.lease_expires_at = datetime.now(UTC) - timedelta(seconds=100)
        box = Box(
            box_id=uuid4(),
            pool_id=worker.pool_id,
            name="history",
            ram_limit_gb=1,
            cpu_limit_cores=1,
            storage_limit_gb=1,
            eligible_worker_ids=[worker.worker_id],
            status="available",
            deleted_at=datetime.now(UTC),
        )
        session.add(box)
        session.flush()
        deployment = Deployment(
            deployment_id=uuid4(),
            box_id=box.box_id,
            repository_url="https://github.com/example/app",
            application_type="python",
            image_reference="image",
            status="stopped",
        )
        session.add(deployment)
        session.flush()
        replica = Replica(
            replica_id=uuid4(),
            deployment_id=deployment.deployment_id,
            worker_id=worker.worker_id,
            role="primary",
            status="stopped",
            container_status="stopped",
        )
        session.add(replica)
        deployment_id, replica_id = deployment.deployment_id, replica.replica_id
    assert client.delete("/api/workers/worker-1").status_code == 204
    assert client.delete(f"/api/pools/{pool['pool_id']}").status_code == 204
    assert client.get("/api/pools").json() == []
    assert client.get(f"/api/pools/{pool['pool_id']}/status").status_code == 404
    assert client.post(f"/api/pools/{pool['pool_id']}/rotate-code").status_code == 404
    assert (
        client.post(
            "/api/pools/join",
            json={
                "pool_name": pool["name"],
                "pool_code": pool["pool_code"],
                "worker_token": "lattice_wk_" + "x" * 43,
                "worker": PAYLOAD | {"worker_id": "worker-2"},
            },
        ).status_code
        == 403
    )
    with context.db.session() as session:
        assert session.get(Deployment, deployment_id) is not None
        assert session.get(Replica, replica_id) is not None
        assert session.get(Pool, worker.pool_id).deleted_at is not None
    assert client.post("/api/pools", json={"name": pool["name"]}).status_code == 409


def test_nonempty_pool_delete_is_rejected(client, context):
    pool, _ = pool_and_worker(client)
    assert client.delete(f"/api/pools/{pool['pool_id']}").status_code == 409
    assert client.delete("/api/workers/worker-1").status_code == 204
    with context.db.session() as session:
        session.add(
            Box(
                pool_id=session.query(Pool).first().pool_id,
                name="allocated",
                ram_limit_gb=1,
                cpu_limit_cores=1,
                storage_limit_gb=1,
                eligible_worker_ids=[],
                status="available",
            )
        )
    assert client.delete(f"/api/pools/{pool['pool_id']}").status_code == 409


def test_inventory_delete_is_admin_only(client):
    pool, token = pool_and_worker(client)
    for headers in [
        {},
        {"Authorization": "Bearer " + token, "X-Worker-ID": "worker-1"},
    ]:
        client.headers.clear()
        assert (
            client.delete("/api/workers/worker-1", headers=headers).status_code == 401
        )
        assert (
            client.delete(f"/api/pools/{pool['pool_id']}", headers=headers).status_code
            == 401
        )


def test_inventory_migration_upgrades_existing_schema_without_data_loss(tmp_path):
    from alembic import command

    from control_plane.database.init_db import migration_config

    db = Database("sqlite:///" + str(tmp_path / "old.db"))
    try:
        with db.engine.begin() as connection:
            command.upgrade(migration_config(connection), "0002_pools_and_relay")
            connection.execute(
                text(
                    "INSERT INTO pools (pool_id,name,code_hash,code_expires_at,max_joins,joins_used,created_at) VALUES (:id,'kept','hash',CURRENT_TIMESTAMP,10,0,CURRENT_TIMESTAMP)"
                ),
                {"id": uuid4().hex},
            )
        init_db(db.engine)
        assert "deleted_at" in {
            c["name"] for c in inspect(db.engine).get_columns("workers")
        }
        with db.engine.connect() as connection:
            assert connection.execute(
                text("SELECT name,deleted_at FROM pools")
            ).one() == ("kept", None)
    finally:
        db.close()


def test_deleted_worker_cannot_reconnect_after_authentication_race(
    client, context, monkeypatch
):
    from unittest.mock import AsyncMock

    pool_and_worker(client)
    assert client.delete("/api/workers/worker-1").status_code == 204
    monkeypatch.setattr(
        context.gateway, "authenticate_worker", AsyncMock(return_value="worker-1")
    )
    context.gateway.on_failure = None
    headers = {
        "Authorization": "Bearer stale",
        "X-Worker-ID": "worker-1",
        "X-Worker-Lease-Enforced": "true",
    }
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws/workers", headers=headers) as ws,
    ):
        ws.receive_json()
    assert not context.gateway.is_worker_connected("worker-1")
    assert "worker-1" not in context.gateway.sessions


def test_retired_worker_and_pool_cannot_be_used_for_new_boxes(client):
    pool, _ = pool_and_worker(client)
    assert client.delete("/api/workers/worker-1").status_code == 204
    payload = {
        "pool_id": pool["pool_id"],
        "name": "blocked",
        "ram_limit_gb": 0.5,
        "cpu_limit_cores": 0.5,
        "storage_limit_gb": 1,
        "eligible_worker_ids": ["worker-1"],
    }
    assert client.post("/api/boxes", json=payload).status_code == 400
    assert client.delete(f"/api/pools/{pool['pool_id']}").status_code == 204
    assert client.post("/api/boxes", json=payload).status_code == 404
