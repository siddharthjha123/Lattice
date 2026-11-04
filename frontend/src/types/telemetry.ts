export type MetricTimeRange = "1m" | "5m" | "15m" | "1h";

export interface MetricSnapshot {
  timestamp: string;
  workerId: string;
  workerName: string;
  cpuUtilization: number | null;
  memoryUtilization: number | null;
  batteryPercentage: number | null;
  healthScore: number | null;
  availableCpuCores: number;
  availableRamGb: number;
  availableStorageGb: number;
  activeContainers: number;
}

export interface WorkerTimeSeriesData {
  timestamp: string;
  [workerKey: string]: number | string | null;
}

export interface AggregatePoolMetrics {
  connectedWorkers: number;
  totalCpuCapacityCores: number;
  totalCpuUtilizationPercent: number;
  availableCpuCapacityCores: number;
  totalMemoryCapacityGb: number;
  totalMemoryUtilizationPercent: number;
  availableMemoryGb: number;
  averageBatteryPercentage: number | null;
  overallPoolHealthPercent: number;
}
