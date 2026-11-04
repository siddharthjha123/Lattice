"""Security, migration and restart coordination regressions."""

import asyncio
import json
import logging
from unittest.mock import AsyncMock
from uuid import uuid4, uuid5

import pytest
from alembic import command

from control_plane.config import Settings
from control_plane.database.init_db import init_db, migration_config
from control_plane.database.models import Box, Deployment, FailoverRecord, Replica
from control_plane.logging import ServiceFormatter
from control_plane.services.runtime import ServiceContext


def test_logs_redact_configured_secrets_and_exception_text():
    config = Settings(
        ADMIN_TOKEN="admin-test-secret",
        SECRET_KEY="hashing-test-secret",
        DATABASE_URL="postgresql://user:private-password@localhost/test",
        REGISTRY_PASSWORD="registry-test-secret",
    )
    formatter = ServiceFormatter(config)
    try:
        raise RuntimeError(config.DATABASE_URL)
    except RuntimeError:
        import sys

        record = logging.LogRecord(
            "control_plane",
            logging.ERROR,
            "",
            0,
            "%s %s %s",
            (
                config.ADMIN_TOKEN.get_secret_value(),
                config.SECRET_KEY,
                config.REGISTRY_PASSWORD.get_secret_value(),
            ),
            sys.exc_info(),
        )
    output = formatter.format(record)
    data = json.loads(output)
    assert data["message"] == "[REDACTED] [REDACTED] [REDACTED]"
    assert data["exception_type"] == "RuntimeError"
    assert "private-password" not in output


def test_initial_migration_is_repeatable_and_matches_models(context):
    init_db(context.db.engine)
    with context.db.engine.begin() as connection:
        command.check(migration_config(connection))


async def test_startup_replays_durable_jobs_without_replanning_recovery(
    context, online
):
    online()
    box_id = uuid4()
    queued = uuid4()
    recovering = uuid4()
    decision = uuid4()
    replica = uuid5(decision, "replica")
    with context.db.session() as session:
        session.add(
            Box(
                box_id=box_id,
                name="Recovery",
                ram_limit_gb=1,
                cpu_limit_cores=1,
                storage_limit_gb=1,
                eligible_worker_ids=["worker-1"],
                primary_worker_id="worker-1",
                failover_enabled=False,
            )
        )
        session.flush()
        for identity, state in [(queued, "queued"), (recovering, "deploying")]:
            session.add(
                Deployment(
                    deployment_id=identity,
                    box_id=box_id,
                    repository_url="https://github.com/example/app",
                    application_type="python",
                    image_reference="registry/app@sha256:" + "a" * 64,
                    status=state,
                )
            )
        session.flush()
        session.add(
            Replica(
                replica_id=replica,
                deployment_id=recovering,
                worker_id="worker-1",
                request_id=decision,
                role="primary",
            )
        )
        session.add(
            FailoverRecord(
                decision_id=decision,
                deployment_id=recovering,
                box_id=box_id,
                failed_worker_id="old-worker",
                replacement_worker_id="worker-1",
                state="redeploying",
                reason="reserved standby",
            )
        )
    context.manager.dispatch_recovery = AsyncMock()
    await context.manager.resume()
    await asyncio.gather(*context.manager.jobs.values())
    context.manager.schedule.assert_called_once_with(queued)
    context.manager.dispatch_recovery.assert_awaited_once_with(
        recovering, replica, "worker-1", decision
    )


async def test_controller_requires_distinct_strong_secrets(tmp_path):
    from control_plane.database.session import Database

    config = Settings(
        DATABASE_URL="sqlite://", ADMIN_TOKEN="x" * 40, SECRET_KEY="x" * 40
    )
    database = Database("sqlite://")
    ctx = ServiceContext(config, database)
    try:
        with pytest.raises(RuntimeError, match="different"):
            await ctx.start()
    finally:
        database.close()
