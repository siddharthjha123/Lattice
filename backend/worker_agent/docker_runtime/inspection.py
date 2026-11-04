"""Sanitized internal inspection data; raw Docker config never leaves the worker."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from uuid import UUID

from shared.contracts import ContainerInspection as InspectionPayload
from shared.contracts import ContainerStatusEvent, PortBinding
from shared.enums import ContainerStatus

from worker_agent.security.policy import DEPLOYMENT_LABEL


@dataclass(frozen=True)
class ContainerInspection:
    container_id: str
    deployment_id: str
    status: str
    health: str
    cpu_limit_cores: float
    ram_limit_bytes: int
    memory_usage_bytes: int | None
    ports: dict

    def summary(self) -> str:
        return (
            f"state={self.status}; health={self.health}; cpu_limit_cores="
            f"{self.cpu_limit_cores}; ram_limit_bytes={self.ram_limit_bytes}; "
            f"memory_usage_bytes={self.memory_usage_bytes}; ports={self.ports}"
        )

    def as_dict(self) -> dict:
        return asdict(self)

    def contract(self) -> InspectionPayload:
        bindings = []
        for key, values in self.ports.items():
            port, protocol = key.split("/")
            for value in values or []:
                bindings.append(
                    PortBinding(
                        internal_port=int(port),
                        protocol=protocol,
                        host_ip=value["HostIp"],
                        host_port=int(value["HostPort"]),
                    )
                )
        return InspectionPayload(
            container_id=self.container_id,
            deployment_id=UUID(self.deployment_id),
            status=self.status,
            health=self.health,
            cpu_limit_cores=self.cpu_limit_cores,
            ram_limit_bytes=self.ram_limit_bytes,
            memory_usage_bytes=self.memory_usage_bytes,
            port_bindings=bindings,
        )

    def event(self) -> ContainerStatusEvent:
        status = "unhealthy" if self.health == "unhealthy" else self.status
        return ContainerStatusEvent(
            deployment_id=UUID(self.deployment_id),
            container_id=self.container_id,
            status=ContainerStatus(status),
            timestamp=datetime.now(UTC),
        )


def inspect_container(container, include_stats=True) -> ContainerInspection:
    container.reload()
    attributes = container.attrs
    state = attributes.get("State", {})
    config = attributes.get("HostConfig", {})
    stats = (
        container.stats(stream=False, one_shot=True)
        if include_stats and container.status == "running"
        else None
    )
    return ContainerInspection(
        container_id=container.id,
        deployment_id=container.labels[DEPLOYMENT_LABEL],
        status=state.get("Status", container.status),
        health=state.get("Health", {}).get("Status", "not_configured"),
        cpu_limit_cores=config.get("NanoCpus", 0) / 1e9,
        ram_limit_bytes=config.get("Memory", 0),
        memory_usage_bytes=stats.get("memory_stats", {}).get("usage", 0)
        if stats
        else None,
        ports=attributes.get("NetworkSettings", {}).get("Ports") or {},
    )
