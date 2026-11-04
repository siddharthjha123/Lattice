import json

import pytest
from pydantic import ValidationError
from worker_agent.config import Settings, load_settings


def settings(tmp_path, **overrides):
    return Settings(
        **(
            {
                "control_plane_url": "http://127.0.0.1:8000",
                "worker_token": "test-token",
                "state_dir": tmp_path,
                "require_control_plane_lease": False,
            }
            | overrides
        )
    )


def test_urls_and_secret_repr(tmp_path):
    config = settings(tmp_path, control_plane_url="https://example.com/prefix/")
    assert config.websocket_url == "wss://example.com/prefix/ws/workers"
    assert config.http_url == "https://example.com/prefix"
    assert "test-token" not in repr(config)


@pytest.mark.parametrize(
    "overrides",
    [
        {"worker_token": ""},
        {"worker_token": "token\r\nheader"},
        {"control_plane_url": "http://example.com"},
        {"control_plane_url": "https://user:password@example.com"},
        {"control_plane_url": "https://example.com?token=secret"},
        {"max_ram_gb": float("nan")},
        {"max_containers": 0},
        {"deployment_storage_gb": 17},
        {"snapshot_path": "//evil.example"},
        {"reconnect_min_seconds": 5, "reconnect_max_seconds": 1},
    ],
)
def test_invalid_configuration(tmp_path, overrides):
    with pytest.raises(ValidationError):
        settings(tmp_path, **overrides)


def test_environment_overrides_json_file(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "control_plane_url": "http://localhost:8000",
                "worker_token": "file-token",
                "max_containers": 2,
            }
        )
    )
    path.chmod(0o600)
    monkeypatch.setenv("MAX_CONTAINERS", "3")
    assert load_settings(path).max_containers == 3
