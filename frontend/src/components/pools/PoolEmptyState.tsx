"use client";

import React from "react";
import { ConnectionCommand } from "./ConnectionCommand";
import { Server, Radio } from "lucide-react";

interface PoolEmptyStateProps {
  joinCode: string | null;
  poolId?: string;
  expiresAt?: string;
  poolName: string;
  className?: string;
}

export function PoolEmptyState({
  joinCode,
  poolId,
  expiresAt,
  poolName,
  className,
}: PoolEmptyStateProps) {
  return (
    <div
      className={`rounded-xl border border-surface-border bg-card p-8 sm:p-12 text-center shadow-lg max-w-3xl mx-auto space-y-8 ${className || ""}`}
    >
      {/* Icon & Live indicator */}
      <div className="flex flex-col items-center justify-center space-y-3">
        <div className="w-16 h-16 rounded-2xl bg-surface border border-surface-border flex items-center justify-center text-zinc-400 shadow-inner">
          <Server className="w-8 h-8 text-primary" />
        </div>

        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-surface border border-surface-border text-xs text-zinc-300">
          <Radio className="w-3.5 h-3.5 text-primary animate-pulse" />
          <span>Waiting for workers...</span>
        </div>
      </div>

      {/* Main Copy */}
      <div className="space-y-2">
        <h2 className="text-2xl font-bold tracking-tight text-foreground">
          Your compute pool is waiting for workers
        </h2>
        <p className="text-sm text-muted-foreground max-w-lg mx-auto leading-relaxed">
          Connect a computer to contribute its available resources to{" "}
          <span className="text-zinc-200 font-medium">{poolName}</span>.
        </p>
      </div>

      {/* Dynamic Connection Command */}
      <div className="pt-2 max-w-xl mx-auto text-left">
        <ConnectionCommand
          joinCode={joinCode}
          poolId={poolId}
          poolName={poolName}
          expiresAt={expiresAt}
        />
      </div>

      {/* Explanation Checklist */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-left border-t border-surface-border/60 pt-6 text-xs text-zinc-400">
        <div className="space-y-1">
          <div className="font-semibold text-zinc-200">1. Install Agent</div>
          <p className="text-zinc-500">
            Download Lattice on your Mac, Linux machine, Windows PC, or
            Raspberry Pi.
          </p>
        </div>
        <div className="space-y-1">
          <div className="font-semibold text-zinc-200">2. Execute Join</div>
          <p className="text-zinc-500">
            Authenticate the worker daemon with your pool's unique join token.
          </p>
        </div>
        <div className="space-y-1">
          <div className="font-semibold text-zinc-200">3. Live Telemetry</div>
          <p className="text-zinc-500">
            Connection state and hardware capacity refresh from real worker
            snapshots.
          </p>
        </div>
      </div>
    </div>
  );
}
