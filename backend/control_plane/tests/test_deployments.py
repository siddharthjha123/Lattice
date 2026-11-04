from uuid import UUID

from control_plane.database.models import Deployment, ResourceReservation


def test_versioned_lifecycle_and_box_claim(client, context, box):
    payload = {
        "repository_url": "https://github.com/example/app",
        "application_type": "python",
        "box_id": box["box_id"],
    }
    res = client.post("/api/deployments", json=payload)
    assert res.status_code == 201, res.text
    identity = res.json()["deployment_id"]
    assert res.json()["status"] == "queued"
    context.manager.schedule.assert_called_once_with(UUID(identity))
    assert client.post("/api/deployments", json=payload).status_code == 409
    assert client.delete("/api/boxes/" + box["box_id"]).status_code == 409
    assert client.get("/api/deployments").json()[0]["deployment_id"] == identity
    assert client.get(f"/api/deployments/{identity}/status").json()["replicas"] == []
    assert client.get(f"/api/deployments/{identity}/logs?limit=2001").status_code == 422
    assert (
        client.post(f"/api/deployments/{identity}/stop").json()["status"] == "stopped"
    )
    with context.db.session() as session:
        assert session.query(ResourceReservation).count() == 0
    again = client.post(f"/api/deployments/{identity}/redeploy")
    assert again.status_code == 201, again.text
    assert again.json()["deployment_id"] != identity
    with context.db.session() as session:
        assert session.query(Deployment).count() == 2
        assert session.get(
            Deployment, UUID(again.json()["deployment_id"])
        ).previous_deployment_id == UUID(identity)


def test_repository_and_distribution_fail_closed(client, context, box):
    payload = {
        "repository_url": "file:///etc",
        "application_type": "python",
        "box_id": box["box_id"],
    }
    assert client.post("/api/deployments", json=payload).status_code == 422
    context.config.REGISTRY_URL = ""
    assert (
        client.post(
            "/api/deployments",
            json=payload | {"repository_url": "https://github.com/example/app"},
        ).status_code
        == 503
    )


async def test_pending_run_can_be_stopped_by_owned_deterministic_name(context, box):
    from unittest.mock import AsyncMock, Mock
    from uuid import uuid4

    from shared.contracts import CommandResult

    from control_plane.database.models import Box, Replica

    identity = uuid4()
    replica = uuid4()
    box_id = UUID(box["box_id"])
    with context.db.session() as session:
        session.add(
            Deployment(
                deployment_id=identity,
                box_id=box_id,
                repository_url="https://github.com/example/app",
                application_type="python",
                image_reference="registry/app:build",
                status="deploying",
            )
        )
        session.flush()
        session.get(Box, box_id).deployment_id = identity
        session.add(
            Replica(
                replica_id=replica,
                deployment_id=identity,
                worker_id="worker-1",
                status="pending",
            )
        )
    context.gateway.is_worker_connected = Mock(return_value=True)
    context.gateway.send_worker_command = AsyncMock(
        return_value=CommandResult(
            request_id=uuid4(), success=True, message="Stopped or absent"
        )
    )
    assert await context.manager.stop_deployment(identity)
    command = context.gateway.send_worker_command.call_args.args[1]
    assert command.container_id == f"lattice-{identity.hex[:12]}-{replica.hex[:8]}"
    with context.db.session() as session:
        assert session.get(Deployment, identity).status == "stopped"
        assert session.query(ResourceReservation).count() == 0
