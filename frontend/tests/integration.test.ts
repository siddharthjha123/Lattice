import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient, setAuthToken, getAuthToken } from "../src/lib/api/client";
import { useAuthStore } from "../src/stores/authStore";
import {
  clearPoolCodes,
  createPool,
  getPool,
  listPools,
  rotatePoolCode,
} from "../src/lib/api/poolsAdapter";
import { boxesForPool } from "../src/lib/api/poolBoxes";
import { fittingWorkers } from "../src/lib/api/admission";
import {
  buildDeploymentRequest,
  readyPublicUrl,
} from "../src/lib/api/deploymentPlan";
import {
  inspectRepository,
  parseGitHubUrl,
} from "../src/lib/api/repoInspectionAdapter";
import { groupProjects } from "../src/lib/api/projectsAdapter";
import { useTelemetryStore } from "../src/stores/telemetryStore";
import { joinCommand } from "../src/lib/constants/downloads";
import type {
  WorkerSnapshot,
  Box,
  Deployment,
  DeploymentStatusResponse,
} from "../src/types/contracts";

class Storage {
  values = new Map<string, string>();
  getItem(key: string) {
    return this.values.get(key) || null;
  }
  setItem(key: string, value: string) {
    this.values.set(key, value);
  }
  removeItem(key: string) {
    this.values.delete(key);
  }
}
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
const pool = {
  pool_id: "pool-a",
  name: "development",
  join_code_expires_at: "2099-01-01T00:00:00Z",
  joins_used: 0,
  max_joins: 10,
  created_at: "2026-11-01T00:00:00Z",
};
const worker = (
  id = "a",
  extra: Partial<WorkerSnapshot> = {},
): WorkerSnapshot => ({
  worker_id: id,
  hostname: id,
  status: "online",
  cpu_cores: 4,
  available_cpu_cores: 2,
  total_ram_gb: 8,
  available_ram_gb: 2,
  total_storage_gb: 100,
  available_storage_gb: 10,
  active_container_count: 0,
  max_containers: 4,
  architecture: "x86_64",
  supported_runtimes: ["python"],
  last_heartbeat: "2026-11-01T00:00:00Z",
  control_connected: true,
  application_relay_connected: true,
  ...extra,
});
const box = (ids: string[]): Box => ({
  box_id: "box-a",
  name: "Box",
  status: "available",
  eligible_worker_ids: ids,
  cpu_limit_cores: 0.5,
  ram_limit_gb: 0.5,
  storage_limit_gb: 1,
});
const plan = {
  repoUrl: "https://github.com/render-examples/flask-hello-world",
  branch: "main",
  boxId: "box-a",
  appType: "python" as const,
  command: '["gunicorn","app:app","--bind","0.0.0.0:8000"]',
  port: 8000,
  readiness: "/",
  env: [] as { key: string; value: string }[],
};
const status = (
  extra: Partial<DeploymentStatusResponse> = {},
): DeploymentStatusResponse => ({
  deployment_id: "deploy-a",
  status: "running",
  stop_requested: false,
  public_url: "https://api.example.com/apps/deploy-a/",
  created_at: pool.created_at,
  updated_at: pool.created_at,
  replicas: [],
  ...extra,
});

beforeEach(() => {
  vi.stubGlobal("window", new EventTarget());
  vi.stubGlobal("sessionStorage", new Storage());
  vi.stubGlobal("localStorage", new Storage());
  clearPoolCodes();
  useTelemetryStore.getState().clearHistory();
  useAuthStore.setState({
    isAuthenticated: false,
    token: "",
    preview: false,
    hydrated: true,
  });
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("operator session and API boundary", () => {
  it("does not send an unauthorized mutation", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    await expect(apiClient("/api/boxes", { method: "POST" })).rejects.toThrow(
      "operator session",
    );
    expect(fetch).not.toHaveBeenCalled();
  });
  it("rejects external endpoints before attaching credentials", async () => {
    setAuthToken("fixture-token");
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    await expect(apiClient("https://attacker.example/collect")).rejects.toThrow(
      "API path",
    );
    expect(fetch).not.toHaveBeenCalled();
  });
  it("rejects bad login instead of creating a fake authenticated profile", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(json({ detail: "Unauthorized" }, 401)),
    );
    await expect(
      useAuthStore.getState().login("bad-token", "Operator"),
    ).rejects.toThrow();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(getAuthToken()).toBe("");
  });
  it("verifies the protected endpoint before saving a tab session", async () => {
    const fetch = vi.fn().mockResolvedValue(json([]));
    vi.stubGlobal("fetch", fetch);
    await useAuthStore.getState().login("fixture-token", "Anand");
    expect(fetch.mock.calls[0][0]).toBe("/api/control/api/pools");
    expect(fetch.mock.calls[0][1].headers.get("Authorization")).toBe(
      "Bearer fixture-token",
    );
    expect(getAuthToken()).toBe("fixture-token");
    expect(useAuthStore.getState().user.name).toBe("Anand");
    expect(localStorage.getItem("Lattice_auth_token")).toBeNull();
  });
  it("formats FastAPI validation details as readable text", async () => {
    setAuthToken("fixture-token");
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          json(
            { detail: [{ loc: ["body", "pool_id"], type: "uuid_parsing" }] },
            422,
          ),
        ),
    );
    await expect(apiClient("/api/boxes")).rejects.toThrow(
      "pool_id: uuid_parsing",
    );
  });
  it("accepts the backend's empty successful deletion response", async () => {
    setAuthToken("fixture-token");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 204 })),
    );
    await expect(
      apiClient("/api/boxes/box-a", { method: "DELETE" }),
    ).resolves.toBeUndefined();
  });
  it("clears operator credentials on explicit logout", () => {
    setAuthToken("fixture-token");
    useAuthStore.getState().logout();
    expect(getAuthToken()).toBe("");
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });
});

