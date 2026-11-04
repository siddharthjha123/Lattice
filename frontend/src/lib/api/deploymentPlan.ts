import {
  ApplicationType,
  DeploymentCreateRequest,
  DeploymentStatusResponse,
} from "@/types/contracts";
import { parseGitHubUrl } from "./repoInspectionAdapter";
export function buildDeploymentRequest(data: {
  repoUrl: string;
  branch: string;
  boxId: string;
  appType: ApplicationType;
  command: string;
  port: number;
  readiness: string;
  env: { key: string; value: string }[];
}): DeploymentCreateRequest {
  if (!parseGitHubUrl(data.repoUrl))
    throw new Error("Enter a plain public HTTPS GitHub repository URL.");
  if (!data.branch.trim() || !data.boxId)
    throw new Error("Select a branch and an available Box.");
  if (!Number.isInteger(data.port) || data.port < 1 || data.port > 65535)
    throw new Error("Port must be an integer between 1 and 65535.");
  if (
    !data.readiness.startsWith("/") ||
    data.readiness.startsWith("//") ||
    /[\r\n]/.test(data.readiness)
  )
    throw new Error(
      "Readiness must be a relative path beginning with a single slash.",
    );
  let start: string[] | undefined;
  if (data.command.trim()) {
    try {
      start = JSON.parse(data.command);
    } catch {
      throw new Error(
        'Startup command must be a JSON argument array, for example ["gunicorn","app:app","--bind","0.0.0.0:8000"].',
      );
    }
    if (
      !Array.isArray(start) ||
      !start.length ||
      start.some((x) => typeof x !== "string" || !x || x.includes("\0"))
    )
      throw new Error("Startup arguments must be nonempty strings.");
  }
  const env: Record<string, string> = {};
  for (const { key, value } of data.env) {
    if (!key.trim()) continue;
    if (
      !/^[A-Za-z_][A-Za-z0-9_]*$/.test(key.trim()) ||
      Object.hasOwn(env, key.trim())
    )
      throw new Error("Environment variable names must be valid and unique.");
    env[key.trim()] = value;
  }
  return {
    repository_url: data.repoUrl.trim(),
    branch: data.branch.trim(),
    box_id: data.boxId,
    application_type: data.appType,
    application_config: {
      start_command: start,
      internal_port: data.port,
      readiness_path: data.readiness,
      environment_variables: env,
    },
  };
}
export function readyPublicUrl(
  status?: DeploymentStatusResponse,
): string | null {
  if (
    status?.status !== "running" ||
    status.stop_requested ||
    !status.public_url
  )
    return null;
  try {
    const u = new URL(status.public_url);
    return ["https:", "http:"].includes(u.protocol) &&
      !u.username &&
      !u.password
      ? status.public_url
      : null;
  } catch {
    return null;
  }
}
