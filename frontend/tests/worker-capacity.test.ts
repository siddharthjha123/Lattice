import { beforeEach, expect, it } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { WorkerResources } from "../src/components/workers/WorkerResources";
import { useTelemetryStore } from "../src/stores/telemetryStore";
import {
  buildChartRows,
  formatChartValue,
} from "../src/lib/utils/chartMetrics";
import type { WorkerSnapshot } from "../src/types/contracts";

const now = Date.parse("2026-11-01T07:30:00Z");
const worker: WorkerSnapshot = {
  worker_id: "bala",
  hostname: "Bala",
  status: "online",
  architecture: "aarch64",
  cpu_cores: 10,
  total_ram_gb: 7.653,
  total_storage_gb: 228.2,
  available_cpu_cores: 0,
  available_ram_gb: 0,
  available_storage_gb: 6.25,
  active_container_count: 0,
  max_containers: 4,
  supported_runtimes: ["python"],
  last_heartbeat: new Date(now).toISOString(),
};
beforeEach(() => useTelemetryStore.getState().clearHistory());
it("shows Docker specs even when an online worker has zero allocatable CPU and RAM", () => {
  const html = renderToStaticMarkup(
    React.createElement(WorkerResources, { worker }),
  );
  expect(html).toContain("10 cores");
  expect(html).toContain("7.65 GiB");
  expect(html).toContain("0.00 GiB");
  expect(html).toContain("cannot currently accept a deployment");
});
it("retains last specs while hiding offline availability", () => {
  const html = renderToStaticMarkup(
    React.createElement(WorkerResources, {
      worker: { ...worker, status: "offline", available_ram_gb: 2 },
    }),
  );
  expect(html).toContain("10 cores");
  expect(html).toContain("Unavailable");
  expect(html).not.toContain("2.00 GiB");
});
it("plots genuine zero capacity and counts without inventing utilization", () => {
  useTelemetryStore.getState().ingestWorkerSnapshots([worker]);
  const history = useTelemetryStore.getState().history;
  for (const metric of ["availableCpu", "availableRam", "containers"] as const)
    expect(buildChartRows(["bala"], history, metric, "1m", now)[0].bala).toBe(
      0,
    );
  expect(
    buildChartRows(["bala"], history, "availableStorage", "1m", now)[0].bala,
  ).toBe(6.25);
  expect(
    buildChartRows(["bala"], history, "cpu", "1m", now)[0].bala,
  ).toBeNull();
  expect(formatChartValue(0.5, "GiB")).toBe("0.5 GiB");
});
it("does not align one worker's missing observation with another worker's reading", () => {
  useTelemetryStore.getState().ingestWorkerSnapshots([
    worker,
    {
      ...worker,
      worker_id: "anand",
      last_heartbeat: new Date(now - 5_000).toISOString(),
      available_storage_gb: 150.5,
    },
  ]);
  const history = useTelemetryStore.getState().history;
  const rows = buildChartRows(
    ["bala", "anand"],
    history,
    "availableStorage",
    "1m",
    now,
  );
  expect(rows[0].anand).toBe(150.5);
  expect(rows[0].bala).toBeNull();
  expect(rows[1].bala).toBe(6.25);
  expect(rows[1].anand).toBeNull();
  expect(
    buildChartRows(["bala"], history, "availableCpu", "1m", now + 61_000),
  ).toEqual([]);
});
