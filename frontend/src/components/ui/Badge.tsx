import React from "react";
import { cn } from "@/lib/utils/cn";

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?:
    | "healthy"
    | "warning"
    | "unhealthy"
    | "offline"
    | "info"
    | "default"
    | "outline";
  showDot?: boolean;
}

export function Badge({
  className,
  variant = "default",
  showDot = false,
  children,
  ...props
}: BadgeProps) {
  const variantStyles = {
    healthy: "bg-emerald-500/10 text-emerald-400 border-emerald-500/25",
    warning: "bg-amber-500/10 text-amber-400 border-amber-500/25",
    unhealthy: "bg-rose-500/10 text-rose-400 border-rose-500/25",
    offline: "bg-zinc-800 text-zinc-400 border-zinc-700",
    info: "bg-sky-500/10 text-sky-400 border-sky-500/25",
    default: "bg-surface text-foreground border-surface-border",
    outline: "bg-transparent text-muted-foreground border-surface-border",
  };

  const dotColors = {
    healthy: "bg-emerald-400",
    warning: "bg-amber-400",
    unhealthy: "bg-rose-400",
    offline: "bg-zinc-500",
    info: "bg-sky-400",
    default: "bg-zinc-400",
    outline: "bg-zinc-400",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium border uppercase tracking-wider",
        variantStyles[variant],
        className,
      )}
      {...props}
    >
      {showDot && (
        <span
          className={cn(
            "w-1.5 h-1.5 rounded-full animate-pulse",
            dotColors[variant],
          )}
        />
      )}
      {children}
    </span>
  );
}
