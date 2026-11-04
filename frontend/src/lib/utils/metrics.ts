import { WorkerSnapshot } from "@/types/contracts";
export const percent = (n: unknown): number | null =>
  typeof n === "number" && Number.isFinite(n) && n >= 0 && n <= 100 ? n : null;
export function workerMetrics(w?: WorkerSnapshot) {
  return {
    cpu: percent(w?.cpu_usage_percent),
    memory: percent(w?.memory_usage_percent),
    battery: percent(w?.battery_percentage),
    health: percent(w?.health_score),
  };
}
