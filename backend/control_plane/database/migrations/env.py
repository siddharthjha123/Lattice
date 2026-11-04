"""Alembic uses the application's explicit connection, never a cloud default."""

from alembic import context
from control_plane.database import models  # noqa: F401
from control_plane.database.session import Base

connection = context.config.attributes["connection"]
context.configure(
    connection=connection, target_metadata=Base.metadata, compare_type=True
)
with context.begin_transaction():
    context.run_migrations()
