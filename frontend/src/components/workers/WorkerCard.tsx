"use client";

import React from "react";
import { workerMetrics } from "@/lib/utils/metrics";
import { WorkerSnapshot } from "@/types/contracts";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { MetricProgressBar } from "@/components/metrics/MetricProgressBar";
import { formatRelativeTime } from "@/lib/utils/formatters";
import { useUiStore } from "@/stores/uiStore";

interface WorkerCardProps {
  worker: WorkerSnapshot;
  className?: string;
}

export function WorkerCard({ worker, className }: WorkerCardProps) {
  const openWorkerDetail = useUiStore((state) => state.openWorkerDetail);

  const {
    cpu: cpuUtil,
    memory: memUtil,
    battery,
    health,
  } = workerMetrics(worker);
  const isOnline = worker.status === "online";
  const statusVariant = isOnline
    ? "healthy"
    : worker.status === "unhealthy"
      ? "warning"
      : "offline";

  return (
    <Card
      role="button"
      tabIndex={0}
      aria-label={`Inspect ${worker.hostname}`}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          openWorkerDetail(worker.worker_id);
        }
      }}
      onClick={() => openWorkerDetail(worker.worker_id)}
      className={`p-4 border border-card-border bg-card hover:border-zinc-700 hover:bg-surface-hover transition-all cursor-pointer flex flex-col justify-between space-y-4 shadow-sm ${className || ""}`}
    >
      {/* Header */}
      <div>
        <div className="flex items-center justify-between gap-2">
          <h4 className="text-sm font-semibold text-foreground truncate tracking-tight">
            {worker.hostname || worker.worker_id}
          </h4>
          <Badge variant={statusVariant} showDot>
            {worker.status}
          </Badge>
        </div>

        <div className="text-xs font-mono text-muted-foreground truncate mt-0.5">
          {worker.worker_id}
        </div>

        <div className="text-[11px] text-zinc-500 mt-1 flex flex-wrap items-center gap-2">
          <span>{worker.architecture.toUpperCase()}</span>
          <span>·</span>
          <span>{worker.cpu_cores} Docker cores</span>
          <span>·</span>
          <span>{worker.total_ram_gb.toFixed(2)} GiB Docker RAM</span>
        </div>
      </div>

      <div className="text-xs text-zinc-400">
        {worker.status === "offline" ? (
          "Current capacity unavailable while offline"
        ) : (
          <>
            Available: {worker.available_cpu_cores} cores ·{" "}
            {worker.available_ram_gb.toFixed(2)} GiB RAM
          </>
        )}
        <br />
        {worker.status === "offline"
          ? "Last reported containers"
          : "Containers"}
        : {worker.active_container_count}/{worker.max_containers}
      </div>
      {/* Metric Progress Bars */}
      <div className="space-y-2.5 py-1">
        <MetricProgressBar label="CPU" value={cpuUtil} type="utilization" />

        <MetricProgressBar label="Battery" value={battery} type="battery" />

        <MetricProgressBar label="Memory" value={memUtil} type="utilization" />

        <MetricProgressBar label="Health" value={health} type="health" />
      </div>

      {/* Footer */}
      <div className="pt-2 border-t border-surface-border/50 text-[11px] text-zinc-500 flex items-center justify-between">
        <span>Last heartbeat</span>
        <span className="font-mono text-zinc-400">
          {formatRelativeTime(worker.last_heartbeat)}
        </span>
      </div>
    </Card>
  );
}
