"""Environment-only service configuration; no embedded account credentials."""

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None, extra="ignore", allow_inf_nan=False
    )

    DATABASE_URL: str = Field(
        default="postgresql+psycopg://lattice@127.0.0.1:5432/lattice", repr=False
    )
    DATABASE_DIRECT_DNS: bool = False
    DATABASE_DNS_OVER_HTTPS: bool = False
    DATABASE_CA_FILE: Path | None = Field(default=None, repr=False)
    ALLOWED_HOSTS: list[str] = ["localhost", "127.0.0.1", "testserver"]
    EXPOSE_API_DOCS: bool = True
    HOST: str = "127.0.0.1"
    PORT: int = Field(default=8000, ge=1, le=65535)
    LOG_LEVEL: str = "INFO"
    BUILD_DIR: Path = Path("/tmp/lattice-builds")
    PUBLIC_BASE_URL: str = "http://127.0.0.1:8000"
    WORKER_RELEASE_DIR: Path | None = None
    APP_DOMAIN: str = ""
    REGISTRY_URL: str = ""
    REGISTRY_USERNAME: str = ""
    REGISTRY_PASSWORD: SecretStr = SecretStr("")
    SECRET_KEY: str = Field(default="", repr=False)
    ADMIN_TOKEN: SecretStr = SecretStr("")
    ALLOWED_REPOSITORY_HOSTS: list[str] = ["github.com"]
    ALLOW_LOCAL_REPOSITORIES: bool = False
    CORS_ORIGINS: list[str] = []
    COMMAND_TIMEOUT: float = Field(default=60, gt=0)
    DOCKER_TIMEOUT: int = Field(default=60, ge=1, le=600)
    GIT_TIMEOUT: float = Field(default=180, ge=1, le=900)
    READINESS_TIMEOUT: float = Field(default=30, gt=0)
    HEARTBEAT_TIMEOUT: float = Field(default=20, gt=0)
    MONITOR_INTERVAL: float = Field(default=1, ge=0.05)
    PYTHON_BASE_IMAGE: str = "python:3.12-slim"
    NODE_BASE_IMAGE: str = "node:22-alpine"
    LEASE_SECONDS: float = Field(default=15, ge=0.5, le=60)
    FENCE_GRACE_SECONDS: float = Field(default=75, ge=0)
    AUTO_MIGRATE: bool = False

    @property
    def normalized_database_url(self) -> str:
        url = self.DATABASE_URL.strip()
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg://", 1)
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        if self.DATABASE_CA_FILE:
            from sqlalchemy.engine import make_url

            path = self.DATABASE_CA_FILE.expanduser().absolute()
            if not path.is_file():
                raise ValueError(
                    "DATABASE_CA_FILE must point to the trusted service CA certificate"
                )
            url = (
                make_url(url)
                .update_query_dict({"sslmode": "verify-full", "sslrootcert": str(path)})
                .render_as_string(hide_password=False)
            )
        return url


settings = Settings()
