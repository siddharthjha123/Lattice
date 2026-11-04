/** Projects are views of actual deployment history; no project persistence API exists. */
import { Deployment } from "@/types/contracts";
import { Project } from "@/types/project";
import { listDeployments } from "./deployments";
import { parseGitHubUrl } from "./repoInspectionAdapter";
export function groupProjects(deployments: Deployment[]): Project[] {
  const groups = new Map<string, Deployment[]>();
  for (const d of deployments)
    groups.set(d.repository_url, [...(groups.get(d.repository_url) || []), d]);
  return [...groups].map(([url, items]) => {
    const sorted = items.sort(
      (a, b) => Date.parse(b.created_at) - Date.parse(a.created_at),
    );
    const parsed = parseGitHubUrl(url);
    return {
      projectId: parsed
        ? `${parsed.owner}:${parsed.repo}`.toLowerCase()
        : encodeURIComponent(url),
      name: parsed?.repo || url,
      owner: parsed?.owner || "Not reported",
      repositoryUrl: url,
      productionDeployment: sorted.find((d) => d.status === "running") || null,
      latestDeployment: sorted[0],
      deploymentCount: sorted.length,
      createdAt: sorted.at(-1)!.created_at,
    };
  });
}
export async function listProjects() {
  return groupProjects(await listDeployments());
}
export async function getProject(id: string) {
  const all = await listDeployments();
  const project = groupProjects(all).find((p) => p.projectId === id) || null;
  return {
    project,
    deployments: project
      ? all.filter((d) => d.repository_url === project.repositoryUrl)
      : [],
  };
}
