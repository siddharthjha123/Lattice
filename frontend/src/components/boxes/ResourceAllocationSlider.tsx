import React, { useId } from "react";
import { cn } from "@/lib/utils/cn";

interface ResourceAllocationSliderProps {
  label: string;
  unit: string;
  min?: number;
  max: number;
  step?: number;
  value: number;
  onChange: (val: number) => void;
  availableTotal?: number;
  className?: string;
  disabled?: boolean;
}

export function ResourceAllocationSlider({
  label,
  unit,
  min = 0.5,
  max,
  step = 0.5,
  value,
  onChange,
  availableTotal = max,
  className,
  disabled = false,
}: ResourceAllocationSliderProps) {
  const labelId = useId();
  const safeMax = Math.max(min, max);
  const remaining = Math.max(0, availableTotal - value);

  return (
    <div
      className={cn(
        "space-y-3 rounded-lg border border-surface-border bg-surface/30 p-4",
        className,
      )}
    >
      <div className="flex items-center justify-between">
        <div>
          <span
            id={labelId}
            className="text-xs font-semibold text-zinc-300 uppercase tracking-wider"
          >
            {label}
          </span>
          <div className="text-[11px] text-muted-foreground mt-0.5">
            Observed maximum on one worker:{" "}
            <span className="font-mono text-zinc-300">
              {availableTotal} {unit}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <input
            aria-labelledby={labelId}
            type="number"
            min={min}
            max={safeMax}
            step={step}
            value={value}
            disabled={disabled}
            onChange={(e) => {
              const val = parseFloat(e.target.value);
              if (!isNaN(val)) {
                onChange(Math.min(safeMax, Math.max(min, val)));
              }
            }}
            className="w-20 rounded border border-surface-border bg-input px-2.5 py-1 font-mono text-sm text-right text-foreground focus:outline-none focus:border-accent"
          />
          <span className="text-xs font-mono text-zinc-400">{unit}</span>
        </div>
      </div>

      {/* Range Slider */}
      <input
        aria-label={`${label} allocation`}
        type="range"
        min={min}
        max={safeMax}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full h-1.5 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-primary"
      />

      {/* Remaining Capacity Bar */}
      <div className="flex items-center justify-between text-[11px] text-zinc-500 pt-0.5">
        <span>
          Allocating:{" "}
          <strong className="text-primary font-mono">
            {value} {unit}
          </strong>
        </span>
        <span>
          Remaining:{" "}
          <strong className="text-zinc-300 font-mono">
            {remaining.toFixed(1)} {unit}
          </strong>
        </span>
      </div>
    </div>
  );
}
