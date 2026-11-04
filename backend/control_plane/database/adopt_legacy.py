"""Explicit, transactional adoption of the team's original unversioned schema.

Never runs on service startup. A private pg_dump backup is required by the CLI.
The legacy shape is checked before additive operations; the revision is stamped
only after data preservation and complete model/schema consistency checks.
"""

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata, produce_migrations
from alembic.migration import MigrationContext
from alembic.operations import Operations, ops
from alembic.script import ScriptDirectory

from control_plane.database import models  # noqa: F401
from control_plane.database.init_db import migration_config
from control_plane.database.session import Base, Database

REVISION = "0001_integrated_schema"
NEW_COLUMNS = {
    "workers": {
        "address",
        "snapshot_at",
        "running_containers",
        "session_id",
        "lease_id",
        "lease_expires_at",
        "draining",
        "fenced_at",
    },
    "boxes": {"deleted_at"},
    "deployments": {
        "application_config",
        "stop_requested",
        "failure_message",
        "architecture",
        "commit_sha",
        "previous_deployment_id",
    },
    "replicas": {
        "request_id",
        "container_status",
        "health",
        "port_bindings",
        "reported_at",
    },
}
DEFAULTS = {
    ("workers", "address"): "'127.0.0.1'",
    ("workers", "running_containers"): "'[]'",
    ("workers", "draining"): "false",
    ("deployments", "application_config"): "'{}'",
    ("deployments", "stop_requested"): "false",
    ("replicas", "request_id"): "gen_random_uuid()",
    ("replicas", "container_status"): "'pending'",
    ("replicas", "health"): "'not_configured'",
    ("replicas", "port_bindings"): "'[]'",
}
LEGACY_TABLES = set(Base.metadata.tables) - {"failover_decisions"}


def legacy_columns(table):
    return [
        column.name
        for column in Base.metadata.tables[table].columns
        if column.name not in NEW_COLUMNS.get(table, set())
    ]


def preflight(connection):
    if connection.dialect.name != "postgresql":
        raise ValueError(
            "Legacy adoption requires PostgreSQL; fresh databases use init_db"
        )
    schema = sa.inspect(connection)
    tables = set(schema.get_table_names())
    if tables != LEGACY_TABLES:
        raise ValueError(
            "Expected exactly the original unversioned tables; inspect the database before adopting"
        )
    for table in sorted(LEGACY_TABLES):
        actual = {column["name"] for column in schema.get_columns(table)}
        if actual != set(legacy_columns(table)):
            raise ValueError(
                f"Unexpected legacy columns in {table}; refusing to guess a migration"
            )
    validations = [
        (
            "duplicate worker tokens",
            "SELECT 1 FROM workers GROUP BY token_hash HAVING count(*)>1 LIMIT 1",
        ),
        (
            "duplicate Box-worker holds",
            "SELECT 1 FROM resource_reservations GROUP BY box_id,worker_id HAVING count(*)>1 LIMIT 1",
        ),
        (
            "duplicate Box-role holds",
            "SELECT 1 FROM resource_reservations GROUP BY box_id,role HAVING count(*)>1 LIMIT 1",
        ),
        (
            "nonpositive reservations",
            "SELECT 1 FROM resource_reservations WHERE ram_limit_gb<=0 OR cpu_limit_cores<=0 OR storage_limit_gb<=0 OR container_slots<=0 LIMIT 1",
        ),
    ]
    for reason, query in validations:
        if connection.execute(sa.text(query)).first():
            raise ValueError(
                f"Cannot adopt: {reason}; existing data needs explicit repair"
            )
    if (
        ScriptDirectory.from_config(migration_config(connection)).get_current_head()
        != REVISION
    ):
        raise ValueError(
            "Migration head changed; this legacy adapter must be reviewed before reuse"
        )


def data_fingerprints(connection):
    result = {}
    for name in sorted(LEGACY_TABLES):
        table = Base.metadata.tables[name]
        columns = [table.c[key] for key in legacy_columns(name)]
        rows = (
            connection.execute(sa.select(*columns).order_by(*table.primary_key.columns))
            .mappings()
            .all()
        )
        serialized = json.dumps(
            [dict(row) for row in rows],
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        ).encode()
        result[name] = {
            "rows": len(rows),
            "sha256": hashlib.sha256(serialized).hexdigest(),
        }
    return result


def leaf_operations(group):
    for operation in group.ops:
        if isinstance(operation, ops.ModifyTableOps):
            yield from leaf_operations(operation)
        else:
            yield operation


def reviewed_operations(connection):
    context = MigrationContext.configure(connection, opts={"compare_type": True})
    migration = produce_migrations(context, Base.metadata)
    operations = list(leaf_operations(migration.upgrade_ops))
    schema = sa.inspect(connection)
    for operation in operations:
        if isinstance(operation, ops.CreateTableOp):
            if operation.table_name != "failover_decisions":
                raise ValueError("Unexpected table creation")
        elif isinstance(operation, ops.AddColumnOp):
            if operation.column.name not in NEW_COLUMNS.get(
                operation.table_name, set()
            ):
                raise ValueError("Unexpected column addition")
            if (
                not operation.column.nullable
                and (operation.table_name, operation.column.name) not in DEFAULTS
            ):
                raise ValueError("Missing reviewed legacy backfill")
        elif isinstance(operation, ops.AlterColumnOp):
            before = operation.existing_type
            after = operation.modify_type
            if (
                not isinstance(before, sa.String)
                or not isinstance(after, sa.String)
                or after.length < before.length
            ):
                raise ValueError("Only reviewed string widening is permitted")
            if (
                operation.modify_nullable is not None
                or operation.modify_server_default is not False
            ):
                raise ValueError("Unexpected change to existing data policy")
        elif isinstance(operation, ops.DropIndexOp):
            if operation.index_name != "ix_workers_token_hash":
                raise ValueError("Unexpected index removal")
        elif isinstance(operation, ops.CreateIndexOp):
            if operation.table_name not in {"workers", "failover_decisions"}:
                raise ValueError("Unexpected index creation")
        elif isinstance(operation, ops.CreateUniqueConstraintOp):
            if operation.table_name not in {
                "resource_reservations",
                "replicas",
                "failover_decisions",
            }:
                raise ValueError("Unexpected unique constraint")
        else:
            raise TypeError(f"Unreviewed operation: {type(operation).__name__}")
    if any(
        row["name"] == "ck_reservation_positive"
        for row in schema.get_check_constraints("resource_reservations")
    ):
        raise ValueError("Legacy constraint state differs from the reviewed schema")
    return operations


