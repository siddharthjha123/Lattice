import pytest

from .conftest import PAYLOAD


def test_health(client):
    assert client.get("/health").json()["database"] == "connected"


def test_provision_is_offline_and_cannot_rotate_token(client, provision):
    token = provision()
    assert token.startswith("lattice_wk_")
    assert client.get("/api/workers/worker-1").json()["status"] == "offline"
    assert client.post("/api/workers/register", json=PAYLOAD).status_code == 409
    assert "token" not in client.get("/api/workers").text
    assert client.get("/api/workers/missing").status_code == 404


def test_management_and_disconnect_require_authentication(client, provision):
    token = provision()
    client.headers.clear()
    assert client.post("/api/workers/register", json=PAYLOAD).status_code == 401
    assert client.get("/api/workers").status_code == 401
    from .conftest import ADMIN

    assert (
        client.get("/api/workers", headers={"X-Worker-Token": ADMIN}).status_code == 401
    )
    assert client.post("/api/workers/worker-1/disconnect").status_code == 401
    headers = {"Authorization": "Bearer " + token, "X-Worker-ID": "worker-1"}
    assert (
        client.post("/api/workers/worker-1/disconnect", headers=headers).status_code
        == 200
    )


@pytest.mark.parametrize("address", ["0.0.0.0", "224.0.0.1", "169.254.1.1", "bad/host"])
def test_invalid_worker_addresses(client, address):
    assert (
        client.post(
            "/api/workers/register", json=PAYLOAD | {"address": address}
        ).status_code
        == 422
    )


def test_openapi_documents_management_bearer(client):
    schema = client.get("/openapi.json").json()
    assert (
        schema["components"]["securitySchemes"]["ManagementBearer"]["scheme"]
        == "bearer"
    )
    assert schema["paths"]["/api/workers/register"]["post"]["security"] == [
        {"ManagementBearer": []}
    ]


def test_offline_worker_token_rotation_revokes_previous_secret(client, provision):
    old = provision()
    response = client.post("/api/workers/worker-1/rotate-token")
    assert response.status_code == 200
    new = response.json()["token"]
    assert new != old
    assert (
        client.post(
            "/api/workers/worker-1/disconnect",
            headers={"Authorization": "Bearer " + old, "X-Worker-ID": "worker-1"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/workers/worker-1/disconnect",
            headers={"Authorization": "Bearer " + new, "X-Worker-ID": "worker-1"},
        ).status_code
        == 200
    )
    assert new not in client.get("/api/workers").text


def test_connected_worker_token_cannot_be_rotated(client, provision, context):
    provision()
    context.gateway.active_connections["worker-1"] = object()
    try:
        assert client.post("/api/workers/worker-1/rotate-token").status_code == 409
    finally:
        context.gateway.active_connections.clear()


def test_worker_cannot_rotate_its_own_token(client, provision):
    token = provision()
    assert (
        client.post(
            "/api/workers/worker-1/rotate-token",
            headers={"Authorization": "Bearer " + token, "X-Worker-ID": "worker-1"},
        ).status_code
        == 401
    )
