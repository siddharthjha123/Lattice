import { apiClient } from "./client";
import { WorkerSnapshot } from "@/types/contracts";

export interface HealthCheckResponse {
  status: string;
  database: string;
  service: string;
  connected_workers?: number;
  timestamp: string;
}

export async function fetchHealth(): Promise<HealthCheckResponse> {
  return apiClient<HealthCheckResponse>("/health");
}

export async function listWorkers(): Promise<WorkerSnapshot[]> {
  return apiClient<WorkerSnapshot[]>("/api/workers");
}

export async function getWorker(workerId: string): Promise<WorkerSnapshot> {
  return apiClient<WorkerSnapshot>(
    `/api/workers/${encodeURIComponent(workerId)}`,
  );
}

export async function disconnectWorker(workerId: string): Promise<{
  worker_id: string;
  status: string;
  message: string;
}> {
  return apiClient(`/api/workers/${encodeURIComponent(workerId)}/disconnect`, {
    method: "POST",
  });
}

export async function registerWorker(data: {
  worker_id: string;
  hostname: string;
  cpu_cores: number;
  total_ram_gb: number;
  total_storage_gb: number;
  max_containers: number;
  architecture: string;
  supported_runtimes: string[];
  address?: string;
}): Promise<{
  worker_id: string;
  token: string;
  status: string;
  message: string;
}> {
  return apiClient("/api/workers/register", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function deleteWorker(workerId: string): Promise<void> {
  await apiClient<void>(`/api/workers/${encodeURIComponent(workerId)}`, {
    method: "DELETE",
  });
}
