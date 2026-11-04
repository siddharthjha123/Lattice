"""SQLAlchemy database models for Control Plane."""

import uuid
from datetime import UTC, datetime

from shared.enums import (
    BoxStatus,
    DeploymentStatus,
    LogLevel,
    ReplicaRole,
    ReplicaStatus,
    WorkerStatus,
)
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Uuid as PG_UUID,
)
from sqlalchemy.orm import relationship

from control_plane.database.session import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class Pool(Base):
    __tablename__ = "pools"
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    pool_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(48), nullable=False, unique=True)
    code_hash = Column(String(256), nullable=False)
    code_expires_at = Column(DateTime(timezone=True), nullable=False)
    max_joins = Column(Integer, nullable=False, default=10)
    joins_used = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class Worker(Base):
    __tablename__ = "workers"
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    worker_id = Column(String(256), primary_key=True)
    pool_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("pools.pool_id", name="fk_worker_pool"),
        nullable=True,
        index=True,
    )
    application_transport = Column(
        String(16), nullable=False, default="direct", server_default="direct"
    )
    hostname = Column(String(255), nullable=False)
    status = Column(String(32), default=WorkerStatus.ONLINE, index=True, nullable=False)
    cpu_cores = Column(Integer, nullable=False)
    available_cpu_cores = Column(Float, nullable=False)
    total_ram_gb = Column(Float, nullable=False)
    available_ram_gb = Column(Float, nullable=False)
    total_storage_gb = Column(Float, nullable=False)
    available_storage_gb = Column(Float, nullable=False)
    active_container_count = Column(Integer, default=0, nullable=False)
    max_containers = Column(Integer, nullable=False)
    architecture = Column(String(64), nullable=False)
    supported_runtimes = Column(
        JSON, nullable=False
    )  # list of strings: ["python", "node"]
    token_hash = Column(String(256), nullable=False, index=True, unique=True)
    last_heartbeat = Column(DateTime(timezone=True), nullable=True)
    registered_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    disconnected_at = Column(DateTime(timezone=True), nullable=True)
    address = Column(String(255), default="127.0.0.1", nullable=False)
    snapshot_at = Column(DateTime(timezone=True), nullable=True)
    running_containers = Column(JSON, default=list, nullable=False)
    session_id = Column(PG_UUID(as_uuid=True), nullable=True)
    lease_id = Column(PG_UUID(as_uuid=True), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    draining = Column(Boolean, default=False, nullable=False)
    fenced_at = Column(DateTime(timezone=True), nullable=True)

    replicas = relationship(
        "Replica", back_populates="worker", cascade="all, delete-orphan"
    )
    reservations = relationship(
        "ResourceReservation", back_populates="worker", cascade="all, delete-orphan"
    )


class Box(Base):
    __tablename__ = "boxes"

    box_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pool_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("pools.pool_id", name="fk_box_pool"),
        nullable=True,
        index=True,
    )
    name = Column(String(256), nullable=False, index=True)
    ram_limit_gb = Column(Float, nullable=False)
    cpu_limit_cores = Column(Float, nullable=False)
    storage_limit_gb = Column(Float, nullable=False)
    eligible_worker_ids = Column(JSON, nullable=False)  # list of worker_ids
    primary_worker_id = Column(String(256), nullable=True)
    standby_worker_id = Column(String(256), nullable=True)
    failover_enabled = Column(Boolean, default=False, nullable=False)
    status = Column(String(32), default=BoxStatus.AVAILABLE, index=True, nullable=False)
    deployment_id = Column(PG_UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    deleted_at = Column(DateTime(timezone=True), nullable=True)

    deployments = relationship(
        "Deployment", back_populates="box", cascade="all, delete-orphan"
    )
    reservations = relationship(
        "ResourceReservation", back_populates="box", cascade="all, delete-orphan"
    )


class Deployment(Base):
    __tablename__ = "deployments"

    deployment_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    box_id = Column(
        PG_UUID(as_uuid=True), ForeignKey("boxes.box_id"), nullable=False, index=True
    )
    repository_url = Column(String(512), nullable=False)
    branch = Column(String(256), nullable=False, default="main")
    application_type = Column(String(32), nullable=False)
    image_reference = Column(String(512), nullable=False)
    status = Column(
        String(32), default=DeploymentStatus.QUEUED, index=True, nullable=False
    )
    public_url = Column(String(512), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    application_config = Column(JSON, default=dict, nullable=False)
    stop_requested = Column(Boolean, default=False, nullable=False)
    failure_message = Column(Text, nullable=True)
    architecture = Column(String(64), nullable=True)
    commit_sha = Column(String(64), nullable=True)
    previous_deployment_id = Column(PG_UUID(as_uuid=True), nullable=True)

    box = relationship("Box", back_populates="deployments")
    replicas = relationship(
        "Replica", back_populates="deployment", cascade="all, delete-orphan"
    )
    logs = relationship(
        "DeploymentLog", back_populates="deployment", cascade="all, delete-orphan"
    )
    events = relationship(
        "DeploymentEvent", back_populates="deployment", cascade="all, delete-orphan"
    )


class Replica(Base):
    __tablename__ = "replicas"

    replica_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deployment_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("deployments.deployment_id"),
        nullable=False,
        index=True,
    )
    worker_id = Column(
        String(256), ForeignKey("workers.worker_id"), nullable=False, index=True
    )
    container_id = Column(String(256), nullable=True)
    role = Column(String(32), default=ReplicaRole.PRIMARY, nullable=False)
    status = Column(String(32), default=ReplicaStatus.PENDING, nullable=False)
    internal_port = Column(Integer, nullable=False, default=8000)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    request_id = Column(
        PG_UUID(as_uuid=True), default=uuid.uuid4, nullable=False, unique=True
    )
    container_status = Column(String(32), default="pending", nullable=False)
    health = Column(String(32), default="not_configured", nullable=False)
    port_bindings = Column(JSON, default=list, nullable=False)
    reported_at = Column(DateTime(timezone=True), nullable=True)
    deployment = relationship("Deployment", back_populates="replicas")
    worker = relationship("Worker", back_populates="replicas")


class ResourceReservation(Base):
    __tablename__ = "resource_reservations"
    __table_args__ = (
        UniqueConstraint("box_id", "worker_id", name="uq_reservation_box_worker"),
        UniqueConstraint("box_id", "role", name="uq_reservation_box_role"),
        CheckConstraint(
            "ram_limit_gb > 0 AND cpu_limit_cores > 0 AND storage_limit_gb > 0 AND container_slots > 0",
            name="ck_reservation_positive",
        ),
    )

    reservation_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    box_id = Column(
        PG_UUID(as_uuid=True), ForeignKey("boxes.box_id"), nullable=False, index=True
    )
    worker_id = Column(
        String(256), ForeignKey("workers.worker_id"), nullable=False, index=True
    )
    role = Column(String(32), default=ReplicaRole.PRIMARY, nullable=False)
    ram_limit_gb = Column(Float, nullable=False)
    cpu_limit_cores = Column(Float, nullable=False)
    storage_limit_gb = Column(Float, nullable=False)
    container_slots = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    box = relationship("Box", back_populates="reservations")
    worker = relationship("Worker", back_populates="reservations")


class DeploymentLog(Base):
    __tablename__ = "deployment_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    deployment_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("deployments.deployment_id"),
        nullable=False,
        index=True,
    )
    container_id = Column(String(256), nullable=True)
    log_level = Column(String(32), default=LogLevel.INFO, nullable=False)
    message = Column(Text, nullable=False)
    timestamp = Column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    deployment = relationship("Deployment", back_populates="logs")


class DeploymentEvent(Base):
    __tablename__ = "deployment_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    deployment_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("deployments.deployment_id"),
        nullable=False,
        index=True,
    )
    event_type = Column(String(64), nullable=False)
    from_status = Column(String(32), nullable=True)
    to_status = Column(String(32), nullable=True)
    message = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    deployment = relationship("Deployment", back_populates="events")


class FailoverRecord(Base):
    __tablename__ = "failover_decisions"
    __table_args__ = (
        UniqueConstraint("deployment_id", "failed_worker_id", name="uq_failover_event"),
    )
    decision_id = Column(PG_UUID(as_uuid=True), primary_key=True)
    deployment_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("deployments.deployment_id"),
        nullable=False,
        index=True,
    )
    box_id = Column(PG_UUID(as_uuid=True), ForeignKey("boxes.box_id"), nullable=False)
    failed_worker_id = Column(String(256), nullable=False)
    replacement_worker_id = Column(String(256), nullable=True)
    state = Column(String(32), nullable=False)
    reason = Column(Text, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
