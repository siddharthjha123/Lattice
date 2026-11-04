import { WorkerSnapshot, DeploymentStatus } from "./contracts";
export interface PoolRecord {
  pool_id: string;
  name: string;
  join_code_expires_at: string;
  joins_used: number;
  max_joins: number;
  created_at: string;
  pool_code?: string;
}
export interface PoolStatus extends PoolRecord {
  workers: WorkerSnapshot[];
  deployments: {
    deployment_id: string;
    status: DeploymentStatus;
    public_url: string | null;
    failure_message: string | null;
  }[];
}
export interface ConnectionPool {
  id: string;
  name: string;
  joinCode: string | null;
  workerCount: number;
  status: "waiting" | "connected";
  createdAt: string;
  expiresAt: string;
  joinsUsed: number;
  maxJoins: number;
  workers: WorkerSnapshot[];
}
export interface PoolCreationPayload {
  name: string;
  expires_hours?: number;
  max_joins?: number;
}
