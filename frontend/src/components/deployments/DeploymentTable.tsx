"use client";

import React, { useState, useMemo } from "react";
import { Deployment } from "@/types/contracts";
import { DeploymentStatusBadge } from "./DeploymentStatusBadge";
import { formatRelativeTime, truncateHash } from "@/lib/utils/formatters";
import {
  Search,
  Filter,
  Eye,
  RotateCcw,
  Square,
  ExternalLink,
  GitBranch,
  Github,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import Link from "next/link";
import {
  useStopDeployment,
  useRedeployDeployment,
} from "@/hooks/useDeployments";

interface DeploymentTableProps {
  deployments: Deployment[];
  className?: string;
}

export function DeploymentTable({
  deployments,
  className,
}: DeploymentTableProps) {
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");

  const stopMutation = useStopDeployment();
  const redeployMutation = useRedeployDeployment();

  const filteredDeployments = useMemo(() => {
    return deployments.filter((d) => {
      if (statusFilter !== "all") {
        if (statusFilter === "ready" && d.status !== "running") return false;
        if (
          statusFilter === "building" &&
          d.status !== "building" &&
          d.status !== "queued"
        )
          return false;
        if (statusFilter === "failed" && d.status !== "failed") return false;
        if (statusFilter === "stopped" && d.status !== "stopped") return false;
      }

      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return (
          d.deployment_id.toLowerCase().includes(q) ||
          d.repository_url.toLowerCase().includes(q) ||
          d.branch.toLowerCase().includes(q) ||
          d.box_id.toLowerCase().includes(q)
        );
      }

      return true;
    });
  }, [deployments, statusFilter, searchQuery]);

  return (
    <div className={`space-y-4 ${className || ""}`}>
      {/* Search and Filters Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Status Filters */}
        <div className="flex items-center space-x-1 rounded-md border border-surface-border bg-surface/40 p-1 text-xs">
          {[
            { id: "all", label: "All" },
            { id: "ready", label: "Ready" },
            { id: "building", label: "Building" },
            { id: "failed", label: "Failed" },
            { id: "stopped", label: "Stopped" },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setStatusFilter(tab.id)}
              className={`px-3 py-1 rounded font-medium transition-colors ${
                statusFilter === tab.id
                  ? "bg-surface-active text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Search Input */}
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-zinc-500" />
          <input
            type="text"
            placeholder="Search deployments..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="h-8 w-48 sm:w-64 rounded-md border border-surface-border bg-input pl-8 pr-3 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-accent"
          />
        </div>
      </div>

      {/* Table Container */}
      <div className="rounded-lg border border-surface-border bg-card overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-surface-border bg-surface/50 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                <th className="py-3 px-4">Deployment</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4">Repository</th>
                <th className="py-3 px-4">Branch</th>
                <th className="py-3 px-4">Assigned Box</th>
                <th className="py-3 px-4">Created</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border/50">
              {filteredDeployments.length === 0 ? (
                <tr>
                  <td
                    colSpan={7}
                    className="py-12 text-center text-xs text-muted-foreground font-sans"
                  >
                    No deployments match the current filter.
                  </td>
                </tr>
              ) : (
                filteredDeployments.map((d) => {
                  const repoName = d.repository_url.split("/").pop() || "repo";

                  return (
                    <tr
                      key={d.deployment_id}
                      className="hover:bg-surface-hover/50 transition-colors group"
                    >
                      {/* Deployment ID & link */}
                      <td className="py-3 px-4 font-mono font-medium text-foreground">
                        <Link
                          href={`/deployments/${d.deployment_id}`}
                          className="hover:text-accent hover:underline flex items-center gap-1.5"
                        >
                          <span>{truncateHash(d.deployment_id, 8)}</span>
                          <ExternalLink className="w-3 h-3 text-zinc-500 opacity-0 group-hover:opacity-100 transition-opacity" />
                        </Link>
                      </td>

                      {/* Status */}
                      <td className="py-3 px-4">
                        <DeploymentStatusBadge status={d.status} />
                      </td>

                      {/* Repository */}
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-1.5 text-zinc-300 font-medium">
                          <Github className="w-3.5 h-3.5 text-zinc-500" />
                          <span className="truncate max-w-[140px]">
                            {repoName}
                          </span>
                        </div>
                      </td>

                      {/* Branch */}
                      <td className="py-3 px-4 font-mono text-zinc-400">
                        <div className="flex items-center gap-1">
                          <GitBranch className="w-3 h-3 text-zinc-500" />
                          <span>{d.branch}</span>
                        </div>
                      </td>

                      {/* Box */}
                      <td className="py-3 px-4 font-mono text-zinc-400">
                        {truncateHash(d.box_id, 8)}
                      </td>

                      {/* Created */}
                      <td className="py-3 px-4 text-zinc-500">
                        {formatRelativeTime(d.created_at)}
                      </td>

                      {/* Actions */}
                      <td className="py-3 px-4 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <Link href={`/deployments/${d.deployment_id}`}>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-7 px-2 text-[11px] gap-1 text-zinc-400 hover:text-foreground"
                            >
                              <Eye className="w-3 h-3" />
                              <span>View</span>
                            </Button>
                          </Link>

                          {d.status === "running" && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() =>
                                stopMutation.mutate(d.deployment_id)
                              }
                              isLoading={stopMutation.isPending}
                              className="h-7 px-2 text-[11px] gap-1 text-zinc-400 hover:text-rose-400"
                              title="Stop deployment"
                            >
                              <Square className="w-3 h-3" />
                              <span>Stop</span>
                            </Button>
                          )}

                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              redeployMutation.mutate(d.deployment_id)
                            }
                            isLoading={redeployMutation.isPending}
                            className="h-7 px-2 text-[11px] gap-1 text-zinc-400 hover:text-primary"
                            title="Redeploy version"
                          >
                            <RotateCcw className="w-3 h-3" />
                            <span>Redeploy</span>
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
