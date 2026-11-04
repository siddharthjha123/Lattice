"""Real PostgreSQL regressions for preservation and transactional legacy adoption.

Opt in with LATTICE_RUN_MIGRATION_TESTS=1. Only its own local container is changed.
"""

import os
import secrets
import time
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from docker.errors import ImageNotFound
from worker_agent.security.policy import open_local_docker

from control_plane.database.adopt_legacy import (
    apply_adoption,
    data_fingerprints,
    legacy_columns,
)
from control_plane.database.init_db import migration_config
from control_plane.database.session import Base, Database

pytestmark = pytest.mark.skipif(
    os.environ.get("LATTICE_RUN_MIGRATION_TESTS") != "1",
    reason="Set LATTICE_RUN_MIGRATION_TESTS=1 for real PostgreSQL adoption checks",
)


@pytest.fixture(scope="module")
def postgres():
    client = open_local_docker(SimpleNamespace(docker_timeout=90))
    image = "public.ecr.aws/docker/library/postgres:18-alpine"
    try:
        client.images.get(image)
    except ImageNotFound:
        client.images.pull(image)
    password = secrets.token_urlsafe(32)
    container = client.containers.run(
        image,
        detach=True,
        environment={
            "POSTGRES_USER": "adoption_test",
            "POSTGRES_PASSWORD": password,
            "POSTGRES_DB": "adoption_test",
        },
        ports={"5432/tcp": ("127.0.0.1", None)},
        nano_cpus=500_000_000,
        mem_limit="512m",
        labels={"lattice.adoption-test": str(uuid4())},
    )
    try:
        container.reload()
        port = container.attrs["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostPort"]
        for _ in range(120):
            if (
                container.exec_run(
                    ["pg_isready", "-h", "127.0.0.1", "-U", "adoption_test"]
                ).exit_code
                == 0
            ):
                break
            time.sleep(0.15)
        yield f"postgresql+psycopg://adoption_test:{password}@127.0.0.1:{port}/adoption_test"
    finally:
        container.remove(force=True, v=True)
        client.close()


def legacy_metadata():
    metadata = sa.MetaData()
    for name, source in Base.metadata.tables.items():
        if name == "failover_decisions":
            continue
        columns = []
        for column in source.columns:
            if column.name not in legacy_columns(name):
                continue
            kind = (
                sa.String(128)
                if isinstance(column.type, sa.String)
                and getattr(column.type, "length", None) == 256
                else column.type
            )
            columns.append(
                sa.Column(
                    column.name,
                    kind,
                    *[
                        sa.ForeignKey(item.target_fullname)
                        for item in column.foreign_keys
                    ],
                    primary_key=column.primary_key,
                    nullable=column.nullable,
                )
            )
        table = sa.Table(name, metadata, *columns)
        for index in source.indexes:
            sa.Index(
                index.name,
                *[table.c[column.name] for column in index.columns],
                unique=False if name == "workers" else index.unique,
            )
    return metadata


