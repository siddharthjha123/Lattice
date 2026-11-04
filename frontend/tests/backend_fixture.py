"""Isolated UI validation fixture. Never use this server for real deployments."""

import json
import re
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse
from uuid import uuid4

TOKEN = "fixture-operator-token-for-ui-validation-only"
POOL_ID = "11111111-1111-4111-8111-111111111111"
def NOW():
    return datetime.now(timezone.utc).isoformat()
pools = [{"pool_id": POOL_ID, "name": "ui-validation-only", "join_code_expires_at": "2099-01-01T00:00:00Z", "joins_used": 2, "max_joins": 10, "created_at": NOW()}]
workers = [{"worker_id": f"22222222-2222-4222-8222-22222222222{i}", "hostname": f"UI fixture worker {i}", "status": "online", "cpu_cores": 4, "available_cpu_cores": 2, "total_ram_gb": 8, "available_ram_gb": 4, "total_storage_gb": 100, "available_storage_gb": 20, "active_container_count": 0, "max_containers": 4, "architecture": "x86_64", "supported_runtimes": ["python", "node"], "control_connected": True, "application_relay_connected": True} for i in (1, 2)]
boxes = []
deployments = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send(self, value, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if status != 204:
            self.wfile.write(json.dumps(value).encode())

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            return self.send({"status": "healthy", "database": "isolated-ui-fixture", "service": "control_plane_fixture", "connected_workers": 2, "timestamp": NOW()})
        if self.headers.get("Authorization") != "Bearer " + TOKEN:
            return self.send({"detail": "Invalid fixture operator token"}, 401)
        for worker in workers:
            worker["last_heartbeat"] = NOW()
        if path == "/api/pools":
            return self.send(pools)
        if path.startswith("/api/pools/") and path.endswith("/status"):
            p = next((p for p in pools if p["pool_id"] == path.split("/")[3]), None)
            return self.send(p | {"workers": workers if p["pool_id"] == POOL_ID else [], "deployments": []}) if p else self.send({"detail": "Pool not found"}, 404)
        if path == "/api/workers":
            return self.send(workers)
        if path.startswith("/api/workers/"):
            return self.send(next((w for w in workers if w["worker_id"] == path.split("/")[3]), {}))
        if path == "/api/boxes":
            return self.send(boxes)
        if path == "/api/deployments":
            return self.send(deployments)
        if path.startswith("/api/deployments/"):
            identity = path.split("/")[3]
            dep = next((d for d in deployments if d["deployment_id"] == identity), None)
            if not dep:
                return self.send({"detail": "Deployment not found"}, 404)
            if path.endswith("/logs"):
                return self.send({"deployment_id": identity, "logs": [{"timestamp": NOW(), "log_level": "info", "message": "UI validation fixture only: no real image build or app execution", "container_id": None}]})
            if path.endswith("/status"):
                return self.send(dep | {"stop_requested": False, "failure_message": None, "updated_at": NOW(), "replicas": []})
            return self.send(dep)
        return self.send({"detail": "Not found in UI fixture"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        if self.headers.get("Authorization") != "Bearer " + TOKEN:
            return self.send({"detail": "Invalid fixture operator token"}, 401)
        payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or "{}")
        if path == "/api/pools":
            if not re.fullmatch(r"[a-z][a-z0-9-]{2,47}", payload.get("name", "")):
                return self.send({"detail": [{"loc": ["body", "name"], "type": "string_pattern_mismatch"}]}, 422)
            if any(p["name"] == payload["name"] for p in pools):
                return self.send({"detail": "Pool name already exists; rotate its join code explicitly"}, 409)
            p = {"pool_id": str(uuid4()), "name": payload["name"], "join_code_expires_at": "2099-01-01T00:00:00Z", "max_joins": payload.get("max_joins", 10), "joins_used": 0, "created_at": NOW()}
            pools.append(p)
            return self.send(p | {"pool_code": "LTC-FIXTURE-ONLY-NOT-REAL"}, 201)
        if path.endswith("/rotate-code"):
            p = next(p for p in pools if p["pool_id"] == path.split("/")[3])
            return self.send(p | {"pool_code": "LTC-ROTATED-FIXTURE-ONLY"})
        if path == "/api/boxes":
            if payload.get("pool_id") != POOL_ID:
                return self.send({"detail": "This isolated fixture only has connected workers in ui-validation-only"}, 400)
            b = {k: v for k, v in payload.items() if k != "pool_id"} | {"box_id": str(uuid4()), "status": "available", "primary_worker_id": workers[0]["worker_id"], "standby_worker_id": workers[1]["worker_id"], "deployment_id": None}
            boxes.append(b)
            return self.send(b, 201)
        if path == "/api/deployments":
            d = payload | {"deployment_id": str(uuid4()), "status": "queued", "image_reference": "fixture:no-image-built", "public_url": None, "created_at": NOW()}
            deployments.append(d)
            return self.send(d, 201)
        if path.endswith("/stop"):
            dep = next(d for d in deployments if d["deployment_id"] == path.split("/")[3])
            dep["status"] = "stopped"
            return self.send({"deployment_id": dep["deployment_id"], "status": "stopped"})
        return self.send({"detail": "Not implemented by this fixture"}, 404)


if __name__ == "__main__":
    print("UI fixture only; listening on 127.0.0.1:3421", flush=True)
    HTTPServer(("127.0.0.1", 3421), Handler).serve_forever()
