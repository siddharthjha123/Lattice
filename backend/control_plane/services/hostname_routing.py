"""Optional flat app hosts; enable only after wildcard DNS/tunnel setup."""

import re
from uuid import UUID


class ApplicationHostnameMiddleware:
    def __init__(self, app, domain, control_hosts):
        self.app = app
        self.domain = domain
        self.control_hosts = set(control_hosts)
        self.pattern = re.compile(r"^app-([a-f0-9]{32})\." + re.escape(domain) + r"$")

    async def __call__(self, scope, receive, send):
        if scope["type"] in {"http", "websocket"}:
            host = next(
                (
                    value.decode("ascii", errors="ignore").split(":", 1)[0].lower()
                    for name, value in scope["headers"]
                    if name == b"host"
                ),
                "",
            )
            match = self.pattern.fullmatch(host)
            unknown = (
                host.endswith("." + self.domain)
                and host not in self.control_hosts
                and not match
            )
            if scope["type"] == "websocket" and (match or unknown):
                await send({"type": "websocket.close", "code": 1003})
                return
            if unknown:
                await send(
                    {
                        "type": "http.response.start",
                        "status": 404,
                        "headers": [(b"content-type", b"text/plain")],
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": b"Unknown application hostname",
                    }
                )
                return
            if match:
                scope = dict(scope)
                path = f"/apps/{UUID(hex=match[1])}" + scope.get("path", "/")
                scope["path"] = path
                scope["raw_path"] = path.encode()
                scope["lattice.app_hostname"] = True
        await self.app(scope, receive, send)
