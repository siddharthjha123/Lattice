"""Team-owned Pydantic v2 entities, wire messages, and scheduler boundaries.

See docs/contracts.md for serialization, units, ownership, and open interfaces.
These models do not implement execution, persistence, or scheduling.
"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    model_validator,
)

from shared.enums import (
    ApplicationType,
    BoxStatus,
    ContainerStatus,
    DeploymentStatus,
    FailoverState,
    LogLevel,
    ReplicaRole,
    ReplicaStatus,
    WorkerStatus,
)

NonEmptyString = Annotated[str, Field(min_length=1, pattern=r"\S")]
WorkerId = NonEmptyString
NonNegativeFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]
PositiveFloat = Annotated[float, Field(gt=0, allow_inf_nan=False)]
NonNegativeInt = Annotated[int, Field(ge=0, strict=True)]
PositiveInt = Annotated[int, Field(gt=0, strict=True)]
Port = Annotated[int, Field(ge=1, le=65535, strict=True)]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class WorkerSnapshot(ContractModel):
    worker_id: WorkerId
    hostname: NonEmptyString
    status: WorkerStatus
    cpu_cores: PositiveInt
    available_cpu_cores: NonNegativeFloat
    total_ram_gb: PositiveFloat
    available_ram_gb: NonNegativeFloat
    total_storage_gb: PositiveFloat
    available_storage_gb: NonNegativeFloat
    active_container_count: NonNegativeInt
    max_containers: PositiveInt
    architecture: NonEmptyString
    supported_runtimes: list[ApplicationType]
    last_heartbeat: AwareDatetime

    @model_validator(mode="after")
    def check_capacity(self) -> "WorkerSnapshot":
        for available, total in (
            (self.available_cpu_cores, self.cpu_cores),
            (self.available_ram_gb, self.total_ram_gb),
            (self.available_storage_gb, self.total_storage_gb),
        ):
            if available > total:
                raise ValueError("Available capacity cannot exceed total capacity")
        # Counts may exceed a newly lowered policy; telemetry must report reality.
        return self


class ResourceRequirements(ContractModel):
    ram_limit_gb: PositiveFloat
    cpu_limit_cores: PositiveFloat
    storage_limit_gb: PositiveFloat


class BoxCreationRequest(ResourceRequirements):
    name: NonEmptyString
    eligible_worker_ids: list[WorkerId] = Field(min_length=1)
    failover_enabled: bool = False

    @model_validator(mode="after")
    def check_workers(self) -> "BoxCreationRequest":
        if len(set(self.eligible_worker_ids)) != len(self.eligible_worker_ids):
            raise ValueError("Eligible worker IDs must be unique")
        if self.failover_enabled and len(self.eligible_worker_ids) < 2:
            raise ValueError("Failover requires at least two eligible workers")
        return self


class Box(BoxCreationRequest):
    box_id: UUID
    primary_worker_id: WorkerId | None = None
    standby_worker_id: WorkerId | None = None
    status: BoxStatus
    deployment_id: UUID | None = None

    @model_validator(mode="after")
    def check_placement(self) -> "Box":
        for worker_id in (self.primary_worker_id, self.standby_worker_id):
            if worker_id is not None and worker_id not in self.eligible_worker_ids:
                raise ValueError("Placed workers must be eligible")
        if self.standby_worker_id is not None:
            if not self.failover_enabled or self.primary_worker_id is None:
                raise ValueError("Standby requires failover and a primary worker")
            if self.standby_worker_id == self.primary_worker_id:
                raise ValueError("Primary and standby must be different workers")
        # A degraded Box may temporarily have no standby; scheduling validates it.
        return self


class Deployment(ContractModel):
    deployment_id: UUID
    box_id: UUID
    repository_url: NonEmptyString
    branch: NonEmptyString
    application_type: ApplicationType
    image_reference: NonEmptyString
    status: DeploymentStatus
    public_url: NonEmptyString | None = None
    created_at: AwareDatetime


class Replica(ContractModel):
    replica_id: UUID
    deployment_id: UUID
    worker_id: WorkerId
    container_id: NonEmptyString | None = None
    role: ReplicaRole
    status: ReplicaStatus
    internal_port: Port


class RunContainerCommand(ContractModel):
    type: Literal["run_container"] = "run_container"
    request_id: UUID
    deployment_id: UUID
    box_id: UUID
    image_reference: NonEmptyString
    container_name: Annotated[
        str,
        Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$"),
    ]
    cpu_limit_cores: PositiveFloat
    ram_limit_mb: PositiveInt
    storage_limit_gb: PositiveFloat | None = None
    internal_port: Port
    environment_variables: dict[str, str] = Field(default_factory=dict)
    role: ReplicaRole

    @model_validator(mode="after")
    def check_environment(self) -> "RunContainerCommand":
        for key, value in self.environment_variables.items():
            if not key or "=" in key or "\x00" in key or "\x00" in value:
                raise ValueError("Invalid environment variable name or value")
        return self


class StopContainerCommand(ContractModel):
    type: Literal["stop_container"] = "stop_container"
    request_id: UUID
    deployment_id: UUID
    container_id: NonEmptyString


class InspectContainerCommand(ContractModel):
    type: Literal["inspect_container"] = "inspect_container"
    request_id: UUID
    container_id: NonEmptyString


class PortBinding(ContractModel):
    internal_port: Port
    host_ip: NonEmptyString
    host_port: Port
    protocol: Literal["tcp", "udp"] = "tcp"


class ContainerInspection(ContractModel):
    container_id: NonEmptyString
    deployment_id: UUID
    status: ContainerStatus
    health: Literal["not_configured", "starting", "healthy", "unhealthy"]
    cpu_limit_cores: NonNegativeFloat
    ram_limit_bytes: NonNegativeInt
    memory_usage_bytes: NonNegativeInt | None = None
    port_bindings: list[PortBinding] = Field(default_factory=list)


class LeaseGrant(ContractModel):
    type: Literal["lease"] = "lease"
    worker_id: WorkerId
    lease_id: UUID
    issued_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def check_interval(self) -> "LeaseGrant":
        seconds = (self.expires_at - self.issued_at).total_seconds()
        if not 0 < seconds <= 60:
            raise ValueError("Worker lease duration must be in (0, 60] seconds")
        return self


class CommandResult(ContractModel):
    type: Literal["command_result"] = "command_result"
    request_id: UUID
    success: Annotated[bool, Field(strict=True)]
    container_id: NonEmptyString | None = None
    message: str
    inspection: ContainerInspection | None = None


class Heartbeat(ContractModel):
    type: Literal["heartbeat"] = "heartbeat"
    worker_id: WorkerId
    cpu_usage_percent: Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]
    available_ram_gb: NonNegativeFloat
    available_storage_gb: NonNegativeFloat
    active_container_count: NonNegativeInt
    running_containers: list[NonEmptyString]
    timestamp: AwareDatetime


class ContainerStatusEvent(ContractModel):
    type: Literal["container_status"] = "container_status"
    deployment_id: UUID
    container_id: NonEmptyString
    status: ContainerStatus
    timestamp: AwareDatetime


class ContainerLogsEvent(ContractModel):
    type: Literal["container_logs"] = "container_logs"
    deployment_id: UUID
    container_id: NonEmptyString
    log_level: LogLevel
    message: str
    timestamp: AwareDatetime


ControlPlaneCommand = Annotated[
    RunContainerCommand | StopContainerCommand | InspectContainerCommand,
    Field(discriminator="type"),
]
WorkerMessage = Annotated[
    CommandResult | Heartbeat | ContainerStatusEvent | ContainerLogsEvent,
    Field(discriminator="type"),
]
CONTROL_PLANE_COMMAND_ADAPTER = TypeAdapter(ControlPlaneCommand)
ControlPlaneMessage = Annotated[
    RunContainerCommand | StopContainerCommand | InspectContainerCommand | LeaseGrant,
    Field(discriminator="type"),
]
CONTROL_PLANE_MESSAGE_ADAPTER = TypeAdapter(ControlPlaneMessage)
WORKER_MESSAGE_ADAPTER = TypeAdapter(WorkerMessage)


class ResourceReservation(ResourceRequirements):
    reservation_id: UUID
    box_id: UUID
    worker_id: WorkerId
    role: ReplicaRole
    container_slots: PositiveInt = 1


class WorkerCapacity(ContractModel):
    worker_id: WorkerId
    available_cpu_cores: NonNegativeFloat
    available_ram_gb: NonNegativeFloat
    available_storage_gb: NonNegativeFloat
    available_container_slots: NonNegativeInt


class BoxValidationResult(ContractModel):
    valid: bool
    errors: list[NonEmptyString] = Field(default_factory=list)
    eligible_worker_ids: list[WorkerId] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_outcome(self) -> "BoxValidationResult":
        if self.valid == bool(self.errors):
            raise ValueError(
                "Valid results have no errors; invalid results need errors"
            )
        return self


class PlacementDecision(ContractModel):
    box_id: UUID
    primary_worker_id: WorkerId
    standby_worker_id: WorkerId | None = None
    reason: NonEmptyString
    reservations: list[ResourceReservation] = Field(min_length=1)

    @model_validator(mode="after")
    def check_reservations(self) -> "PlacementDecision":
        expected = {(self.primary_worker_id, ReplicaRole.PRIMARY)}
        if self.standby_worker_id is not None:
            if self.standby_worker_id == self.primary_worker_id:
                raise ValueError("Primary and standby must be different workers")
            expected.add((self.standby_worker_id, ReplicaRole.STANDBY))
        actual = {(item.worker_id, item.role) for item in self.reservations}
        if actual != expected or len(self.reservations) != len(expected):
            raise ValueError("Exactly one reservation is required per placed worker")
        if any(item.box_id != self.box_id for item in self.reservations):
            raise ValueError("Reservation Box IDs must match the placement")
        if len({item.reservation_id for item in self.reservations}) != len(expected):
            raise ValueError("Reservation IDs must be unique")
        return self


class WorkerSelectionResult(ContractModel):
    worker_id: WorkerId | None = None
    reason: NonEmptyString


class ReservationReleaseResult(ContractModel):
    box_id: UUID
    reservations: list[ResourceReservation]
    released_reservation_ids: list[UUID]


class FailoverDecision(ContractModel):
    decision_id: UUID
    deployment_id: UUID
    box_id: UUID
    failed_worker_id: WorkerId
    replacement_worker_id: WorkerId | None = None
    state: FailoverState
    reason: NonEmptyString
