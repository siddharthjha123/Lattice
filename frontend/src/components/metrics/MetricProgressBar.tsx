import React from "react";
import { cn } from "@/lib/utils/cn";
import {
  getUtilizationColor,
  getHealthColor,
  getBatteryColor,
} from "@/lib/utils/colors";

export type MetricBarType = "utilization" | "health" | "battery";

interface MetricProgressBarProps {
  label: string;
  value: number | null | undefined;
  type?: MetricBarType;
  unit?: string;
  className?: string;
  showValueText?: boolean;
}

export function MetricProgressBar({
  label,
  value,
  type = "utilization",
  unit = "%",
  className,
  showValueText = true,
}: MetricProgressBarProps) {
  const isAvailable = value !== null && value !== undefined && !isNaN(value);

  // Derive color details based on the metric type
  let colorInfo = {
    color: "#71717a",
    twText: "text-zinc-500",
    twBg: "bg-zinc-700",
  };
  if (isAvailable) {
    if (type === "health") {
      colorInfo = getHealthColor(value);
    } else if (type === "battery") {
      colorInfo = getBatteryColor(value);
    } else {
      colorInfo = getUtilizationColor(value);
    }
  }

  const clampedVal = isAvailable
    ? Math.max(0, Math.min(100, Math.round(value!)))
    : 0;

  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex items-center justify-between text-xs">
        <span className="text-zinc-400 font-medium">{label}</span>
        {showValueText && (
          <span className={cn("font-mono font-medium", colorInfo.twText)}>
            {isAvailable ? `${clampedVal}${unit}` : "Not available"}
          </span>
        )}
      </div>

      <div className="h-1.5 w-full rounded-full bg-zinc-800/80 overflow-hidden">
        {isAvailable ? (
          <div
            className={cn(
              "h-full rounded-full transition-transform duration-150 origin-left motion-reduce:transition-none",
              colorInfo.twBg,
            )}
            style={{
              transitionTimingFunction: "cubic-bezier(0.23, 1, 0.32, 1)",
              width: "100%",
              transform: `scaleX(${clampedVal / 100})`,
            }}
          />
        ) : (
          <div className="h-full w-full bg-zinc-800" />
        )}
      </div>
    </div>
  );
}
