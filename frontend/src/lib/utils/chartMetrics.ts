import type { MetricSnapshot, MetricTimeRange } from "@/types/telemetry";
export const chartMetrics = {
  cpu: { title: "CPU utilization", unit: "%", field: "cpuUtilization" },
  memory: {
    title: "Memory utilization",
    unit: "%",
    field: "memoryUtilization",
  },
  battery: { title: "Battery level", unit: "%", field: "batteryPercentage" },
  health: { title: "Health score", unit: "%", field: "healthScore" },
  availableCpu: {
    title: "Available CPU history",
    unit: "cores",
    field: "availableCpuCores",
  },
  availableRam: {
    title: "Available RAM history",
    unit: "GiB",
    field: "availableRamGb",
  },
  availableStorage: {
    title: "Available storage history",
    unit: "GiB",
    field: "availableStorageGb",
  },
  containers: {
    title: "Active containers history",
    unit: "containers",
    field: "activeContainers",
  },
} as const;
export type ChartMetric = keyof typeof chartMetrics;
export const capacityChartMetrics = [
  "availableCpu",
  "availableRam",
  "availableStorage",
  "containers",
] as const;
export const formatChartValue = (value: number, unit: string) =>
  `${Number(value.toFixed(2))}${unit === "%" ? "" : " "}${unit}`;
export function buildChartRows(
  ids: string[],
  history: Record<string, MetricSnapshot[]>,
  metric: ChartMetric,
  range: MetricTimeRange,
  now = Date.now(),
) {
  const windowMs = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
  }[range];
  const points = new Map<string, Map<string, MetricSnapshot>>();
  const timestamps = new Set<string>();
  for (const id of ids) {
    const index = new Map<string, MetricSnapshot>();
    for (const point of history[id] || []) {
      const time = Date.parse(point.timestamp);
      if (!Number.isFinite(time) || time > now || now - time > windowMs)
        continue;
      index.set(point.timestamp, point);
      timestamps.add(point.timestamp);
    }
    points.set(id, index);
  }
  return [...timestamps]
    .sort((a, b) => Date.parse(a) - Date.parse(b))
    .map((timestamp) => {
      const row: Record<string, string | number | null> = {
        timestamp,
        timeLabel: new Date(timestamp).toLocaleTimeString("en-US", {
          hour12: false,
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        }),
      };
      for (const id of ids) {
        const value = points.get(id)?.get(timestamp)?.[
          chartMetrics[metric].field
        ];
        row[id] =
          typeof value === "number" && Number.isFinite(value) && value >= 0
            ? value
            : null;
      }
      return row;
    });
}
