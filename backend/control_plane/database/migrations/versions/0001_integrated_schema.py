"""Initial integrated schema; existing prototype databases require an explicit migration review."""

import sqlalchemy as sa
from alembic import op

revision = "0001_integrated_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "boxes",
        sa.Column("box_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("ram_limit_gb", sa.Float(), nullable=False),
        sa.Column("cpu_limit_cores", sa.Float(), nullable=False),
        sa.Column("storage_limit_gb", sa.Float(), nullable=False),
        sa.Column("eligible_worker_ids", sa.JSON(), nullable=False),
        sa.Column("primary_worker_id", sa.String(length=256), nullable=True),
        sa.Column("standby_worker_id", sa.String(length=256), nullable=True),
        sa.Column("failover_enabled", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("deployment_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("box_id"),
    )
    op.create_index(op.f("ix_boxes_name"), "boxes", ["name"], unique=False)
    op.create_index(op.f("ix_boxes_status"), "boxes", ["status"], unique=False)
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)
    op.create_table(
        "workers",
        sa.Column("worker_id", sa.String(length=256), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("cpu_cores", sa.Integer(), nullable=False),
        sa.Column("available_cpu_cores", sa.Float(), nullable=False),
        sa.Column("total_ram_gb", sa.Float(), nullable=False),
        sa.Column("available_ram_gb", sa.Float(), nullable=False),
        sa.Column("total_storage_gb", sa.Float(), nullable=False),
        sa.Column("available_storage_gb", sa.Float(), nullable=False),
        sa.Column("active_container_count", sa.Integer(), nullable=False),
        sa.Column("max_containers", sa.Integer(), nullable=False),
        sa.Column("architecture", sa.String(length=64), nullable=False),
        sa.Column("supported_runtimes", sa.JSON(), nullable=False),
        sa.Column("token_hash", sa.String(length=256), nullable=False),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("running_containers", sa.JSON(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("lease_id", sa.Uuid(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("draining", sa.Boolean(), nullable=False),
        sa.Column("fenced_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("worker_id"),
    )
    op.create_index(op.f("ix_workers_status"), "workers", ["status"], unique=False)
    op.create_index(
        op.f("ix_workers_token_hash"), "workers", ["token_hash"], unique=True
    )
    op.create_table(
        "deployments",
        sa.Column("deployment_id", sa.Uuid(), nullable=False),
        sa.Column("box_id", sa.Uuid(), nullable=False),
        sa.Column("repository_url", sa.String(length=512), nullable=False),
        sa.Column("branch", sa.String(length=256), nullable=False),
        sa.Column("application_type", sa.String(length=32), nullable=False),
        sa.Column("image_reference", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("public_url", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("application_config", sa.JSON(), nullable=False),
        sa.Column("stop_requested", sa.Boolean(), nullable=False),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("architecture", sa.String(length=64), nullable=True),
        sa.Column("commit_sha", sa.String(length=64), nullable=True),
        sa.Column("previous_deployment_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["box_id"],
            ["boxes.box_id"],
        ),
        sa.PrimaryKeyConstraint("deployment_id"),
    )
    op.create_index(
        op.f("ix_deployments_box_id"), "deployments", ["box_id"], unique=False
    )
    op.create_index(
        op.f("ix_deployments_status"), "deployments", ["status"], unique=False
    )
    op.create_table(
        "resource_reservations",
        sa.Column("reservation_id", sa.Uuid(), nullable=False),
        sa.Column("box_id", sa.Uuid(), nullable=False),
        sa.Column("worker_id", sa.String(length=256), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("ram_limit_gb", sa.Float(), nullable=False),
        sa.Column("cpu_limit_cores", sa.Float(), nullable=False),
        sa.Column("storage_limit_gb", sa.Float(), nullable=False),
        sa.Column("container_slots", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "ram_limit_gb > 0 AND cpu_limit_cores > 0 AND storage_limit_gb > 0 AND container_slots > 0",
            name="ck_reservation_positive",
        ),
        sa.ForeignKeyConstraint(
            ["box_id"],
            ["boxes.box_id"],
        ),
        sa.ForeignKeyConstraint(
            ["worker_id"],
            ["workers.worker_id"],
        ),
        sa.PrimaryKeyConstraint("reservation_id"),
        sa.UniqueConstraint("box_id", "role", name="uq_reservation_box_role"),
        sa.UniqueConstraint("box_id", "worker_id", name="uq_reservation_box_worker"),
    )
    op.create_index(
        op.f("ix_resource_reservations_box_id"),
        "resource_reservations",
        ["box_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_resource_reservations_worker_id"),
        "resource_reservations",
        ["worker_id"],
        unique=False,
    )
    op.create_table(
        "deployment_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("deployment_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["deployment_id"],
            ["deployments.deployment_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_deployment_events_deployment_id"),
        "deployment_events",
        ["deployment_id"],
        unique=False,
    )
    op.create_table(
        "deployment_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("deployment_id", sa.Uuid(), nullable=False),
        sa.Column("container_id", sa.String(length=256), nullable=True),
        sa.Column("log_level", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["deployment_id"],
            ["deployments.deployment_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_deployment_logs_deployment_id"),
        "deployment_logs",
        ["deployment_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_deployment_logs_timestamp"),
        "deployment_logs",
        ["timestamp"],
        unique=False,
    )
    op.create_table(
        "failover_decisions",
        sa.Column("decision_id", sa.Uuid(), nullable=False),
        sa.Column("deployment_id", sa.Uuid(), nullable=False),
        sa.Column("box_id", sa.Uuid(), nullable=False),
        sa.Column("failed_worker_id", sa.String(length=256), nullable=False),
        sa.Column("replacement_worker_id", sa.String(length=256), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["box_id"],
            ["boxes.box_id"],
        ),
        sa.ForeignKeyConstraint(
            ["deployment_id"],
            ["deployments.deployment_id"],
        ),
        sa.PrimaryKeyConstraint("decision_id"),
        sa.UniqueConstraint(
            "deployment_id", "failed_worker_id", name="uq_failover_event"
        ),
    )
    op.create_index(
        op.f("ix_failover_decisions_deployment_id"),
        "failover_decisions",
        ["deployment_id"],
        unique=False,
    )
    op.create_table(
        "replicas",
        sa.Column("replica_id", sa.Uuid(), nullable=False),
        sa.Column("deployment_id", sa.Uuid(), nullable=False),
        sa.Column("worker_id", sa.String(length=256), nullable=False),
        sa.Column("container_id", sa.String(length=256), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("internal_port", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("container_status", sa.String(length=32), nullable=False),
        sa.Column("health", sa.String(length=32), nullable=False),
        sa.Column("port_bindings", sa.JSON(), nullable=False),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["deployment_id"],
            ["deployments.deployment_id"],
        ),
        sa.ForeignKeyConstraint(
            ["worker_id"],
            ["workers.worker_id"],
        ),
        sa.PrimaryKeyConstraint("replica_id"),
        sa.UniqueConstraint("request_id"),
    )
    op.create_index(
        op.f("ix_replicas_deployment_id"), "replicas", ["deployment_id"], unique=False
    )
    op.create_index(
        op.f("ix_replicas_worker_id"), "replicas", ["worker_id"], unique=False
    )


def downgrade():
    raise RuntimeError(
        "Destructive downgrade is intentionally unsupported; restore a reviewed backup"
    )