def preview(connection):
    preflight(connection)
    return [
        {
            "operation": type(op).__name__,
            "table": getattr(op, "table_name", None),
            "column": getattr(
                getattr(op, "column", None), "name", getattr(op, "column_name", None)
            ),
        }
        for op in reviewed_operations(connection)
    ]


def apply_adoption(connection):
    preflight(connection)
    before = data_fingerprints(connection)
    operations = reviewed_operations(connection)
    runner = Operations(MigrationContext.configure(connection))
    for operation in operations:
        if isinstance(operation, ops.AddColumnOp):
            column = operation.column
            default = DEFAULTS.get((operation.table_name, column.name))
            runner.add_column(
                operation.table_name,
                sa.Column(
                    column.name,
                    column.type,
                    nullable=column.nullable,
                    server_default=sa.text(default) if default else None,
                ),
            )
            if default:
                runner.alter_column(
                    operation.table_name, column.name, server_default=None
                )
        else:
            runner.invoke(operation)
    runner.create_check_constraint(
        "ck_reservation_positive",
        "resource_reservations",
        "ram_limit_gb > 0 AND cpu_limit_cores > 0 AND storage_limit_gb > 0 AND container_slots > 0",
    )
    differences = compare_metadata(
        MigrationContext.configure(connection, opts={"compare_type": True}),
        Base.metadata,
    )
    if differences:
        raise RuntimeError(
            "Adopted schema does not match the frozen integrated schema; transaction rolled back"
        )
    after = data_fingerprints(connection)
    if before != after:
        raise RuntimeError(
            "Legacy data preservation check failed; transaction rolled back"
        )
    command.stamp(migration_config(connection), REVISION)
    return {
        "revision": REVISION,
        "operations": len(operations) + 1,
        "existing_data_preserved": True,
        "tables": after,
    }


def verified_backup(path):
    if path.is_symlink():
        raise ValueError("Backup must not be a symlink")
    info = path.stat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
    ):
        raise ValueError("Backup must be an owner-only regular file (0600)")
    with path.open("rb") as source:
        if source.read(5) != b"PGDMP":
            raise ValueError("A custom-format pg_dump backup is required")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        type=Path,
        help="Owner-only environment file; exported environment still takes precedence",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the reviewed adoption transaction; otherwise preview only",
    )
    parser.add_argument(
        "--backup", type=Path, help="Owner-only pre-migration pg_dump custom archive"
    )
    parser.add_argument("--report", type=Path, help="Private JSON evidence path")
    args = parser.parse_args(argv)
    from control_plane.config import settings

    if args.env_file:
        from control_plane.environment import load_settings_file

        settings = load_settings_file(args.env_file)
    database = Database(
        settings.normalized_database_url,
        resolve_host=settings.DATABASE_DIRECT_DNS,
        encrypted_dns=settings.DATABASE_DNS_OVER_HTTPS,
    )
    try:
        digest = None
        if args.apply:
            if args.backup is None:
                raise ValueError("--apply requires --backup")
            digest = verified_backup(args.backup)
        with database.engine.begin() as connection:
            connection.execute(sa.text("SET LOCAL lock_timeout='5s'"))
            connection.execute(sa.text("SET LOCAL statement_timeout='30s'"))
            connection.execute(sa.text("SET LOCAL TIME ZONE 'UTC'"))
            if args.apply:
                if not connection.execute(
                    sa.text("SELECT pg_try_advisory_xact_lock(172917,1)")
                ).scalar_one():
                    raise RuntimeError(
                        "A controller owns this database; stop it before adoption"
                    )
                # Lock the original tables together so the before/after evidence
                # cannot be affected by another writer during this short change.
                identifiers = ", ".join(
                    '"' + name + '"' for name in sorted(LEGACY_TABLES)
                )
                connection.exec_driver_sql(
                    "LOCK TABLE " + identifiers + " IN ACCESS EXCLUSIVE MODE"
                )
                result = apply_adoption(connection)
                result["backup_sha256"] = digest
            else:
                connection.execute(sa.text("SET TRANSACTION READ ONLY"))
                result = {"planned_operations": preview(connection)}
        if args.report:
            descriptor = os.open(
                args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            with os.fdopen(descriptor, "w") as output:
                json.dump(result, output, indent=2)
        print(json.dumps(result, indent=2))
        return 0
    except Exception as error:  # noqa: BLE001 -- never disclose DB URLs/credentials in CLI failures
        print(
            "Legacy adoption failed:",
            type(error).__name__,
            "; no connection credentials printed",
        )
        if isinstance(error, (ValueError, RuntimeError)):
            print(str(error))
        return 1
    finally:
        database.close()


if __name__ == "__main__":
    raise SystemExit(main())
