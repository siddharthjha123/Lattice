import json
from unittest.mock import Mock
from uuid import uuid4

import pytest

from control_plane.config import Settings
from control_plane.services.git_builder import (
    ApplicationConfig,
    GitBuilder,
    ImageDistributionAdapter,
    validate_repository_url,
)


def test_dockerfile_uses_actual_entrypoints(tmp_path):
    builder = GitBuilder(Settings())
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"start": "node server.js"}})
    )
    assert builder.detect_application_type(tmp_path) == "node"
    builder.prepare_dockerfile(tmp_path, "node", ApplicationConfig())
    source = (tmp_path / "Dockerfile").read_text()
    assert "node:22-alpine" in source and '"npm", "start"' in source
    (tmp_path / "Dockerfile").unlink()
    (tmp_path / "package.json").unlink()
    (tmp_path / "requirements.txt").write_text("fastapi\nuvicorn\n")
    (tmp_path / "main.py").write_text("from fastapi import FastAPI\napp=FastAPI()\n")
    builder.prepare_dockerfile(tmp_path, "python", ApplicationConfig())
    assert "main:app" in (tmp_path / "Dockerfile").read_text()


def test_ambiguous_apps_require_explicit_start_command(tmp_path):
    builder = GitBuilder(Settings())
    with pytest.raises(ValueError):
        builder.prepare_dockerfile(tmp_path, "python", ApplicationConfig())
    builder.prepare_dockerfile(
        tmp_path, "python", ApplicationConfig(start_command=["python", "server.py"])
    )
    assert '"python", "server.py"' in (tmp_path / "Dockerfile").read_text()


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/repo",
        "ssh://git@github.com/x/y",
        "https://u:p@github.com/x/y",
        "http://github.com/x/y",
        "https://evil.test/x/y",
        "https://github.com/x/y?token=secret",
    ],
)
def test_repository_policy(url):
    with pytest.raises(ValueError):
        validate_repository_url(url, Settings())


async def test_push_requires_registry_and_digest():
    client = Mock()
    identity = uuid4()
    adapter = ImageDistributionAdapter(Settings(), client)
    with pytest.raises(RuntimeError):
        await adapter.distribute_image("local:test")
    adapter = ImageDistributionAdapter(
        Settings(REGISTRY_URL="registry.example/team"), client
    )
    tag = adapter.get_target_image_tag(identity)
    assert tag.startswith("registry.example/team/")
    client.images.push.return_value = iter([{"error": "no credentials"}])
    with pytest.raises(RuntimeError):
        await adapter.distribute_image(tag)
    client.images.push.return_value = iter([{"aux": {"Digest": "sha256:" + "a" * 64}}])
    assert (await adapter.distribute_image(tag)).endswith("@sha256:" + "a" * 64)
