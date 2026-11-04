"""Prepared build-error regressions; no real image pulls or builds required."""

from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from docker.errors import APIError

from control_plane.config import Settings
from control_plane.database.models import Deployment, DeploymentLog
from control_plane.logging import redact_message
from control_plane.services.git_builder import GitBuilder


async def test_build_error_retains_network_cause_and_redacts_registry_secret(tmp_path):
    secret = "registry-diagnostic-test-secret"
    config = Settings(REGISTRY_URL="registry.example/team", REGISTRY_PASSWORD=secret)
    client = Mock()
    client.api.build.return_value = iter(
        [
            {"stream": "Step 1/12 : FROM python:3.12-slim\n"},
            {
                "error": "generic failure",
                "errorDetail": {"message": "connect: no route to host " + secret},
            },
        ]
    )
    builder = GitBuilder(config, client)
    _, stream = await builder.build_docker_image(
        tmp_path, uuid4(), platform="linux/amd64"
    )
    lines = []
    with pytest.raises(RuntimeError, match="no route to host") as observed:
        async for line in stream:
            lines.append(line)
    assert secret not in str(observed.value)
    assert "[REDACTED]" in str(observed.value)
    assert any("linux/amd64" in line for line in lines)
    assert client.api.build.call_args.kwargs["platform"] == "linux/amd64"


async def test_structured_error_without_error_key_still_fails_build(tmp_path):
    client = Mock()
    client.api.build.return_value = iter(
        [{"errorDetail": {"message": "lookup registry.example: no such host"}}]
    )
    _, stream = await GitBuilder(Settings(), client).build_docker_image(
        tmp_path, uuid4()
    )
    with pytest.raises(RuntimeError, match="no such host"):
        async for _ in stream:
            pass


async def test_docker_api_error_explanation_is_preserved_without_url_credentials(
    tmp_path,
):
    client = Mock()
    client.api.build.side_effect = APIError(
        "build failed",
        explanation="Get https://user:private-pass@registry.example/v2/: unavailable",
    )
    _, stream = await GitBuilder(Settings(), client).build_docker_image(
        tmp_path, uuid4()
    )
    with pytest.raises(RuntimeError, match="registry.example") as observed:
        async for _ in stream:
            pass
    assert "private-pass" not in str(observed.value)


def test_diagnostic_redaction_covers_password_fragments_and_query_tokens():
    config = Settings(
        DATABASE_URL="postgresql://user:private-db-pass@database.example/db"
    )
    result = redact_message(
        "private-db-pass https://registry.example/token?token=private-query&scope=pull Authorization: Bearer private-bearer",
        config,
    )
    assert "private-db-pass" not in result
    assert "private-query" not in result
    assert "private-bearer" not in result
    assert "scope=pull" in result


async def test_deployment_logs_store_sanitized_diagnostic_text(context, box):
    identity = uuid4()
    with context.db.session() as session:
        session.add(
            Deployment(
                deployment_id=identity,
                box_id=UUID(box["box_id"]),
                repository_url="https://github.com/example/app",
                application_type="python",
                image_reference="pending",
                status="building",
            )
        )
    token = context.config.ADMIN_TOKEN.get_secret_value()
    await context.manager.log(identity, "no route to host " + token, "error")
    with context.db.session() as session:
        message = (
            session.query(DeploymentLog).filter_by(deployment_id=identity).one().message
        )
        assert "no route to host" in message
        assert token not in message


async def test_worker_startup_timeout_identifies_stage_without_exposing_remote_error(
    context,
):
    from unittest.mock import AsyncMock

    context.manager.check_cancelled = AsyncMock()
    command = Mock()
    context.manager.run_command = AsyncMock(return_value=command)
    context.gateway.send_worker_command = AsyncMock(
        side_effect=TimeoutError("private-remote-credential")
    )
    with pytest.raises(
        RuntimeError, match="did not acknowledge container startup"
    ) as observed:
        await context.manager.dispatch_run(uuid4(), uuid4(), "worker-1")
    message = str(observed.value)
    assert "registry" in message and "lease fencing" in message
    assert "private-remote-credential" not in message
    context.gateway.send_worker_command.assert_awaited_once_with("worker-1", command)
