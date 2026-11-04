"""Retire inventory without cascading deletion of deployment history."""

import sqlalchemy as sa
from alembic import op

revision = "0003_retired_inventory"
down_revision = "0002_pools_and_relay"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "workers", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "pools", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade():
    raise RuntimeError(
        "Restore a reviewed backup rather than resurrecting retired credentials"
    )
