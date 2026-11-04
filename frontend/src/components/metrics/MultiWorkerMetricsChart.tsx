"use client";

import React, { useState, useMemo } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import {
  buildChartRows,
  chartMetrics,
  ChartMetric,
  formatChartValue,
} from "@/lib/utils/chartMetrics";
import { getWorkerColor } from "@/lib/utils/colors";
import { MetricTimeRange, MetricSnapshot } from "@/types/telemetry";

export interface WorkerInfo {
  workerId: string;
  workerName: string;
  color?: string;
}

interface MultiWorkerMetricsChartProps {
  metricType: ChartMetric;
  workers: WorkerInfo[];
  history: Record<string, MetricSnapshot[]>;
  timeRange?: MetricTimeRange;
  height?: number;
  onTimeRangeChange?: (range: MetricTimeRange) => void;
  className?: string;
}

export function MultiWorkerMetricsChart({
  metricType,
  workers,
  history,
  timeRange = "5m",
  height = 320,
  onTimeRangeChange,
  className,
}: MultiWorkerMetricsChartProps) {
  const [hoveredWorkerId, setHoveredWorkerId] = useState<string | null>(null);

  // Assign distinct colors to each worker
  const workerColorMap = useMemo(() => {
    const map = new Map<string, string>();
    workers.forEach((w, idx) => {
      map.set(w.workerId, w.color || getWorkerColor(idx));
    });
    return map;
  }, [workers]);

  const chartData = useMemo(
    () =>
      buildChartRows(
        workers.map((w) => w.workerId),
        history,
        metricType,
        timeRange,
      ),
    [workers, history, metricType, timeRange],
  );
  const { title, unit } = chartMetrics[metricType];

  return (
    <section
      aria-label={title}
      className={`flex flex-col space-y-4 ${className || ""}`}
    >
      {/* Chart Header & Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h4 className="text-sm font-semibold text-foreground tracking-tight">
            {title}
          </h4>
          <span className="text-xs text-muted-foreground font-mono">
            ({unit})
          </span>
        </div>

        {/* Time range selector */}
        {onTimeRangeChange && (
          <div className="flex items-center space-x-1 rounded-md border border-surface-border bg-surface/50 p-0.5 text-xs">
            {(["1m", "5m", "15m", "1h"] as MetricTimeRange[]).map((range) => (
              <button
                aria-label={`${title}: ${range}`}
                aria-pressed={timeRange === range}
                key={range}
                onClick={() => onTimeRangeChange(range)}
                className={`px-2.5 py-1 rounded font-medium transition-colors ${
                  timeRange === range
                    ? "bg-surface-active text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {range}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Recharts Canvas */}
      <div className="relative w-full rounded-lg border border-surface-border bg-black/60 p-4">
        {!chartData.some((row) =>
          workers.some((w) => typeof row[w.workerId] === "number"),
        ) ? (
          <div
            className="flex items-center justify-center text-xs text-muted-foreground font-mono"
            style={{ height }}
          >
            This metric is not reported in the received snapshots.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={height}>
            <LineChart
              data={chartData}
              margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
              onMouseLeave={() => setHoveredWorkerId(null)}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="#1f212a"
                vertical={false}
              />
              <XAxis
                dataKey="timeLabel"
                stroke="#52525b"
                tick={{ fontSize: 11, fill: "#71717a" }}
                tickLine={false}
                axisLine={{ stroke: "#27272a" }}
              />
              <YAxis
                domain={unit === "%" ? [0, 100] : [0, "auto"]}
                allowDecimals={metricType !== "containers"}
                stroke="#52525b"
                tick={{ fontSize: 11, fill: "#71717a" }}
                tickLine={false}
                axisLine={{ stroke: "#27272a" }}
                tickFormatter={(val) =>
                  unit === "%" ? `${val}%` : String(val)
                }
              />
              <Tooltip
                content={({ active, payload, label }) => {
                  if (!active || !payload || !payload.length) return null;

                  return (
                    <div className="rounded-md border border-surface-border bg-card p-2.5 shadow-xl text-xs space-y-1.5 min-w-[160px]">
                      <div className="text-[11px] font-mono text-zinc-400 border-b border-surface-border/60 pb-1">
                        {label}
                      </div>
                      {payload.map((entry: any) => {
                        const workerId = entry.dataKey;
                        const worker = workers.find(
                          (w) => w.workerId === workerId,
                        );
                        const isHovered = hoveredWorkerId === workerId;
                        const isAnyHovered = hoveredWorkerId !== null;
                        const originalColor =
                          workerColorMap.get(workerId) || "#38bdf8";

                        return (
                          <div
                            key={workerId}
                            className={`flex items-center justify-between gap-3 ${
                              isHovered
                                ? "font-semibold text-foreground"
                                : isAnyHovered
                                  ? "text-zinc-600 grayscale"
                                  : "text-zinc-300"
                            }`}
                          >
                            <div className="flex items-center gap-1.5 truncate">
                              <span
                                className="w-2 h-2 rounded-full shrink-0"
                                style={{
                                  backgroundColor:
                                    isAnyHovered && !isHovered
                                      ? "#52525b"
                                      : originalColor,
                                }}
                              />
                              <span className="truncate">
                                {worker?.workerName || workerId}
                              </span>
                            </div>
                            <span className="font-mono">
                              {entry.value !== null && entry.value !== undefined
                                ? formatChartValue(Number(entry.value), unit)
                                : "N/A"}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  );
                }}
              />

              {/* Render dynamic line per worker */}
              {workers.map((w) => {
                const originalColor =
                  workerColorMap.get(w.workerId) || "#38bdf8";
                const isHovered = hoveredWorkerId === w.workerId;
                const isAnyHovered = hoveredWorkerId !== null;

                // Requirement: Hovering a worker keeps it fully visible and grayscales others
                const strokeColor = isHovered
                  ? originalColor
                  : isAnyHovered
                    ? "#3f3f46" // Grayscale de-emphasized
                    : originalColor;

                const strokeOpacity = isHovered ? 1 : isAnyHovered ? 0.25 : 0.9;
                const strokeWidth = isHovered ? 3 : isAnyHovered ? 1.2 : 2;

                return (
                  <Line
                    key={w.workerId}
                    type="monotone"
                    dataKey={w.workerId}
                    name={w.workerName}
                    stroke={strokeColor}
                    strokeWidth={strokeWidth}
                    strokeOpacity={strokeOpacity}
                    dot={{ r: 2 }}
                    activeDot={
                      isHovered
                        ? {
                            r: 5,
                            fill: originalColor,
                            stroke: "#000",
                            strokeWidth: 2,
                          }
                        : false
                    }
                    connectNulls={false}
                    isAnimationActive={false}
                  />
                );
              })}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Interactive Legend with Worker Hover State */}
      <div className="flex flex-wrap items-center gap-3 pt-1">
        {workers.map((w) => {
          const originalColor = workerColorMap.get(w.workerId) || "#38bdf8";
          const isHovered = hoveredWorkerId === w.workerId;
          const isAnyHovered = hoveredWorkerId !== null;

          return (
            <button
              key={w.workerId}
              onFocus={() => setHoveredWorkerId(w.workerId)}
              onBlur={() => setHoveredWorkerId(null)}
              onMouseEnter={() => setHoveredWorkerId(w.workerId)}
              onMouseLeave={() => setHoveredWorkerId(null)}
              className={`flex items-center gap-2 px-2.5 py-1 rounded-md text-xs border focus-visible:ring-2 focus-visible:ring-primary ${
                isHovered
                  ? "bg-surface-active border-zinc-600 text-foreground shadow-sm"
                  : isAnyHovered
                    ? "opacity-40 grayscale border-transparent text-zinc-500"
                    : "bg-surface/40 border-surface-border text-zinc-300 hover:border-zinc-700"
              }`}
            >
              <span
                className="w-2.5 h-2.5 rounded-full"
                style={{
                  backgroundColor:
                    isAnyHovered && !isHovered ? "#52525b" : originalColor,
                }}
              />
              <span className="font-medium">{w.workerName}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
