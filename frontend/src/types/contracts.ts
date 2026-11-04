/**
 * Canonical frontend contracts matching the backend Pydantic v2 models.
 * Reference: backend/shared/contracts.py & backend/shared/enums.py
 */

export type WorkerStatus = "online" | "offline" | "unhealthy";
export type BoxStatus = "available" | "deployed" | "degraded" | "failed";
export type ApplicationType = "python" | "node";
export type DeploymentStatus =
  "queued" | "building" | "deploying" | "running" | "failed" | "stopped";
export type ReplicaRole = "primary" | "standby";
export type ReplicaStatus = "pending" | "running" | "unhealthy" | "stopped";
export type ContainerStatus =
  | "created"
  | "running"
  | "paused"
  | "restarting"
  | "removing"
  | "exited"
  | "dead"
  | "unhealthy"
  | "stopped";
export type LogLevel = "debug" | "info" | "warning" | "error" | "critical";

export interface PortBinding {
  internal_port: number;
  host_ip: string;
  host_port: number;
  protocol: "tcp" | "udp";
}

export interface WorkerSnapshot {
  worker_id: string;
  hostname: string;
  status: WorkerStatus;
  cpu_cores: number;
  available_cpu_cores: number;
  total_ram_gb: number;
  available_ram_gb: number;
  total_storage_gb: number;
  available_storage_gb: number;
  active_container_count: number;
  max_containers: number;
  architecture: string;
  supported_runtimes: ApplicationType[];
  last_heartbeat: string;
  address?: string;
  control_connected?: boolean;
  application_relay_connected?: boolean;
  running_container_ids?: string[];
  // Optional metrics: absent fields must remain unavailable.
  cpu_usage_percent?: number | null;
  memory_usage_percent?: number | null;
  battery_percentage?: number | null;
  health_score?: number | null;
}

export interface BoxCreationRequest {
  pool_id?: string | null;
  name: string;
  cpu_limit_cores: number;
  ram_limit_gb: number;
  storage_limit_gb: number;
  eligible_worker_ids: string[];
  failover_enabled?: boolean;
}

export interface Box extends BoxCreationRequest {
  box_id: string;
  primary_worker_id?: string | null;
  standby_worker_id?: string | null;
  status: BoxStatus;
  deployment_id?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface ApplicationConfig {
  start_command?: string[] | null;
  internal_port?: number;
  readiness_path?: string;
  environment_variables?: Record<string, string>;
}

export interface DeploymentCreateRequest {
  repository_url: string;
  branch: string;
  application_type: ApplicationType;
  box_id: string;
  application_config: ApplicationConfig;
}

export interface Deployment {
  deployment_id: string;
  box_id: string;
  repository_url: string;
  branch: string;
  application_type: ApplicationType;
  image_reference: string;
  status: DeploymentStatus;
  public_url?: string | null;
  created_at: string;
}

export interface ReplicaResponse {
  replica_id: string;
  worker_id: string;
  container_id?: string | null;
  role: ReplicaRole;
  status: ReplicaStatus;
  container_status: string;
  health: "not_configured" | "starting" | "healthy" | "unhealthy";
  internal_port: number;
  port_bindings: PortBinding[];
}

export interface DeploymentStatusResponse {
  deployment_id: string;
  status: DeploymentStatus;
  public_url?: string | null;
  stop_requested: boolean;
  failure_message?: string | null;
  created_at: string;
  updated_at: string;
  replicas: ReplicaResponse[];
}

export interface DeploymentLogEntry {
  timestamp: string;
  log_level: LogLevel;
  message: string;
  container_id?: string | null;
}

export interface DeploymentLogsResponse {
  deployment_id: string;
  logs: DeploymentLogEntry[];
}
