"""One explicit service context per FastAPI app; no import-time connections."""

import asyncio
import fcntl
import os
from hashlib import sha256
from pathlib import Path

from sqlalchemy import text

from control_plane.database.session import Database
from control_plane.services.deployment_manager import DeploymentManager
from control_plane.services.git_builder import GitBuilder
from control_plane.services.websocket_gateway import WorkerConnectionManager


class ServiceContext:
    def __init__(self, config, database=None, builder=None):
        self.config = config
        self.owns_db = database is None
        self.db = database or Database(
            config.normalized_database_url,
            resolve_host=config.DATABASE_DIRECT_DNS,
            encrypted_dns=config.DATABASE_DNS_OVER_HTTPS,
        )
        self.builder = builder or GitBuilder(config)
        self.gateway = WorkerConnectionManager(self.db, config)
        from control_plane.services.application_relay import ApplicationRelay
        from control_plane.services.pools import JoinLimiter

        self.relay = ApplicationRelay(self.gateway)
        self.join_limiter = JoinLimiter()
        self.manager = DeploymentManager(self)
        self.gateway.on_failure = self.manager.schedule_worker_failure
        self.stop = asyncio.Event()
        self.monitor = None
        self.leader_connection = None
        self.lock_descriptor = None

    def acquire_leadership(self):
        if self.db.engine.dialect.name == "postgresql":
            self.leader_connection = self.db.engine.connect()
            held = self.leader_connection.execute(
                text("SELECT pg_try_advisory_lock(172917, 1)")
            ).scalar_one()
            self.leader_connection.commit()
            if not held:
                self.leader_connection.close()
                self.leader_connection = None
                raise RuntimeError(
                    "Another Control Plane owns this database; run one gateway process"
                )
        else:
            key = sha256(self.config.normalized_database_url.encode()).hexdigest()[:16]
            path = Path("/tmp") / f"lattice-controller-{key}.lock"
            self.lock_descriptor = os.open(
                path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
            )
            try:
                fcntl.flock(self.lock_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(self.lock_descriptor)
                self.lock_descriptor = None
                raise RuntimeError("Another Control Plane owns this database") from None

    async def start(self):
        if (
            len(self.config.SECRET_KEY) < 32
            or len(self.config.ADMIN_TOKEN.get_secret_value()) < 32
        ):
            raise RuntimeError(
                "Set SECRET_KEY and ADMIN_TOKEN to distinct random values of at least 32 characters"
            )
        if self.config.SECRET_KEY == self.config.ADMIN_TOKEN.get_secret_value():
            raise RuntimeError("Use different management and token-hashing secrets")
        from control_plane.logging import configure_logging

        configure_logging(self.config)
        await asyncio.to_thread(self.acquire_leadership)
        try:
            if self.config.AUTO_MIGRATE:
                from control_plane.database.init_db import init_db

                await asyncio.to_thread(init_db, self.db.engine)
            await self.db.run(lambda session: session.execute(text("SELECT 1")))
            self.monitor = asyncio.create_task(self.manager.monitor(self.stop))
            await self.manager.resume()
        except Exception:
            await self.close()
            raise

    async def close(self):
        self.stop.set()
        if self.monitor is not None:
            await self.monitor
        await self.manager.shutdown()
        await self.relay.close()
        await self.gateway.close()
        await asyncio.to_thread(self.builder.close)
        if self.leader_connection is not None:
            self.leader_connection.execute(text("SELECT pg_advisory_unlock(172917, 1)"))
            self.leader_connection.commit()
            self.leader_connection.close()
            self.leader_connection = None
        if self.lock_descriptor is not None:
            os.close(self.lock_descriptor)
            self.lock_descriptor = None
        if self.owns_db:
            await asyncio.to_thread(self.db.close)
