import React from "react";
import { cn } from "@/lib/utils/cn";
import { Card } from "@/components/ui/Card";

interface MetricCardProps {
  icon?: React.ReactNode;
  label: string;
  value: React.ReactNode;
  detail?: string;
  badge?: React.ReactNode;
  onClick?: () => void;
  className?: string;
}

export function MetricCard({
  icon,
  label,
  value,
  detail,
  badge,
  onClick,
  className,
}: MetricCardProps) {
  const isClickable = Boolean(onClick);

  return (
    <Card
      role={isClickable ? "button" : undefined}
      tabIndex={isClickable ? 0 : undefined}
      onKeyDown={(e) => {
        if (isClickable && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          onClick?.();
        }
      }}
      onClick={onClick}
      className={cn(
        "p-4 transition-colors border border-card-border bg-card",
        isClickable &&
          "cursor-pointer hover:border-zinc-700 hover:bg-surface-hover hover:shadow-md",
        className,
      )}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
          {label}
        </span>
        <div className="flex items-center gap-2">
          {badge}
          {icon && <div className="text-zinc-500">{icon}</div>}
        </div>
      </div>

      <div className="flex items-baseline gap-2">
        <div className="text-2xl font-bold tracking-tight text-foreground font-sans">
          {value}
        </div>
      </div>

      {detail && (
        <div className="mt-1.5 text-xs text-muted-foreground truncate">
          {detail}
        </div>
      )}
    </Card>
  );
}
