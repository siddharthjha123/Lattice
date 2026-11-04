"""Real Git cloning, explicit application configuration, Docker build and push."""

import ast
import asyncio
import json
import os
import re
import shutil
import threading
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

from docker.errors import DockerException
from docker.utils import parse_repository_tag
from pydantic import BaseModel, ConfigDict, Field, field_validator
from shared.enums import ApplicationType
from worker_agent.security.policy import open_local_docker

from control_plane.config import settings
from control_plane.logging import redact_message


class ApplicationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_command: list[str] | None = None
    internal_port: int = Field(default=8000, ge=1, le=65535)
    readiness_path: str = "/"
    environment_variables: dict[str, str] = Field(default_factory=dict)

    @field_validator("start_command")
    @classmethod
    def check_command(cls, value):
        if value is not None and (
            not value or any(not item or "\x00" in item for item in value)
        ):
            raise ValueError("Start command must be a nonempty argument list")
        return value

    @field_validator("readiness_path")
    @classmethod
    def check_path(cls, value):
        if (
            not value.startswith("/")
            or value.startswith("//")
            or "\r" in value
            or "\n" in value
        ):
            raise ValueError(
                "Readiness path must be relative to the application origin"
            )
        return value


def validate_repository_url(value, config):
    parsed = urlsplit(value)
    local = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Repository URL cannot contain credentials, query or fragment")
    if config.ALLOW_LOCAL_REPOSITORIES and local and parsed.scheme in {"http", "https"}:
        return value
    if (
        parsed.scheme != "https"
        or parsed.hostname not in config.ALLOWED_REPOSITORY_HOSTS
    ):
        raise ValueError("Repository must use HTTPS on an allowed public Git host")
    if not re.fullmatch(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?", parsed.path):
        raise ValueError("Repository URL must identify an owner and repository")
    return value


class ImageDistributionAdapter:
    def __init__(self, config=None, client=None):
        self.config = config or settings
        self.client = client

    def get_target_image_tag(self, deployment_id):
        prefix = self.config.REGISTRY_URL.strip().rstrip("/")
        name = f"lattice-app-{deployment_id}:build"
        return f"{prefix}/{name}" if prefix else name

    async def distribute_image(self, local_image_tag):
        if not self.config.REGISTRY_URL:
            raise RuntimeError(
                "REGISTRY_URL is required; local builder images are not remote worker images"
            )
        if self.client is None:
            raise RuntimeError("Docker is required for real image publication")

        def push():
            auth = None
            if self.config.REGISTRY_USERNAME:
                auth = {
                    "username": self.config.REGISTRY_USERNAME,
                    "password": self.config.REGISTRY_PASSWORD.get_secret_value(),
                }
            digest = None
            for entry in self.client.images.push(
                local_image_tag, stream=True, decode=True, auth_config=auth
            ):
                if entry.get("error") or entry.get("errorDetail"):
                    raise RuntimeError("Registry rejected image publication")
                digest = entry.get("aux", {}).get("Digest", digest)
            repository, _ = parse_repository_tag(local_image_tag)
            if digest is None:
                image = self.client.images.get(local_image_tag)
                for reference in image.attrs.get("RepoDigests") or []:
                    if reference.startswith(repository + "@"):
                        digest = reference.split("@", 1)[1]
            if digest is None or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
                raise RuntimeError("Registry did not return a verified image digest")
            return repository + "@" + digest

        return await asyncio.to_thread(push)


class GitBuilder:
    def __init__(self, config=None, client=None):
        self.config = config or settings
        self.build_root = Path(self.config.BUILD_DIR).expanduser().absolute()
        self.client = client

    def docker(self):
        if self.client is None:
            self.client = open_local_docker(
                SimpleNamespace(docker_timeout=self.config.DOCKER_TIMEOUT)
            )
        self.client.ping()
        return self.client

    def distribution_tag(self, deployment_id):
        return ImageDistributionAdapter(self.config).get_target_image_tag(deployment_id)

    async def clone_repository(self, repository_url, branch, deployment_id):
        validate_repository_url(repository_url, self.config)
        if (
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", branch)
            or ".." in branch
            or branch.endswith(".lock")
        ):
            raise ValueError("Invalid Git branch")
        self.build_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.build_root.is_symlink():
            raise ValueError("Build root must not be a symlink")
        target = self.build_root / str(deployment_id)
        if target.exists() or target.is_symlink():
            self.cleanup(deployment_id)

        async def logs():
            yield "Cloning the configured public repository\n"
            process = await asyncio.create_subprocess_exec(
                "git",
                "-c",
                "credential.helper=",
                "-c",
                "protocol.file.allow=never",
                "-c",
                "protocol.ext.allow=never",
                "-c",
                "http.followRedirects=false",
                "clone",
                "--depth=1",
                "--branch",
                branch,
                "--",
                repository_url,
                str(target),
                env=os.environ
                | {"GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1"},
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                async with asyncio.timeout(self.config.GIT_TIMEOUT):
                    while line := await process.stdout.readline():
                        yield line.decode(errors="replace")[:16384]
                    if await process.wait() != 0:
                        raise RuntimeError(
                            "Git clone failed; verify the public URL and branch"
                        )
            finally:
                if process.returncode is None:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), 5)
                    except TimeoutError:
                        process.kill()
                        await process.wait()

        return target, logs()

    def detect_application_type(self, path):
        if (path / "package.json").is_file():
            return ApplicationType.NODE
        if (path / "requirements.txt").is_file() or (path / "pyproject.toml").is_file():
            return ApplicationType.PYTHON
        raise ValueError(
            "Application type is ambiguous; provide Python/Node configuration with the Dockerfile"
        )

    def load_application_config(self, path, override):
        file = path / "lattice.json"
        supplied = json.loads(file.read_text()) if file.is_file() else {}
        return ApplicationConfig.model_validate(supplied | override)

    def prepare_dockerfile(self, path, app_type, application=None):
        if (path / "Dockerfile").is_file():
            return
        application = application or ApplicationConfig()
        start = application.start_command
        if app_type == ApplicationType.NODE:
            package = json.loads((path / "package.json").read_text())
            if start is None:
                if package.get("scripts", {}).get("start"):
                    start = ["npm", "start"]
                else:
                    entry = next(
                        (
                            name
                            for name in ("index.js", "server.js", "app.js")
                            if (path / name).is_file()
                        ),
                        None,
                    )
                    if entry is None:
                        raise ValueError(
                            "Node application needs a start script or explicit start_command"
                        )
                    start = ["node", entry]
            base = self.config.NODE_BASE_IMAGE
            install = "COPY package*.json ./\nRUN npm install --omit=dev --no-audit --no-fund\n"
        else:
            if start is None:
                for filename in ("main.py", "app.py"):
                    candidate = path / filename
                    if candidate.is_file() and "FastAPI" in candidate.read_text():
                        ast.parse(candidate.read_text())
                        start = [
                            "python",
                            "-m",
                            "uvicorn",
                            filename[:-3] + ":app",
                            "--host",
                            "0.0.0.0",
                            "--port",
                            str(application.internal_port),
                        ]
                        break
                if start is None:
                    raise ValueError(
                        "Python application needs an explicit start_command when FastAPI startup is unclear"
                    )
            base = self.config.PYTHON_BASE_IMAGE
            if (path / "requirements.txt").is_file():
                install = "COPY . .\nRUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt\n"
            elif (path / "pyproject.toml").is_file():
                install = "COPY . .\nRUN pip install --no-cache-dir --disable-pip-version-check .\n"
            else:
                install = ""
        content = (
            f"FROM {base}\nWORKDIR /app\n"
            + install
            + "COPY . .\nRUN mkdir -p /data && chown 65532:65532 /data\n"
            "ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 NPM_CONFIG_UPDATE_NOTIFIER=false\n"
            f"ENV PORT={application.internal_port}\nUSER 65532:65532\nEXPOSE {application.internal_port}\n"
            + "CMD "
            + json.dumps(start)
            + "\n"
        )
        (path / "Dockerfile").write_text(content)
        if not (path / ".dockerignore").exists():
            (path / ".dockerignore").write_text(
                ".git\n.env\n.env.*\n!.env.example\n.venv\nnode_modules\n__pycache__\n"
            )

    async def build_docker_image(self, path, deployment_id, *, platform=None):
        client = await asyncio.to_thread(self.docker)
        adapter = ImageDistributionAdapter(self.config, client)
        tag = adapter.get_target_image_tag(deployment_id)

        async def logs():
            loop = asyncio.get_running_loop()
            queue = asyncio.Queue(maxsize=128)
            cancelled = threading.Event()

            def produce():
                try:
                    entries = client.api.build(
                        path=str(path),
                        **({"platform": platform} if platform else {}),
                        tag=tag,
                        rm=True,
                        decode=True,
                        labels={
                            "io.lattice.deployment": str(deployment_id)
                        },
                    )
                    for entry in entries:
                        if cancelled.is_set():
                            entries.close()
                            break
                        if entry.get("error") or entry.get("errorDetail"):
                            detail = entry.get("errorDetail")
                            detail = (
                                detail.get("message")
                                if isinstance(detail, dict)
                                else detail
                            )
                            detail = (
                                detail
                                or entry.get("error")
                                or "Docker daemon returned a build error"
                            )
                            raise RuntimeError(
                                "Docker build failed: "
                                + redact_message(detail, self.config)[:4096]
                            )
                        output = entry.get("stream")
                        if (
                            not output
                            and entry.get("status")
                            and not entry.get("progressDetail")
                        ):
                            output = entry["status"]
                        if output and output.strip():
                            asyncio.run_coroutine_threadsafe(
                                queue.put(redact_message(output, self.config)[:16384]),
                                loop,
                            ).result(30)
                except Exception as exc:  # noqa: BLE001 -- transfer build failures out of the thread
                    if isinstance(exc, DockerException):
                        detail = getattr(exc, "explanation", None) or str(exc)
                        exc = RuntimeError(
                            "Docker build failed: "
                            + redact_message(detail, self.config)[:4096]
                        )
                    asyncio.run_coroutine_threadsafe(queue.put(exc), loop).result(30)
                finally:
                    asyncio.run_coroutine_threadsafe(queue.put(None), loop).result(30)

            producer = asyncio.create_task(asyncio.to_thread(produce))
            try:
                yield "Building application image on control-plane Docker; target=" + (
                    platform or "daemon default"
                )
                while (item := await queue.get()) is not None:
                    if isinstance(item, Exception):
                        raise item
                    yield item
                await producer
            finally:
                cancelled.set()
                # Release a producer blocked on a full queue when a caller cancels.
                while not producer.done():
                    try:
                        await asyncio.wait_for(queue.get(), 0.1)
                    except TimeoutError:
                        pass
                await producer

        return tag, logs()

    async def publish(self, tag):
        client = await asyncio.to_thread(self.docker)
        return await ImageDistributionAdapter(self.config, client).distribute_image(tag)

    async def image_architecture(self, tag):
        return await asyncio.to_thread(
            lambda: self.docker().images.get(tag).attrs["Architecture"]
        )

    def cleanup(self, deployment_id):
        target = self.build_root / str(deployment_id)
        if target.is_symlink():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)

    def close(self):
        if self.client is not None:
            self.client.close()
