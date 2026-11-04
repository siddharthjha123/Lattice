import React from "react";
import { cn } from "@/lib/utils/cn";

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description: string;
  action?: React.ReactNode;
  className?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center p-8 border border-dashed border-surface-border rounded-lg bg-surface/30",
        className,
      )}
    >
      {icon && (
        <div className="w-12 h-12 rounded-full bg-surface flex items-center justify-center text-muted-foreground mb-4 border border-surface-border">
          {icon}
        </div>
      )}
      <h3 className="text-base font-medium text-foreground tracking-tight">
        {title}
      </h3>
      <p className="mt-1 text-sm text-muted-foreground max-w-sm">
        {description}
      </p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
