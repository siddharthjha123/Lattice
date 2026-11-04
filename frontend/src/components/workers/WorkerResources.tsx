import React from "react";
import type { WorkerSnapshot } from "@/types/contracts";
import { MetricCard } from "@/components/metrics/MetricCard";
export function WorkerResources({ worker }: { worker: WorkerSnapshot }) {
  const offline = worker.status === "offline";
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold mb-3">Reported specs</h3>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <MetricCard
            label="Docker CPU cores"
            value={`${worker.cpu_cores} cores`}
          />
          <MetricCard
            label="Docker RAM"
            value={`${worker.total_ram_gb.toFixed(2)} GiB`}
          />
          <MetricCard
            label="Worker filesystem"
            value={`${worker.total_storage_gb.toFixed(1)} GiB`}
          />
          <MetricCard label="Architecture" value={worker.architecture} />
        </div>
        <p className="mt-2 text-xs text-zinc-400">
          CPU and RAM describe the Docker execution engine; storage describes
          the worker data filesystem. These are not the owner's contribution
          limits.{offline ? " Specs are from the last saved report." : ""}
        </p>
      </div>
      <div>
        <h3 className="text-sm font-semibold mb-3">
          Available for deployments
        </h3>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <MetricCard
            label="Available CPU"
            value={
              offline ? "Unavailable" : `${worker.available_cpu_cores} cores`
            }
          />
          <MetricCard
            label="Available RAM"
            value={
              offline
                ? "Unavailable"
                : `${worker.available_ram_gb.toFixed(2)} GiB`
            }
          />
          <MetricCard
            label="Available storage"
            value={
              offline
                ? "Unavailable"
                : `${worker.available_storage_gb.toFixed(1)} GiB`
            }
          />
          <MetricCard
            label={offline ? "Last reported containers" : "Containers"}
            value={`${worker.active_container_count}/${worker.max_containers}`}
          />
        </div>
      </div>
      {!offline &&
        (worker.available_cpu_cores === 0 || worker.available_ram_gb === 0) && (
          <p
            role="status"
            className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-amber-200"
          >
            This worker is reporting zero available CPU or RAM. Its specs are
            visible above, but it cannot currently accept a deployment. Owner
            budgets, existing Docker containers or local admission state can
            limit capacity. Connection status alone does not establish capacity.
          </p>
        )}
      <p className="text-xs text-zinc-400">
        Available capacity accounts for owner budgets, Docker limits and
        existing allocations. It is not CPU or RAM utilization.
      </p>
    </div>
  );
}
