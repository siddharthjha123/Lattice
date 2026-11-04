"use client";
import { WorkerSnapshot } from "@/types/contracts";
import { MetricCard } from "./MetricCard";
import { LargeDetailModal } from "@/components/modals/LargeDetailModal";
import { MultiWorkerMetricsChart } from "./MultiWorkerMetricsChart";
import { useUiStore } from "@/stores/uiStore";
import { useTelemetryStore } from "@/stores/telemetryStore";
import { workerMetrics } from "@/lib/utils/metrics";
import { formatPercent } from "@/lib/utils/formatters";
export function AggregateMetricsSection({
  workers,
}: {
  workers: WorkerSnapshot[];
}) {
  const {
    isAggregateModalOpen,
    aggregateMetricType,
    openAggregateModal,
    closeAggregateModal,
  } = useUiStore();
  const { history, timeRange, setTimeRange } = useTelemetryStore();
  const connected = workers.filter((w) => w.status === "online");
  const sum = (
    field:
      "cpu_cores" | "available_cpu_cores" | "total_ram_gb" | "available_ram_gb",
  ) => connected.reduce((n, w) => n + w[field], 0);
  const average = (metric: "cpu" | "memory" | "battery" | "health") => {
    const values = connected.map((w) => workerMetrics(w)[metric]);
    return values.length && values.every((v) => v !== null)
      ? values.reduce<number>((n, v) => n + (v || 0), 0) / values.length
      : null;
  };
  return (
    <>
      <div className="space-y-3">
        <h3 className="text-sm text-muted-foreground uppercase font-semibold">
          Pool capacity and reported metrics
        </h3>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <MetricCard
            label="Online workers"
            value={connected.length}
            detail={`${workers.length} enrolled workers`}
          />
          <MetricCard
            label="Available CPU"
            value={`${sum("available_cpu_cores").toFixed(1)} cores`}
            detail={`${sum("cpu_cores")} total hardware cores; before idle holds`}
          />
          <MetricCard
            label="Available RAM"
            value={`${sum("available_ram_gb").toFixed(2)} GiB`}
            detail={`${sum("total_ram_gb").toFixed(1)} GiB total hardware RAM`}
          />
          <MetricCard
            label="CPU utilization"
            value={formatPercent(average("cpu"))}
            detail="Reported utilization only"
            onClick={() => openAggregateModal("cpu")}
          />
          <MetricCard
            label="Memory utilization"
            value={formatPercent(average("memory"))}
            detail="Reported utilization only"
            onClick={() => openAggregateModal("memory")}
          />
          <MetricCard
            label="Battery"
            value={formatPercent(average("battery"))}
            detail="Unavailable when hardware data is absent"
            onClick={() => openAggregateModal("battery")}
          />
          <MetricCard
            label="Health score"
            value={formatPercent(average("health"))}
            detail="Connection status is shown on worker cards"
            onClick={() => openAggregateModal("health")}
          />
          <MetricCard
            label="Active containers"
            value={connected.reduce((n, w) => n + w.active_container_count, 0)}
            detail="Latest authenticated worker snapshots"
          />
        </div>
        <p className="text-xs text-zinc-500">
          Missing utilization, battery and numeric health readings remain
          unavailable. Free capacity is not a measurement of CPU usage.
        </p>
      </div>
      <LargeDetailModal
        isOpen={isAggregateModalOpen}
        onClose={closeAggregateModal}
        title="Multi-worker metrics"
        subtitle="History contains only snapshots received in this tab; absent metrics are not estimated."
      >
        <MultiWorkerMetricsChart
          metricType={aggregateMetricType}
          workers={workers.map((w) => ({
            workerId: w.worker_id,
            workerName: w.hostname,
          }))}
          history={history}
          timeRange={timeRange}
          onTimeRangeChange={setTimeRange}
        />
      </LargeDetailModal>
    </>
  );
}
