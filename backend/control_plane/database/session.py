"""Short transactional sessions; async callers keep database I/O off the loop."""

import asyncio
import threading
from contextlib import contextmanager, nullcontext

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

Base = declarative_base()


class Database:
    def __init__(self, url, *, resolve_host=False, encrypted_dns=False):
        sqlite = url.startswith("sqlite")
        options = {"pool_pre_ping": True, "hide_parameters": True}
        if not sqlite:
            options["pool_timeout"] = 10
            options["pool_recycle"] = 300
            options["connect_args"] = {
                "connect_timeout": 10,
                "options": "-c statement_timeout=15000 -c lock_timeout=5000",
                "keepalives": 1,
                "keepalives_idle": 15,
                "keepalives_interval": 5,
                "keepalives_count": 3,
            }
        if sqlite:
            options["connect_args"] = {"check_same_thread": False}
            if url in {"sqlite://", "sqlite:///:memory:"}:
                options["poolclass"] = StaticPool
        self.engine = create_engine(url, **options)
        if (
            not sqlite
            and (resolve_host or encrypted_dns)
            and "hostaddr" not in make_url(url).query
        ):
            from control_plane.database.encrypted_resolution import EncryptedResolver
            from control_plane.database.resolution import resolve_connection_address

            resolver = EncryptedResolver() if encrypted_dns else None

            @event.listens_for(self.engine, "do_connect")
            def direct_resolution(dialect, record, arguments, parameters):
                # Refresh each new connection, including after DB address changes.
                parameters.pop("hostaddr", None)
                address = (
                    resolver.resolve(parameters)
                    if resolver
                    else resolve_connection_address(parameters)
                )
                if address is not None:
                    parameters["hostaddr"] = address
                # parameters['host'], sslmode and sslrootcert remain untouched.

        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.lock = threading.Lock() if sqlite else None
        if sqlite:

            @event.listens_for(self.engine, "connect")
            def foreign_keys(connection, _):
                connection.execute("PRAGMA foreign_keys=ON")

    @contextmanager
    def session(self):
        with (
            self.lock if self.lock is not None else nullcontext(),
            self.SessionLocal() as session,
        ):
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    async def run(self, operation):
        def transact():
            with self.session() as session:
                return operation(session)

        return await asyncio.to_thread(transact)

    def close(self):
        self.engine.dispose()