describe("real pool and membership contracts", () => {
  beforeEach(() => setAuthToken("fixture-token"));
  it("uses the backend creation payload and returned code", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(json({ ...pool, pool_code: "LTC-REAL-CODE" }, 201));
    vi.stubGlobal("fetch", fetch);
    const result = await createPool({
      name: "development",
      expires_hours: 24,
      max_joins: 10,
    });
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({
      name: "development",
      expires_hours: 24,
      max_joins: 10,
    });
    expect(result.id).toBe(pool.pool_id);
    expect(result.joinCode).toBe("LTC-REAL-CODE");
  });
  it("never fabricates a join code for a previously existing pool", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(json([pool]))
        .mockResolvedValueOnce(
          json({ ...pool, workers: [worker()], deployments: [] }),
        ),
    );
    const result = await getPool(pool.pool_id);
    expect(result.joinCode).toBeNull();
    expect(result.workerCount).toBe(1);
  });
  it("does not convert server failure into a default or fake successful pool", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(json({ detail: "Database unavailable" }, 503)),
    );
    await expect(listPools()).rejects.toThrow("Database unavailable");
  });
  it("invalidates a cached code when another operator rotates the metadata", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(json({ ...pool, pool_code: "LTC-OLD" }))
      .mockResolvedValueOnce(json([pool]))
      .mockResolvedValueOnce(
        json({
          ...pool,
          join_code_expires_at: "2099-02-01T00:00:00Z",
          workers: [],
          deployments: [],
        }),
      );
    vi.stubGlobal("fetch", fetch);
    await createPool({ name: pool.name });
    expect((await getPool(pool.pool_id)).joinCode).toBeNull();
  });
  it("rotates only on the explicit rotate-code operation", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(json({ ...pool, pool_code: "LTC-NEW" }));
    vi.stubGlobal("fetch", fetch);
    expect((await rotatePoolCode(pool.pool_id)).joinCode).toBe("LTC-NEW");
    expect(fetch.mock.calls[0][0]).toContain("/api/pools/pool-a/rotate-code");
    expect(fetch.mock.calls[0][1].method).toBe("POST");
  });
  it("counts only members with both live channels and online admission", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(json([pool]))
        .mockResolvedValueOnce(
          json({
            ...pool,
            workers: [
              worker("a"),
              worker("b", { application_relay_connected: false }),
              worker("c", { status: "offline" }),
            ],
            deployments: [],
          }),
        ),
    );
    const result = await getPool(pool.pool_id);
    expect(result.workers).toHaveLength(3);
    expect(result.workerCount).toBe(1);
  });
  it("does not show Boxes from another pool", () => {
    expect(
      boxesForPool(
        [box(["a"]), { ...box(["foreign"]), box_id: "foreign" }],
        [worker("a")],
      ),
    ).toEqual([box(["a"])]);
  });
  it("requires full simultaneous per-worker capacity", () => {
    expect(
      fittingWorkers(
        [
          worker("a", { available_ram_gb: 0.25 }),
          worker("b", { available_cpu_cores: 0.1 }),
        ],
        { cpu: 0.5, ram: 0.5, storage: 1 },
      ),
    ).toEqual([]);
  });
  it("uses PowerShell executable and isolated pool state for Windows", () => {
    const command = joinCommand("cloud", null, "windows");
    expect(command).toContain(
      '& "$env:LOCALAPPDATA\\Lattice\\venv\\Scripts\\lattice.exe"',
    );
    expect(command).toContain(
      '--state-dir "$env:USERPROFILE\\.lattice\\pools\\cloud"',
    );
    expect(command).not.toContain("--pool-code");
    expect(joinCommand("other", null, "windows")).not.toContain("pools\\cloud");
  });
  it("rejects unsafe pool/code text before generating shell commands", () => {
    expect(() => joinCommand("cloud;echo bad")).toThrow();
    expect(() => joinCommand("cloud", "code;echo bad")).toThrow();
  });
  it("generates the implemented CLI syntax with a prompted code by default", () => {
    expect(joinCommand("development")).toContain(
      '"$HOME/lattice-venv/bin/lattice" connect --server http://127.0.0.1:8000 --pool-name development --state-dir "$HOME/.lattice/pools/development"',
    );
    expect(joinCommand("development", "LTC-REAL")).toContain(
      "--pool-code LTC-REAL",
    );
  });
});

