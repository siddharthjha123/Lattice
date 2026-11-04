"""Authenticated full snapshots and graceful disconnect hooks for the gateway."""

from urllib.parse import quote

import httpx

from worker_agent.security.auth import WorkerAuthenticationError, authentication_headers


class ControlPlaneUnavailable(RuntimeError):
    """Lifecycle notification could not be delivered."""


class ControlPlaneLifecycle:
    def __init__(self, settings, worker_id, client=None):
        self.settings = settings
        self.worker_id = worker_id
        self.lease_id = None
        self.client = client or httpx.AsyncClient(
            timeout=settings.connect_timeout,
            follow_redirects=False,
            trust_env=False,
        )

    async def _post(self, path, payload=None) -> None:
        try:
            response = await self.client.post(
                self.settings.http_url + path,
                headers=authentication_headers(
                    self.worker_id, self.settings.worker_token
                )
                | ({"X-Worker-Lease-ID": str(self.lease_id)} if self.lease_id else {}),
                json=payload,
            )
        except httpx.HTTPError:
            raise ControlPlaneUnavailable(
                "Control Plane HTTP connection failed"
            ) from None
        if response.status_code in {401, 403}:
            raise WorkerAuthenticationError("Worker authentication was rejected")
        if not 200 <= response.status_code < 300:
            raise ControlPlaneUnavailable(
                f"Control Plane returned HTTP {response.status_code}"
            )

    async def publish_snapshot(self, snapshot) -> bool:
        path = (
            self.settings.snapshot_path
            or f"/api/workers/{quote(self.worker_id, safe='')}/snapshot"
        )
        await self._post(path, snapshot.model_dump(mode="json"))
        return True

    async def notify_disconnect(self) -> None:
        await self._post(f"/api/workers/{quote(self.worker_id, safe='')}/disconnect")

    async def close(self) -> None:
        await self.client.aclose()
