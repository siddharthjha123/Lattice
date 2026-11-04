"""Isolated unit API fixtures; production execution is tested separately."""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from control_plane.config import Settings
from control_plane.database.init_db import init_db
from control_plane.database.session import Database
from control_plane.main import create_app
from control_plane.services.git_builder import GitBuilder
from control_plane.services.runtime import ServiceContext

ADMIN = "test-management-" + "a" * 40
PAYLOAD = {
    "worker_id": "worker-1",
    "hostname": "test-host",
    "cpu_cores": 4,
    "total_ram_gb": 8,
    "total_storage_gb": 100,
    "max_containers": 4,
    "architecture": "arm64",
    "supported_runtimes": ["python", "node"],
}


@pytest.fixture
def context(tmp_path):
    config = Settings(
        DATABASE_URL="sqlite://",
        SECRET_KEY="test-hashing-" + "b" * 40,
        ADMIN_TOKEN=ADMIN,
        BUILD_DIR=tmp_path / "builds",
        REGISTRY_URL="127.0.0.1:5000",
        MONITOR_INTERVAL=60,
    )
    db = Database(config.DATABASE_URL)
    init_db(db.engine)
    ctx = ServiceContext(config, db, GitBuilder(config))
    ctx.manager.schedule = (
        Mock()
    )  # API unit tests must never clone arbitrary remote repositories.
    yield ctx
    db.close()


@pytest.fixture
def client(context):
    with TestClient(create_app(context.config, context)) as client:
        client.headers["Authorization"] = "Bearer " + ADMIN
        yield client


@pytest.fixture
def provision(client):
    def register(identity="worker-1"):
        res = client.post(
            "/api/workers/register", json=PAYLOAD | {"worker_id": identity}
        )
        assert res.status_code == 201, res.text
        return res.json()["token"]

    return register


@pytest.fixture
def online(context, provision):
    def activate(identity="worker-1"):
        token = provision(identity)
        from control_plane.database.models import Worker

        with context.db.session() as session:
            session.get(Worker, identity).status = "online"
        return token

    return activate


@pytest.fixture
def box(client, online):
    online()
    res = client.post(
        "/api/boxes",
        json={
            "name": "API unit Box",
            "ram_limit_gb": 1,
            "cpu_limit_cores": 1,
            "storage_limit_gb": 1,
            "eligible_worker_ids": ["worker-1"],
            "failover_enabled": False,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()
