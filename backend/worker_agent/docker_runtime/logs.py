"""Bounded, incremental log polling into the shared container_logs contract."""

from collections import deque
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

from shared.contracts import ContainerLogsEvent
from shared.enums import LogLevel

from worker_agent.security.policy import DEPLOYMENT_LABEL


class LogCollector:
    def __init__(self, settings):
        self.settings = settings
        self.seen = {}
        self.since = {}

    def collect(self, container) -> list[ContainerLogsEvent]:
        seen = self.seen.setdefault(container.id, deque(maxlen=2048))
        events = []
        remaining = self.settings.log_max_bytes
        since = self.since.get(container.id)
        for stderr in (False, True):
            raw = container.logs(
                stdout=not stderr,
                stderr=stderr,
                stream=False,
                timestamps=True,
                tail=self.settings.log_tail_lines,
                since=since,
            )
            for line in raw.decode("utf-8", errors="replace").splitlines():
                key = (stderr, sha256(line.encode()).digest())
                if key in seen:
                    continue
                timestamp_text, separator, message = line.partition(" ")
                try:
                    timestamp = datetime.fromisoformat(timestamp_text)
                    if timestamp.tzinfo is None:
                        raise ValueError("Missing log timestamp offset")
                except ValueError:
                    timestamp = datetime.now(UTC)
                    message = line
                if not separator:
                    message = line
                if remaining <= 0:
                    break
                message = message.replace(
                    self.settings.worker_token.get_secret_value(), "[REDACTED]"
                )
                encoded = message.encode()[:remaining]
                message = encoded.decode("utf-8", errors="ignore")
                remaining -= len(encoded)
                events.append(
                    ContainerLogsEvent(
                        deployment_id=UUID(container.labels[DEPLOYMENT_LABEL]),
                        container_id=container.id,
                        log_level=LogLevel.WARNING if stderr else LogLevel.INFO,
                        message=message,
                        timestamp=timestamp,
                    )
                )
                seen.append(key)
                self.since[container.id] = max(
                    self.since.get(container.id, 0), int(timestamp.timestamp())
                )
        return events

    def retain(self, container_ids: set[str]) -> None:
        self.seen = {
            key: value for key, value in self.seen.items() if key in container_ids
        }
        self.since = {
            key: value for key, value in self.since.items() if key in container_ids
        }
