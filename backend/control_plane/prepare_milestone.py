"""Apply explicit setup and create one real pool; does not connect or deploy tests."""

import argparse
import json
import os
from pathlib import Path

from alembic import command
from sqlalchemy import text
from sqlalchemy.orm import Session

from control_plane.database.init_db import migration_config
from control_plane.database.session import Database
from control_plane.environment import load_settings_file
from control_plane.services.pools import create_pool


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--pool-name", default="development")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from control_plane.api.pools import PoolCreate

    payload = PoolCreate(name=args.pool_name)
    config = load_settings_file(args.env_file)
    if args.output.exists() or args.output.is_symlink():
        raise RuntimeError(
            "Setup output already exists; do not silently rotate pool credentials"
        )
    database = Database(
        config.normalized_database_url, resolve_host=config.DATABASE_DIRECT_DNS
    )
    created = False
    try:
        with database.engine.begin() as connection:
            if connection.dialect.name == "postgresql":
                connection.execute(text("SET LOCAL lock_timeout='5s'"))
                if not connection.execute(
                    text("SELECT pg_try_advisory_xact_lock(172917,1)")
                ).scalar_one():
                    raise RuntimeError("Stop the controller before applying pool setup")
            command.upgrade(migration_config(connection), "head")
            with (
                Session(
                    bind=connection, join_transaction_mode="create_savepoint"
                ) as session,
                session.begin(),
            ):
                result = create_pool(
                    session,
                    payload.name,
                    config,
                    hours=payload.expires_hours,
                    max_joins=payload.max_joins,
                )
            args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd = os.open(
                args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            created = True
            with os.fdopen(fd, "w") as output:
                json.dump(result, output, indent=2)
                output.flush()
                os.fsync(output.fileno())
        print(
            "Pool setup committed. Join details saved privately to " + str(args.output)
        )
    except Exception:
        if created:
            args.output.unlink(missing_ok=True)
        raise
    finally:
        database.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # noqa: BLE001 -- protect credentials in setup errors
        print(
            "Pool setup failed:", type(error).__name__, "; no secret values displayed"
        )
        raise SystemExit(1)
