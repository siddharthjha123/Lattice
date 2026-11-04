"""Stable JSON enum values shared by the three backend modules."""

from enum import StrEnum


class WorkerStatus(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    UNHEALTHY = "unhealthy"


class BoxStatus(StrEnum):
    AVAILABLE = "available"
    DEPLOYED = "deployed"
    DEGRADED = "degraded"
    FAILED = "failed"


class ApplicationType(StrEnum):
    PYTHON = "python"
    NODE = "node"


class DeploymentStatus(StrEnum):
    QUEUED = "queued"
    BUILDING = "building"
    DEPLOYING = "deploying"
    RUNNING = "running"
    FAILED = "failed"
    STOPPED = "stopped"


class ReplicaRole(StrEnum):
    PRIMARY = "primary"
    STANDBY = "standby"


class ReplicaStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    UNHEALTHY = "unhealthy"
    STOPPED = "stopped"


class ContainerStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    RESTARTING = "restarting"
    REMOVING = "removing"
    EXITED = "exited"
    DEAD = "dead"
    UNHEALTHY = "unhealthy"
    STOPPED = "stopped"


class LogLevel(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class FailoverState(StrEnum):
    DETECTING = "detecting"
    WORKER_FAILED = "worker_failed"
    SELECTING_STANDBY = "selecting_standby"
    REDEPLOYING = "redeploying"
    HEALTH_CHECK = "health_check"
    RECOVERED = "recovered"
    FAILED = "failed"
