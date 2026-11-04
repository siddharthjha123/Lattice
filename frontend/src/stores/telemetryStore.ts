import { workerMetrics } from "@/lib/utils/metrics";
import { create } from "zustand";
import { MetricTimeRange, MetricSnapshot } from "@/types/telemetry";
import { WorkerSnapshot } from "@/types/contracts";

interface TelemetryState {
  // History indexed by workerId: array of snapshots over time
  history: Record<string, MetricSnapshot[]>;
  timeRange: MetricTimeRange;
  hoveredWorkerId: string | null;
  selectedWorkerId: string | null;
  activeMetricType: "cpu" | "memory" | "battery" | "health";
  setTimeRange: (range: MetricTimeRange) => void;
  setHoveredWorkerId: (id: string | null) => void;
  setSelectedWorkerId: (id: string | null) => void;
  setActiveMetricType: (type: "cpu" | "memory" | "battery" | "health") => void;
  ingestWorkerSnapshots: (workers: WorkerSnapshot[]) => void;
  clearHistory: () => void;
}

export const useTelemetryStore = create<TelemetryState>((set) => ({
  history: {},
  timeRange: "5m",
  hoveredWorkerId: null,
  selectedWorkerId: null,
  activeMetricType: "cpu",

  setTimeRange: (range) => set({ timeRange: range }),
  setHoveredWorkerId: (id) => set({ hoveredWorkerId: id }),
  setSelectedWorkerId: (id) => set({ selectedWorkerId: id }),
  setActiveMetricType: (type) => set({ activeMetricType: type }),

  ingestWorkerSnapshots: (workers) => {
    set((state) => {
      const nextHistory = { ...state.history };

      for (const worker of workers) {
        const id = worker.worker_id;
        const currentList = nextHistory[id] ? [...nextHistory[id]] : [];

        if (
          worker.status !== "online" ||
          !Number.isFinite(Date.parse(worker.last_heartbeat)) ||
          currentList.at(-1)?.timestamp === worker.last_heartbeat
        )
          continue;
        const metrics = workerMetrics(worker);
        const point: MetricSnapshot = {
          timestamp: worker.last_heartbeat,
          workerId: id,
          workerName: worker.hostname || id,
          cpuUtilization: metrics.cpu,
          memoryUtilization: metrics.memory,
          batteryPercentage: metrics.battery,
          healthScore: metrics.health,
          availableCpuCores: worker.available_cpu_cores,
          availableRamGb: worker.available_ram_gb,
          availableStorageGb: worker.available_storage_gb,
          activeContainers: worker.active_container_count,
        };

        // Keep at most 1200 authenticated readings per worker in this tab.
        if (currentList.length >= 1200) {
          currentList.shift();
        }
        currentList.push(point);
        nextHistory[id] = currentList;
      }

      return { history: nextHistory };
    });
  },

  clearHistory: () => set({ history: {} }),
}));
