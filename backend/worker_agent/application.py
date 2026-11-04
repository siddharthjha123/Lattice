"""Compose the worker adapters and supervise their lifecycle as one process."""

import asyncio
import logging
import os
import signal
import time
from datetime import UTC, datetime

from shared.contracts import LeaseGrant

from worker_agent.communication.client import GatewayClient
from worker_agent.communication.control import ControlServer
from worker_agent.communication.lifecycle import ControlPlaneUnavailable
from worker_agent.communication.reporting import WorkerReporter, wait_interval
from worker_agent.owner import OwnerControls
from worker_agent.security.auth import WorkerAuthenticationError

LOGGER = logging.getLogger(__name__)


class WorkerApplication:
    def __init__(self, runtime, dispatcher, lifecycle, state):
        self.runtime = runtime
        self.settings = runtime.settings
        self.lifecycle = lifecycle
        self.state = state
        self.stop = asyncio.Event()
        self.gateway = GatewayClient(self.settings, runtime.worker_id, dispatcher)
        self.reporter = WorkerReporter(runtime, self.gateway, lifecycle, state)
        self.gateway.on_connect = self.reconcile_session
        self.owner = OwnerControls(runtime, state, self.request_disconnect)
        self.control = ControlServer(state, self.owner.handle)
        self.shutdown_task = None
        self.lease_deadline = 0.0
        self.gateway.on_lease = self.receive_lease
        if self.settings.require_control_plane_lease:
            try:
                saved = LeaseGrant.model_validate(self.state.read_json("lease.json"))
                remaining = (saved.expires_at - datetime.now(UTC)).total_seconds()
                if (
                    saved.worker_id == self.runtime.worker_id
                    and 0 < remaining <= self.settings.max_lease_seconds
                ):
                    self.lease_deadline = time.monotonic() + remaining
                    self.runtime.lease_valid = True
            except (FileNotFoundError, ValueError):
                pass

    async def reconcile_session(self):
        # Never publish a snapshot with a missing/stale lease identifier while
        # the new connection's first LeaseGrant is still buffered on the socket.
        self.lifecycle.lease_id = None
        await self.reporter.reconcile()

    async def receive_lease(self, grant):
        now = datetime.now(UTC)
        if (
            grant.issued_at - now
        ).total_seconds() > self.settings.max_clock_skew_seconds:
            raise WorkerAuthenticationError(
                "Control Plane clock is outside the allowed skew"
            )
        remaining = (grant.expires_at - now).total_seconds()
        if (
            remaining <= 0
            or remaining
            > self.settings.max_lease_seconds + self.settings.max_clock_skew_seconds
        ):
            raise WorkerAuthenticationError("Expired or excessive Control Plane lease")
        self.lease_deadline = time.monotonic() + remaining
        self.runtime.lease_valid = True
        self.lifecycle.lease_id = grant.lease_id
        await asyncio.to_thread(
            self.state.write_json, "lease.json", grant.model_dump(mode="json")
        )

    async def lease_loop(self):
        while not self.stop.is_set():
            if (
                self.settings.require_control_plane_lease
                and time.monotonic() >= self.lease_deadline
            ):
                self.runtime.lease_valid = False
                try:
                    await asyncio.to_thread(self.runtime.fence)
                except Exception as exc:  # noqa: BLE001 -- keep retrying fencing without leaking daemon details
                    LOGGER.error("Lease fencing failed (%s)", type(exc).__name__)
            await wait_interval(self.stop, 0.1)

    async def request_disconnect(self):
        if self.shutdown_task is None:
            # Drain new admissions, but keep applications serving during handoff.
            self.runtime.paused = True
            self.runtime.draining = True
            self.shutdown_task = asyncio.create_task(self._disconnect())
        return {
            "disconnecting": True,
            "grace_seconds": self.settings.disconnect_grace_seconds,
        }

    async def _disconnect(self):
        try:
            await self.lifecycle.notify_disconnect()
            LOGGER.info("Control Plane acknowledged intentional disconnect")
        except (ControlPlaneUnavailable, WorkerAuthenticationError):
            LOGGER.warning("Disconnect notification could not be acknowledged")
        await wait_interval(self.stop, self.settings.disconnect_grace_seconds)
        try:
            if self.settings.stop_on_disconnect:
                await asyncio.to_thread(self.owner.stop, persist_pause=False)
        finally:
            self.stop.set()

    async def run(self, install_signals=True):
        loop = asyncio.get_running_loop()
        signals = (signal.SIGINT, signal.SIGTERM) if install_signals else ()
        tasks = []
        windows_handlers = {}
        stopping = None
        try:
            await self.control.start()
            if self.runtime.paused:
                LOGGER.warning(
                    "Worker paused by saved owner policy; run lattice resume to contribute capacity"
                )
                await asyncio.to_thread(self.owner.pause)
            for signum in signals:
                if os.name == "nt":

                    def on_console_signal(number, frame):
                        loop.call_soon_threadsafe(
                            lambda: asyncio.create_task(self.request_disconnect())
                        )

                    windows_handlers[signum] = signal.signal(signum, on_console_signal)
                else:
                    loop.add_signal_handler(
                        signum, lambda: asyncio.create_task(self.request_disconnect())
                    )
            tasks = [
                asyncio.create_task(self.gateway.run(self.stop)),
                asyncio.create_task(self.reporter.heartbeat_loop(self.stop)),
                asyncio.create_task(self.reporter.event_loop(self.stop)),
                asyncio.create_task(self.lease_loop()),
            ]
            if self.settings.application_relay:
                from worker_agent.communication.application_relay import (
                    WorkerApplicationRelay,
                )

                tasks.append(
                    asyncio.create_task(WorkerApplicationRelay(self).run(self.stop))
                )
            stopping = asyncio.create_task(self.stop.wait())
            done, _ = await asyncio.wait(
                [*tasks, stopping], return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                if task is not stopping:
                    await task
                    if not self.stop.is_set():
                        raise RuntimeError(
                            "Worker background task stopped unexpectedly"
                        )
        finally:
            self.stop.set()
            if stopping is not None:
                stopping.cancel()
                await asyncio.gather(stopping, return_exceptions=True)
            for signum in signals:
                if os.name == "nt":
                    if signum in windows_handlers:
                        signal.signal(signum, windows_handlers[signum])
                else:
                    loop.remove_signal_handler(signum)
            await asyncio.gather(*tasks, return_exceptions=True)
            if self.settings.require_control_plane_lease:
                # The watchdog ends with this process. Do not leave leased
                # containers serving without it, even if handoff was unacknowledged.
                self.runtime.lease_valid = False
                await asyncio.to_thread(self.runtime.fence)
            if self.shutdown_task is not None:
                await asyncio.gather(self.shutdown_task, return_exceptions=True)
            await self.control.close()
