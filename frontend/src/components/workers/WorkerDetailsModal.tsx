"use client";
import { useState } from "react";
import { useUiStore } from "@/stores/uiStore";
import { useTelemetryStore } from "@/stores/telemetryStore";
import {
  useWorker,
  useDisconnectWorker,
  useDeleteWorker,
} from "@/hooks/useWorkers";
import { usePools } from "@/hooks/usePools";
import { LargeDetailModal } from "@/components/modals/LargeDetailModal";
import { ConfirmDialog } from "@/components/modals/ConfirmDialog";
import { WorkerResources } from "./WorkerResources";
import { capacityChartMetrics } from "@/lib/utils/chartMetrics";
import { MultiWorkerMetricsChart } from "@/components/metrics/MultiWorkerMetricsChart";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { Button } from "@/components/ui/Button";
import { workerMetrics } from "@/lib/utils/metrics";
import { formatPercent, formatRelativeTime } from "@/lib/utils/formatters";
export function WorkerDetailsModal() {
  const { activeWorkerDetailId, closeWorkerDetail } = useUiStore();
  const query = useWorker(activeWorkerDetailId);
  const worker = query.data;
  const { history, timeRange, setTimeRange } = useTelemetryStore();
  const disconnect = useDisconnectWorker();
  const [confirm, setConfirm] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const remove = useDeleteWorker();
  const metrics = workerMetrics(worker);
  const pools = usePools();
  const pool = pools.data?.find((item) =>
    item.workers.some((item) => item.worker_id === worker?.worker_id),
  );
  const connection = pool?.workers.find(
    (item) => item.worker_id === worker?.worker_id,
  );
  const channel = (value?: boolean) =>
    value === true
      ? "Connected"
      : value === false
        ? "Disconnected"
        : "Not reported";
  const offline = worker?.status === "offline";
  const availableMetrics = (
    ["cpu", "memory", "battery", "health"] as const
  ).filter((metric) => metrics[metric] !== null);
  return (
    <>
      <LargeDetailModal
        isOpen={!!activeWorkerDetailId}
        onClose={closeWorkerDetail}
        title={worker?.hostname || "Worker details"}
        subtitle={
          worker
            ? `${worker.status} · ${worker.architecture} · last heartbeat ${formatRelativeTime(worker.last_heartbeat)}`
            : "Loading authenticated snapshot"
        }
        headerAction={
          worker ? (
            <div className="flex flex-wrap gap-2">
              {(worker.status !== "offline" ||
                connection?.control_connected ||
                connection?.application_relay_connected) && (
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => setConfirm(true)}
                >
                  Drain worker
                </Button>
              )}
              <Button
                variant="outline"
                size="sm"
                disabled={
                  worker.status !== "offline" ||
                  connection?.control_connected === true ||
                  connection?.application_relay_connected === true
                }
                title="Disconnect the worker and release its Boxes before deletion"
                onClick={() => {
                  remove.reset();
                  setDeleteConfirm(true);
                }}
              >
                Delete worker
              </Button>
            </div>
          ) : null
        }
      >
        {query.error ? (
          <ErrorState
            message={query.error.message}
            onRetry={() => query.refetch()}
          />
        ) : !worker ? (
          <LoadingState text="Loading worker…" />
        ) : (
          <>
            <div className="text-xs font-mono text-zinc-400 break-all">
              {worker.worker_id}
            </div>
            <div className="flex flex-wrap gap-x-6 gap-y-2 text-xs text-zinc-400">
              <span>
                Pool:{" "}
                <strong className="text-zinc-200">
                  {pool?.name || "Not reported"}
                </strong>
              </span>
              <span>Control: {channel(connection?.control_connected)}</span>
              <span>
                App relay: {channel(connection?.application_relay_connected)}
              </span>
            </div>
            {offline && (
              <p
                role="status"
                className="text-sm rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-amber-200"
              >
                This worker is offline. Current capacity is unavailable; saved
                container counts and the last heartbeat describe its previous
                report.
              </p>
            )}
            <WorkerResources worker={worker} />
            <section
              className="space-y-4"
              aria-label="Reported capacity history"
            >
              <div>
                <h3 className="text-sm font-semibold">Live capacity history</h3>
                <p className="text-xs text-zinc-400 mt-1">
                  Recorded from authenticated snapshots while this tab is open.
                  Zero is a reported reading; refreshing starts a new history.
                </p>
              </div>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {capacityChartMetrics.map((metric) => (
                  <MultiWorkerMetricsChart
                    key={metric}
                    metricType={metric}
                    workers={[
                      {
                        workerId: worker.worker_id,
                        workerName: worker.hostname,
                      },
                    ]}
                    history={history}
                    timeRange={timeRange}
                    height={200}
                    onTimeRangeChange={setTimeRange}
                  />
                ))}
              </div>
            </section>
            <p className="text-xs text-zinc-400">
              OS name is not included in this snapshot. CPU utilization{" "}
              {formatPercent(metrics.cpu)} · Memory utilization{" "}
              {formatPercent(metrics.memory)} · Battery{" "}
              {formatPercent(metrics.battery)} · Numeric health{" "}
              {formatPercent(metrics.health)}. Unreported fields are
              unavailable.
            </p>
            {availableMetrics.length === 0 ? (
              <div className="rounded-lg border border-surface-border bg-surface p-5 space-y-2">
                <h3 className="text-sm font-semibold">
                  Additional host metrics unavailable
                </h3>
                <p className="text-xs text-zinc-400">
                  The current worker API reports capacity and container counts,
                  but does not expose the CPU/RAM utilization, battery or
                  health-score samples these charts need. Connecting or
                  refreshing alone will not populate them.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {availableMetrics.map((metric) => (
                  <MultiWorkerMetricsChart
                    key={metric}
                    metricType={metric}
                    workers={[
                      {
                        workerId: worker.worker_id,
                        workerName: worker.hostname,
                      },
                    ]}
                    history={history}
                    timeRange={timeRange}
                    height={220}
                    onTimeRangeChange={setTimeRange}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </LargeDetailModal>
      <ConfirmDialog
        isOpen={deleteConfirm}
        onClose={() => setDeleteConfirm(false)}
        title={`Delete worker "${worker?.hostname || ""}"?`}
        description={`Worker ID: ${worker?.worker_id || "unavailable"}. This removes the retired worker from active lists and revokes its enrollment. Deployment history is retained. A deleted worker must use a new state directory to enroll again. Active leases, workloads and Box references block deletion.`}
        confirmText="Delete worker"
        isLoading={remove.isPending}
        error={remove.error?.message}
        onConfirm={() => {
          if (activeWorkerDetailId)
            remove.mutate(activeWorkerDetailId, {
              onSuccess: () => {
                setDeleteConfirm(false);
                closeWorkerDetail();
              },
            });
        }}
      />
      <ConfirmDialog
        isOpen={confirm}
        onClose={() => setConfirm(false)}
        title="Drain and disconnect this worker?"
        description="This blocks new contributions and requests workload shutdown or a funded standby handoff. Apps without failover can become unavailable."
        confirmText="Drain worker"
        isLoading={disconnect.isPending}
        onConfirm={() => {
          if (activeWorkerDetailId)
            disconnect.mutate(activeWorkerDetailId, {
              onSuccess: () => setConfirm(false),
            });
        }}
      />
    </>
  );
}
