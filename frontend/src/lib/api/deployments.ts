import { apiClient } from "./client";
import {
  Deployment,
  DeploymentCreateRequest,
  DeploymentLogsResponse,
  DeploymentStatusResponse,
} from "@/types/contracts";

export async function listDeployments(): Promise<Deployment[]> {
  return apiClient<Deployment[]>("/api/deployments");
}

export async function getDeployment(deploymentId: string): Promise<Deployment> {
  return apiClient<Deployment>(`/api/deployments/${deploymentId}`);
}

export async function createDeployment(
  payload: DeploymentCreateRequest,
): Promise<Deployment> {
  return apiClient<Deployment>("/api/deployments", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getDeploymentLogs(
  deploymentId: string,
  limit: number = 500,
): Promise<DeploymentLogsResponse> {
  return apiClient<DeploymentLogsResponse>(
    `/api/deployments/${deploymentId}/logs?limit=${limit}`,
  );
}

export async function getDeploymentStatus(
  deploymentId: string,
): Promise<DeploymentStatusResponse> {
  return apiClient<DeploymentStatusResponse>(
    `/api/deployments/${deploymentId}/status`,
  );
}

export async function stopDeployment(
  deploymentId: string,
): Promise<{ deployment_id: string; status: string }> {
  return apiClient(`/api/deployments/${deploymentId}/stop`, {
    method: "POST",
  });
}

export async function redeployDeployment(
  deploymentId: string,
): Promise<Deployment> {
  return apiClient<Deployment>(`/api/deployments/${deploymentId}/redeploy`, {
    method: "POST",
  });
}
