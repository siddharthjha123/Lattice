"""Validated owner configuration; credentials never appear in model reprs."""

import json
import os
import re
from ipaddress import ip_address
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from worker_agent.security.auth import validate_worker_id
from worker_agent.security.private_files import private_reader, reject_link


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None, extra="forbid", allow_inf_nan=False, case_sensitive=False
    )

    control_plane_url: str
    worker_token: SecretStr
    worker_id: str | None = None
    state_dir: Path = Path.home() / ".local/share/lattice/worker"
    max_containers: int = Field(default=4, ge=1, le=1000)
    max_ram_gb: float = Field(default=4, gt=0)
    max_storage_gb: float = Field(default=16, gt=0)
    max_cpu_cores: float = Field(default=2, gt=0)
    deployment_storage_gb: float = Field(default=1, gt=0)
    deployment_storage_limits: dict[UUID, float] = Field(default_factory=dict)
    heartbeat_interval: float = Field(default=5, ge=0.1, le=300)
    reconnect_min_seconds: float = Field(default=1, ge=0.05, le=60)
    reconnect_max_seconds: float = Field(default=30, ge=0.1, le=300)
    connect_timeout: float = Field(default=10, ge=0.1, le=120)
    docker_timeout: int = Field(default=60, ge=1, le=600)
    image_pull_policy: Literal["always", "if_not_present"] = "always"
    disconnect_grace_seconds: float = Field(default=10, ge=0, le=120)
    stop_on_disconnect: bool = False
    command_queue_size: int = Field(default=32, ge=1, le=1024)
    log_tail_lines: int = Field(default=50, ge=1, le=1000)
    log_max_bytes: int = Field(default=16384, ge=256, le=1048576)
    container_user: str = "65532:65532"
    bind_address: str = "127.0.0.1"
    allow_insecure_connection: bool = False
    application_relay: bool = False
    snapshot_path: str | None = None
    require_control_plane_lease: bool = True
    max_lease_seconds: float = Field(default=60, ge=0.5, le=60)
    max_clock_skew_seconds: float = Field(default=2, ge=0, le=10)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        # Environment overrides a supplied JSON file, without modifying os.environ.
        return env_settings, init_settings, file_secret_settings

    @field_validator("control_plane_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https", "ws", "wss"} or not parsed.hostname:
            raise ValueError("CONTROL_PLANE_URL must be an HTTP or WebSocket URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError(
                "Control Plane URL cannot contain credentials or query data"
            )
        _ = parsed.port  # Reject malformed ports during configuration.
        return value.rstrip("/")

    @field_validator("worker_token")
    @classmethod
    def validate_token(cls, value: SecretStr) -> SecretStr:
        token = value.get_secret_value()
        if not token or any(not 33 <= ord(character) <= 126 for character in token):
            raise ValueError(
                "WORKER_TOKEN must be nonblank and contain no control bytes"
            )
        return value

    @field_validator("worker_id", "container_user", "bind_address")
    @classmethod
    def validate_text(cls, value: str | None) -> str | None:
        if value is not None and (
            not value.strip() or any(c in value for c in "\r\n\x00")
        ):
            raise ValueError("Configuration identifier contains invalid characters")
        return value

    @field_validator("snapshot_path")
    @classmethod
    def validate_snapshot_path(cls, value: str | None) -> str | None:
        if value is not None and (
            not value.startswith("/")
            or value.startswith("//")
            or urlsplit(value).query
            or urlsplit(value).fragment
        ):
            raise ValueError(
                "SNAPSHOT_PATH must be an absolute path on the Control Plane"
            )
        return value

    @model_validator(mode="after")
    def validate_policy(self) -> "Settings":
        if self.worker_id is not None:
            validate_worker_id(self.worker_id)
        if not re.fullmatch(r"[1-9][0-9]*:[0-9]+", self.container_user):
            raise ValueError("CONTAINER_USER must be a numeric non-root UID:GID")
        ip_address(self.bind_address)
        parsed = urlsplit(self.control_plane_url)
        local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if (
            parsed.scheme in {"http", "ws"}
            and not local
            and not self.allow_insecure_connection
        ):
            raise ValueError(
                "Remote Control Plane requires TLS or explicit insecure opt-in"
            )
        if self.reconnect_max_seconds < self.reconnect_min_seconds:
            raise ValueError("Reconnect maximum cannot be below its minimum")
        limits = [self.deployment_storage_gb, *self.deployment_storage_limits.values()]
        if any(not (0 < value <= self.max_storage_gb) for value in limits):
            raise ValueError("Deployment storage limits must fit the worker budget")
        return self

    @property
    def websocket_url(self) -> str:
        parsed = urlsplit(self.control_plane_url)
        scheme = "wss" if parsed.scheme in {"https", "wss"} else "ws"
        return urlunsplit((scheme, parsed.netloc, parsed.path + "/ws/workers", "", ""))

    @property
    def http_url(self) -> str:
        parsed = urlsplit(self.control_plane_url)
        scheme = "https" if parsed.scheme in {"https", "wss"} else "http"
        return urlunsplit((scheme, parsed.netloc, parsed.path, "", ""))


def read_config(path: Path | None = None) -> dict:
    if path is None:
        return {}
    reject_link(path)
    # Token-free configuration remains readable for existing POSIX callers.
    # Windows configuration always receives full owner/SYSTEM ACL checks.
    if os.name == "nt":
        with private_reader(path) as stream:
            data = json.load(stream)
    else:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor) as stream:
            info = os.fstat(stream.fileno())
            data = json.load(stream)
        if (
            isinstance(data, dict)
            and any(key.lower() == "worker_token" for key in data)
            and (info.st_uid != os.getuid() or info.st_mode & 0o077)
        ):
            raise PermissionError(
                "Configuration containing a worker token must be owner-only (0600)"
            )
    if not isinstance(data, dict):
        raise TypeError("Worker configuration must be a JSON object")
    return data


def load_settings(path: Path | None = None) -> Settings:
    return Settings(**read_config(path))
