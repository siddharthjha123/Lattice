"use client";

import React from "react";
import { RepositoryInspection } from "@/types/repository";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import {
  GitBranch,
  GitCommit as CommitIcon,
  Code2,
  FileCode2,
  CheckCircle2,
  XCircle,
  Clock,
  User,
} from "lucide-react";
import { formatRelativeTime } from "@/lib/utils/formatters";

interface RepositoryInspectionCardProps {
  inspection: RepositoryInspection;
  selectedBranch: string;
  onBranchChange: (branch: string) => void;
  className?: string;
}

export function RepositoryInspectionCard({
  inspection,
  selectedBranch,
  onBranchChange,
  className,
}: RepositoryInspectionCardProps) {
  return (
    <Card
      className={`p-5 border border-surface-border bg-surface/30 space-y-5 ${className || ""}`}
    >
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-surface-border/60 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-surface border border-surface-border flex items-center justify-center text-zinc-300">
            <Code2 className="w-4 h-4 text-primary" />
          </div>
          <div>
            <div className="text-sm font-bold text-foreground">
              {inspection.owner} / {inspection.repoName}
            </div>
            <a
              href={inspection.repositoryUrl}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-muted-foreground hover:text-accent font-mono"
            >
              {inspection.repositoryUrl}
            </a>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Badge variant="info">{inspection.detectedFramework}</Badge>
          <Badge variant="default">{inspection.detectedLanguage}</Badge>
        </div>
      </div>

      {/* Branch selector & Commit Details */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Branch Selection */}
        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-zinc-300 uppercase tracking-wider flex items-center gap-1.5">
            <GitBranch className="w-3.5 h-3.5 text-zinc-400" />
            <span>Target Branch</span>
          </label>
          <select
            value={selectedBranch}
            onChange={(e) => onBranchChange(e.target.value)}
            className="w-full rounded-md border border-surface-border bg-input px-3 py-2 text-xs font-mono text-foreground focus:outline-none focus:border-accent"
          >
            {inspection.availableBranches.map((b) => (
              <option key={b} value={b}>
                {b} {b === inspection.defaultBranch ? "(default)" : ""}
              </option>
            ))}
          </select>
        </div>

        {/* Latest Commit Info */}
        <div className="space-y-1.5 rounded-md border border-surface-border/60 bg-black/40 p-2.5 text-xs">
          <div className="flex items-center justify-between text-zinc-400">
            <span className="flex items-center gap-1 font-semibold text-zinc-300">
              <CommitIcon className="w-3.5 h-3.5 text-primary" />
              <span className="font-mono text-primary font-bold">
                {inspection.latestCommit.hash}
              </span>
            </span>
            <span className="text-[11px] text-zinc-500 flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {formatRelativeTime(inspection.latestCommit.timestamp)}
            </span>
          </div>
          <p className="text-zinc-200 truncate font-medium">
            {inspection.latestCommit.message}
          </p>
          <div className="text-[11px] text-zinc-500 flex items-center gap-1">
            <User className="w-3 h-3" />
            <span>Author: {inspection.latestCommit.author}</span>
          </div>
        </div>
      </div>

      {/* Configuration & Dockerfile Status */}
      <div className="grid grid-cols-2 gap-3 pt-1 border-t border-surface-border/40 text-xs">
        <div className="flex items-center gap-2">
          {inspection.hasDockerfile ? (
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          ) : (
            <XCircle className="w-4 h-4 text-zinc-600 shrink-0" />
          )}
          <div>
            <div className="font-medium text-zinc-300">Dockerfile</div>
            <div className="text-[11px] text-zinc-500">
              {inspection.hasDockerfile
                ? "Custom Dockerfile detected"
                : "Automated image synthesis"}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {inspection.hasLatticeJson ? (
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          ) : (
            <XCircle className="w-4 h-4 text-zinc-600 shrink-0" />
          )}
          <div>
            <div className="font-medium text-zinc-300">lattice.json Config</div>
            <div className="text-[11px] text-zinc-500">
              {inspection.hasLatticeJson
                ? "Config file discovered in repository"
                : "Using runtime auto-configuration"}
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
}
