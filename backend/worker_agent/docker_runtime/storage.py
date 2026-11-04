"""Logical named-volume budgets measured by the daemon, never host mounts.

Polling detects an overrun after it occurs. This is not a filesystem hard quota.
"""

import math
from dataclasses import dataclass

from worker_agent.security.policy import DEPLOYMENT_LABEL, STORAGE_LABEL, WORKER_LABEL
from worker_agent.telemetry.system_monitor import GIB


@dataclass(frozen=True)
class VolumeUsage:
    deployment_id: str
    name: str
    limit_gb: float
    used_bytes: int


class StorageMonitor:
    def __init__(self, client, worker_id, max_storage_gb):
        self.client = client
        self.worker_id = worker_id
        self.max_storage_gb = max_storage_gb

    def volumes(self) -> list[VolumeUsage]:
        result = []
        for volume in self.client.df().get("Volumes") or []:
            labels = volume.get("Labels") or {}
            if labels.get(WORKER_LABEL) != self.worker_id:
                continue
            size = (volume.get("UsageData") or {}).get("Size", -1)
            limit = float(labels.get(STORAGE_LABEL, "nan"))
            if size < 0 or not math.isfinite(limit) or limit <= 0:
                raise RuntimeError(
                    "Docker cannot reliably measure an owned data volume"
                )
            result.append(
                VolumeUsage(labels[DEPLOYMENT_LABEL], volume["Name"], limit, size)
            )
        return result

    def committed_gb(self, volumes, active_deployments) -> float:
        return sum(
            volume.limit_gb
            if volume.deployment_id in active_deployments
            else volume.used_bytes / GIB
            for volume in volumes
        )

    def available_gb(self, active_deployments) -> float:
        return max(
            0,
            self.max_storage_gb - self.committed_gb(self.volumes(), active_deployments),
        )

    def admit(
        self, deployment_id, limit_gb, active_deployments, host_free_bytes
    ) -> None:
        volumes = self.volumes()
        existing = [
            volume for volume in volumes if volume.deployment_id == deployment_id
        ]
        if any(volume.used_bytes > limit_gb * GIB for volume in existing):
            raise ValueError(
                "Deployment data already exceeds its configured storage limit"
            )
        other = [volume for volume in volumes if volume.deployment_id != deployment_id]
        if (
            self.committed_gb(other, active_deployments) + limit_gb
            > self.max_storage_gb
        ):
            raise ValueError("Insufficient worker storage budget")
        growth = max(0, limit_gb * GIB - sum(volume.used_bytes for volume in existing))
        if growth > host_free_bytes:
            raise ValueError("Insufficient available host storage")

    def violations(self) -> dict[str, str]:
        volumes = self.volumes()
        violations = {
            volume.deployment_id: "Deployment data storage limit exceeded"
            for volume in volumes
            if volume.used_bytes > volume.limit_gb * GIB
        }
        if sum(volume.used_bytes for volume in volumes) > self.max_storage_gb * GIB:
            violations.update(
                {
                    volume.deployment_id: "Worker data storage budget exceeded"
                    for volume in volumes
                }
            )
        return violations
