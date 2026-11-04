"""Apply versioned database migrations to an explicitly configured database."""

from pathlib import Path

from alembic import command
from alembic.config import Config


def migration_config(connection):
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    config.attributes["connection"] = connection
    return config


def init_db(engine=None):
    owned = engine is None
    if owned:
        from control_plane.config import settings
        from control_plane.database.session import Database

        database = Database(
            settings.normalized_database_url,
            resolve_host=settings.DATABASE_DIRECT_DNS,
            encrypted_dns=settings.DATABASE_DNS_OVER_HTTPS,
        )
        engine = database.engine
    try:
        with engine.begin() as connection:
            command.upgrade(migration_config(connection), "head")
    finally:
        if owned:
            database.close()


if __name__ == "__main__":
    init_db()
