import React from "react";
import { LatticeLoader } from "./LatticeLoader";
import { cn } from "@/lib/utils/cn";

export function LoadingState({
  text = "Loading data...",
  className,
  size = 64,
}: {
  text?: string;
  className?: string;
  size?: number;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center py-16 gap-4 text-muted-foreground",
        className,
      )}
    >
      <LatticeLoader size={size} />
      {text && <span className="text-sm font-medium">{text}</span>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "animate-pulse rounded bg-surface border border-surface-border/50",
        className,
      )}
    />
  );
}