@pytest.fixture
def legacy(postgres):
    database = Database(postgres)
    with database.engine.begin() as connection:
        # The disposable container and database are created by this fixture only.
        connection.exec_driver_sql("DROP SCHEMA public CASCADE")
        connection.exec_driver_sql("CREATE SCHEMA public")
    metadata = legacy_metadata()
    metadata.create_all(database.engine)
    now = datetime.now(UTC)
    box = uuid4()
    deployment = uuid4()
    replica = uuid4()
    with database.engine.begin() as c:
        c.execute(
            metadata.tables["workers"]
            .insert()
            .values(
                worker_id="legacy-worker",
                hostname="legacy",
                status="online",
                cpu_cores=2,
                available_cpu_cores=2,
                total_ram_gb=4,
                available_ram_gb=4,
                total_storage_gb=8,
                available_storage_gb=8,
                active_container_count=0,
                max_containers=2,
                architecture="arm64",
                supported_runtimes=["python"],
                token_hash="a" * 64,
                registered_at=now,
            )
        )
        c.execute(
            metadata.tables["boxes"]
            .insert()
            .values(
                box_id=box,
                name="Preserved Box",
                ram_limit_gb=1,
                cpu_limit_cores=1,
                storage_limit_gb=1,
                eligible_worker_ids=["legacy-worker"],
                primary_worker_id="legacy-worker",
                failover_enabled=False,
                status="available",
                created_at=now,
                updated_at=now,
            )
        )
        c.execute(
            metadata.tables["deployments"]
            .insert()
            .values(
                deployment_id=deployment,
                box_id=box,
                repository_url="https://github.com/example/app",
                branch="main",
                application_type="python",
                image_reference="legacy:local",
                status="failed",
                created_at=now,
                updated_at=now,
            )
        )
        c.execute(
            metadata.tables["replicas"]
            .insert()
            .values(
                replica_id=replica,
                deployment_id=deployment,
                worker_id="legacy-worker",
                role="primary",
                status="stopped",
                internal_port=8000,
                created_at=now,
                updated_at=now,
            )
        )
        c.execute(
            metadata.tables["resource_reservations"]
            .insert()
            .values(
                reservation_id=uuid4(),
                box_id=box,
                worker_id="legacy-worker",
                role="primary",
                ram_limit_gb=1,
                cpu_limit_cores=1,
                storage_limit_gb=1,
                container_slots=1,
                created_at=now,
            )
        )
    yield database, metadata, box
    database.close()


def test_adoption_preserves_all_original_values_and_matches_schema(legacy):
    database, _, _ = legacy
    with database.engine.begin() as connection:
        before = data_fingerprints(connection)
        result = apply_adoption(connection)
        assert result["existing_data_preserved"]
        assert before == data_fingerprints(connection)
        assert connection.execute(
            sa.text("SELECT request_id IS NOT NULL FROM replicas")
        ).scalar_one()
        assert (
            connection.execute(
                sa.text("SELECT running_containers FROM workers")
            ).scalar_one()
            == []
        )
        command.check(migration_config(connection))
    assert "ck_reservation_positive" in {
        row["name"]
        for row in sa.inspect(database.engine).get_check_constraints(
            "resource_reservations"
        )
    }


def test_duplicate_reservations_abort_without_partial_schema_changes(legacy):
    database, metadata, box = legacy
    with database.engine.begin() as connection:
        connection.execute(
            metadata.tables["resource_reservations"]
            .insert()
            .values(
                reservation_id=uuid4(),
                box_id=box,
                worker_id="legacy-worker",
                role="primary",
                ram_limit_gb=1,
                cpu_limit_cores=1,
                storage_limit_gb=1,
                container_slots=1,
                created_at=datetime.now(UTC),
            )
        )
    with (
        pytest.raises(ValueError, match="duplicate Box-worker"),
        database.engine.begin() as connection,
    ):
        apply_adoption(connection)
    schema = sa.inspect(database.engine)
    assert "failover_decisions" not in schema.get_table_names()
    assert "lease_id" not in {row["name"] for row in schema.get_columns("workers")}


def test_late_consistency_failure_rolls_back_ddl_and_data(legacy, monkeypatch):
    from control_plane.database import adopt_legacy

    database, _, _ = legacy
    monkeypatch.setattr(
        adopt_legacy, "compare_metadata", lambda *a, **kw: [("unexpected-change",)]
    )
    with (
        pytest.raises(RuntimeError, match="schema does not match"),
        database.engine.begin() as connection,
    ):
        apply_adoption(connection)
    schema = sa.inspect(database.engine)
    assert "failover_decisions" not in schema.get_table_names()
    assert "running_containers" not in {
        row["name"] for row in schema.get_columns("workers")
    }
    with database.engine.connect() as connection:
        assert (
            connection.execute(sa.text("SELECT count(*) FROM workers")).scalar_one()
            == 1
        )


def test_unrecognized_schema_is_refused(legacy):
    database, _, _ = legacy
    with database.engine.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE workers ADD COLUMN unreviewed text")
    with (
        pytest.raises(ValueError, match="Unexpected legacy columns"),
        database.engine.begin() as connection,
    ):
        apply_adoption(connection)
    assert "alembic_version" not in sa.inspect(database.engine).get_table_names()
