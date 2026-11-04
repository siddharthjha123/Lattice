"use client";

import React from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useOperatorSession } from "@/stores/authStore";
import { ErrorState } from "@/components/ui/ErrorState";
import { listProjects, getProject } from "@/lib/api/projectsAdapter";
import { DeploymentTable } from "@/components/deployments/DeploymentTable";
import { DeploymentStatusBadge } from "@/components/deployments/DeploymentStatusBadge";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import {
  FolderGit2,
  Github,
  GitBranch,
  Rocket,
  ExternalLink,
  Box as BoxIcon,
  Clock,
  Layers,
  ArrowRight,
} from "lucide-react";
import Link from "next/link";
import {
  formatDate,
  formatRelativeTime,
  truncateHash,
} from "@/lib/utils/formatters";

export default function ProjectDetailPage() {
  const session = useOperatorSession();
  const params = useParams();
  const projectId = (params?.projectId as string) || "overview";
  const isOverview = projectId === "overview";

  const {
    data: allProjects = [],
    isLoading: isLoadingAll,
    error: allError,
    refetch: refetchAll,
  } = useQuery({
    queryKey: ["projects"],
    queryFn: listProjects,
    enabled: session,
    refetchInterval: 5000,
  });

  const {
    data: projectDetails,
    isLoading: isLoadingSingle,
    error: singleError,
    refetch: refetchSingle,
  } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => getProject(projectId),
    enabled: session && !isOverview,
    refetchInterval: 5000,
  });

  if (allError || singleError)
    return (
      <ErrorState
        message={(allError || singleError)?.message}
        onRetry={() => {
          refetchAll();
          refetchSingle();
        }}
      />
    );
  if (isOverview) {
    return (
      <>
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-surface-border/60 pb-6">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground">
              Projects
            </h1>
            <p className="text-xs sm:text-sm text-muted-foreground mt-1">
              Repositories connected to Lattice with automated container build
              and mesh placement.
            </p>
          </div>

          <Link href="/deployments/new">
            <Button variant="primary" size="sm" className="gap-1.5 shadow-sm">
              <Rocket className="w-3.5 h-3.5" />
              <span>Deploy New Project</span>
            </Button>
          </Link>
        </div>

        {/* Projects Grid */}
        <div className="space-y-4">
          {isLoadingAll ? (
            <div className="py-16 text-center text-xs text-muted-foreground">
              Loading projects...
            </div>
          ) : allProjects.length === 0 ? (
            <div className="rounded-xl border border-dashed border-surface-border p-12 text-center bg-surface/20 space-y-4 max-w-md mx-auto">
              <div className="w-12 h-12 rounded-full bg-surface border border-surface-border mx-auto flex items-center justify-center text-zinc-500">
                <FolderGit2 className="w-6 h-6 text-zinc-400" />
              </div>
              <div>
                <h4 className="text-sm font-semibold text-foreground">
                  No Projects Yet
                </h4>
                <p className="text-xs text-muted-foreground mt-1">
                  Connect a GitHub repository to automatically provision build
                  logs and deployment history.
                </p>
              </div>
              <Link href="/deployments/new">
                <Button variant="primary" size="sm">
                  Create First Deployment
                </Button>
              </Link>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {allProjects.map((project) => {
                const prod = project.productionDeployment;
                return (
                  <Card
                    key={project.projectId}
                    className="p-5 border border-card-border bg-card hover:border-zinc-700 transition-all flex flex-col justify-between space-y-4 shadow-sm group"
                  >
                    <div>
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-2.5">
                          <div className="p-2 rounded-lg bg-surface border border-surface-border text-primary group-hover:border-primary/40 transition-colors">
                            <FolderGit2 className="w-4 h-4" />
                          </div>
                          <div>
                            <h4 className="text-base font-semibold text-foreground tracking-tight">
                              {project.name}
                            </h4>
                            <div className="text-xs font-mono text-zinc-500 mt-0.5 truncate max-w-[160px]">
                              {project.owner}
                            </div>
                          </div>
                        </div>

                        {prod && <DeploymentStatusBadge status={prod.status} />}
                      </div>

                      <div className="mt-4 p-2.5 rounded-lg bg-surface/40 border border-surface-border/50 text-xs space-y-1.5 font-mono">
                        <div className="flex items-center justify-between text-zinc-400">
                          <span className="flex items-center gap-1">
                            <Github className="w-3 h-3 text-zinc-500" />
                            <span className="truncate max-w-[180px]">
                              {project.repositoryUrl.replace(
                                "https://github.com/",
                                "",
                              )}
                            </span>
                          </span>
                        </div>
                        {prod && (
                          <div className="flex items-center justify-between text-[11px] text-zinc-500 pt-1 border-t border-surface-border/40">
                            <span>
                              Prod: {truncateHash(prod.deployment_id, 7)}
                            </span>
                            <span>{formatRelativeTime(prod.created_at)}</span>
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center justify-between pt-2 border-t border-surface-border/50 text-xs">
                      <span className="text-[11px] text-zinc-500">
                        {project.deploymentCount}{" "}
                        {project.deploymentCount === 1
                          ? "deployment"
                          : "deployments"}
                      </span>
                      <Link
                        href={`/projects/${project.projectId}`}
                        className="text-primary hover:underline flex items-center gap-1 font-medium"
                      >
                        <span>View Project</span>
                        <ArrowRight className="w-3 h-3" />
                      </Link>
                    </div>
                  </Card>
                );
              })}
            </div>
          )}
        </div>
      </>
    );
  }

  // Single Project View
  const project = projectDetails?.project;
  const deployments = projectDetails?.deployments || [];
  const prod = project?.productionDeployment;

  return (
    <>
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-surface-border/60 pb-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Link
              href="/projects/overview"
              className="text-xs text-muted-foreground hover:text-foreground font-medium"
            >
              ← All Projects
            </Link>
          </div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground">
              {project?.name || projectId}
            </h1>
            {prod && <DeploymentStatusBadge status={prod.status} />}
          </div>
          <p className="text-xs text-muted-foreground mt-1 font-mono">
            {project?.repositoryUrl || "Repository"}
          </p>
        </div>

        <Link href={`/deployments/new`}>
          <Button variant="primary" size="sm" className="gap-1.5 shadow-sm">
            <Rocket className="w-3.5 h-3.5" />
            <span>New Deployment</span>
          </Button>
        </Link>
      </div>

      {/* Production Deployment Card */}
      {prod && (
        <Card className="p-6 border border-card-border bg-card space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-surface-border/60 pb-4">
            <div className="flex items-center gap-2.5">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Production Deployment
              </span>
              <DeploymentStatusBadge status={prod.status} />
            </div>

            {prod.public_url ? (
              <a href={prod.public_url} target="_blank" rel="noreferrer">
                <Button
                  variant="primary"
                  size="sm"
                  className="gap-1.5 h-7 text-xs"
                >
                  <span>Visit Domain</span>
                  <ExternalLink className="w-3 h-3" />
                </Button>
              </a>
            ) : (
              <Link href={`/deployments/${prod.deployment_id}`}>
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1.5 h-7 text-xs"
                >
                  <span>View Details</span>
                  <ExternalLink className="w-3 h-3" />
                </Button>
              </Link>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 text-xs">
            <div>
              <span className="text-zinc-500 block">Deployment ID</span>
              <span className="font-mono text-zinc-200">
                {truncateHash(prod.deployment_id, 10)}
              </span>
            </div>
            <div>
              <span className="text-zinc-500 block">Branch</span>
              <span className="font-mono text-zinc-200">{prod.branch}</span>
            </div>
            <div>
              <span className="text-zinc-500 block">Assigned Box</span>
              <span className="font-mono text-zinc-200">
                {truncateHash(prod.box_id, 8)}
              </span>
            </div>
            <div>
              <span className="text-zinc-500 block">Created</span>
              <span className="text-zinc-200">
                {formatRelativeTime(prod.created_at)}
              </span>
            </div>
          </div>
        </Card>
      )}

      {/* Deployment History Table */}
      <div className="space-y-4 pt-2">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Deployment History
        </h3>
        <DeploymentTable deployments={deployments} />
      </div>
    </>
  );
}
