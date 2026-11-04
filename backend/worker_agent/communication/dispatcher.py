"""Structured execution with durable replay results and sanitized failures."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from docker.errors import APIError, DockerException
from shared.contracts import (
    CommandResult,
    ContainerStatusEvent,
    InspectContainerCommand,
    RunContainerCommand,
    StopContainerCommand,
)


@dataclass
class Execution:
    result: CommandResult
    events: list[ContainerStatusEvent] = field(default_factory=list)


class CommandDispatcher:
    def __init__(self, runtime, journal, settings):
        self.runtime = runtime
        self.journal = journal
        self.settings = settings

    def execute(self, command) -> Execution:
        # A single consumer serializes commands. Docker mutation locks also protect
        # owner operations and storage enforcement running in other threads.
        try:
            cached = self.journal.begin(command)
        except ValueError:
            return Execution(
                CommandResult(
                    request_id=command.request_id,
                    success=False,
                    message="Request ID was reused with different parameters",
                )
            )
        if cached:
            return Execution(cached)
        events = []
        inspection_payload = None
        try:
            if isinstance(command, RunContainerCommand):
                container_id = self.runtime.run(command)
                # Running process and application readiness are separate facts.
                events.append(
                    self.runtime.inspect(container_id, include_stats=False).event()
                )
                message = "Container started; application readiness requires health verification"
            elif isinstance(command, StopContainerCommand):
                container_id = self.runtime.stop(
                    command.container_id, str(command.deployment_id)
                )
                message = "Container stopped"
                events.append(
                    ContainerStatusEvent(
                        deployment_id=command.deployment_id,
                        container_id=container_id,
                        status="stopped",
                        timestamp=datetime.now(UTC),
                    )
                )
            elif isinstance(command, InspectContainerCommand):
                inspection = self.runtime.inspect(command.container_id)
                container_id = inspection.container_id
                message = inspection.summary()
                inspection_payload = inspection.contract()
                events.append(inspection.event())
            else:
                raise TypeError("Unsupported command")
            result = CommandResult(
                request_id=command.request_id,
                success=True,
                container_id=container_id,
                message=message,
                inspection=inspection_payload,
            )
        except APIError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            result = self._failure(command, f"Docker operation failed (HTTP {status})")
        except DockerException:
            result = self._failure(
                command, "Docker daemon is unavailable or rejected the operation"
            )
        except (ValueError, PermissionError, RuntimeError) as exc:
            result = self._failure(command, str(exc))
        except Exception:  # noqa: BLE001 -- contain failures at the remote command boundary
            result = self._failure(command, "Worker execution failed")
        self.journal.finish(result)
        return Execution(result, events if result.success else [])

    def _failure(self, command, message):
        message = message.replace(
            self.settings.worker_token.get_secret_value(), "[REDACTED]"
        )
        return CommandResult(
            request_id=command.request_id, success=False, message=message[:1024]
        )