describe("deployment payload and readiness", () => {
  it("preserves quoted JSON arguments without whitespace splitting", () => {
    const result = buildDeploymentRequest({
      ...plan,
      command: '["python","-c","print(\\"hello world\\")"]',
    });
    expect(result.application_config.start_command).toEqual([
      "python",
      "-c",
      'print("hello world")',
    ]);
  });
  it.each(["bad", '"gunicorn"', "[]", '["a",""]'])(
    "rejects malformed command %s before submission",
    (command) => {
      expect(() => buildDeploymentRequest({ ...plan, command })).toThrow();
    },
  );
  it("rejects duplicate environment keys", () => {
    expect(() =>
      buildDeploymentRequest({
        ...plan,
        env: [
          { key: "PORT", value: "1" },
          { key: "PORT", value: "2" },
        ],
      }),
    ).toThrow("unique");
  });
  it.each([0, 70000, NaN, 1.5])("rejects invalid port %s", (port) =>
    expect(() => buildDeploymentRequest({ ...plan, port })).toThrow("Port"),
  );
  it.each(["//other.example/health", "http://other.example/", "bad"])(
    "rejects unsafe readiness path %s",
    (readiness) =>
      expect(() => buildDeploymentRequest({ ...plan, readiness })).toThrow(
        "Readiness",
      ),
  );
  it("only exposes the actual URL of a ready, unstopped deployment", () => {
    expect(readyPublicUrl(status())).toBe(status().public_url);
    expect(readyPublicUrl(status({ status: "building" }))).toBeNull();
    expect(readyPublicUrl(status({ stop_requested: true }))).toBeNull();
    expect(readyPublicUrl(status({ public_url: null }))).toBeNull();
    expect(
      readyPublicUrl(status({ public_url: "javascript:alert(1)" })),
    ).toBeNull();
  });
});

describe("truthful repository, project and telemetry views", () => {
  it.each([
    "https://evil.example/github.com/a/b",
    "https://github.com/a/b/tree/main",
    "https://user:secret@github.com/a/b",
  ])("rejects misleading repository URL %s", (url) =>
    expect(parseGitHubUrl(url)).toBeNull(),
  );
  it("never returns made-up commits when GitHub rejects inspection", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(json({ message: "rate limited" }, 403)),
    );
    await expect(inspectRepository(plan.repoUrl)).rejects.toThrow(
      "GitHub inspection unavailable",
    );
  });
  it("never promotes a failed deployment to production", () => {
    const d: Deployment = {
      deployment_id: "a",
      box_id: "box-a",
      repository_url: plan.repoUrl,
      branch: "main",
      application_type: "python",
      image_reference: "pending",
      status: "failed",
      created_at: pool.created_at,
    };
    expect(groupProjects([d])[0].productionDeployment).toBeNull();
  });
  it("keeps missing metrics null and deduplicates the same heartbeat", () => {
    const store = useTelemetryStore.getState();
    store.ingestWorkerSnapshots([worker()]);
    store.ingestWorkerSnapshots([worker()]);
    const points = useTelemetryStore.getState().history.a;
    expect(points).toHaveLength(1);
    expect(points[0]).toMatchObject({
      timestamp: worker().last_heartbeat,
      cpuUtilization: null,
      memoryUtilization: null,
      batteryPercentage: null,
      healthScore: null,
    });
  });
  it("does not fabricate new historical readings for offline workers", () => {
    useTelemetryStore
      .getState()
      .ingestWorkerSnapshots([worker("a", { status: "offline" })]);
    expect(useTelemetryStore.getState().history.a).toBeUndefined();
  });
});
