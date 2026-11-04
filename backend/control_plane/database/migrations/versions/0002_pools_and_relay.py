"""Add logical pools and outbound application transport without changing history."""

import sqlalchemy as sa
from alembic import op

revision = "0002_pools_and_relay"
down_revision = "0001_integrated_schema"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pools",
        sa.Column("pool_id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(48), nullable=False, unique=True),
        sa.Column("code_hash", sa.String(256), nullable=False),
        sa.Column("code_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_joins", sa.Integer(), nullable=False),
        sa.Column("joins_used", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    with op.batch_alter_table("workers") as batch:
        batch.add_column(sa.Column("pool_id", sa.Uuid(), nullable=True))
        batch.add_column(
            sa.Column(
                "application_transport",
                sa.String(16),
                nullable=False,
                server_default="direct",
            )
        )
        batch.create_foreign_key("fk_worker_pool", "pools", ["pool_id"], ["pool_id"])
        batch.create_index("ix_workers_pool_id", ["pool_id"])
    with op.batch_alter_table("boxes") as batch:
        batch.add_column(sa.Column("pool_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key("fk_box_pool", "pools", ["pool_id"], ["pool_id"])
        batch.create_index("ix_boxes_pool_id", ["pool_id"])


def downgrade():
    raise RuntimeError("Restore a reviewed backup rather than deleting pool membership")
