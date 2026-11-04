"use client";

import React, { useState } from "react";
import { useParams } from "next/navigation";
import { DeletePoolButton } from "@/components/pools/DeletePoolButton";
import { PoolEmptyState } from "@/components/pools/PoolEmptyState";
import { AggregateMetricsSection } from "@/components/metrics/AggregateMetricsSection";
import { WorkerList } from "@/components/workers/WorkerList";
import { BoxCreationWizard } from "@/components/boxes/BoxCreationWizard";
import { ConnectionCommand } from "@/components/pools/ConnectionCommand";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { workerReady } from "@/lib/api/poolsAdapter";
import { usePool } from "@/hooks/usePools";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { RefreshCw, Radio, Plus, Box, ArrowRight } from "lucide-react";
import Link from "next/link";

export default function PoolDetailPage() {
  const params = useParams();
  const poolId = (params?.poolId as string) || "default";

  const {
    data: pool,
    refetch: refetchPool,
    isFetching: isFetchingPool,
    isLoading,
    error,
  } = usePool(poolId);
  const workers = pool?.workers || [];

  const [isBoxWizardOpen, setIsBoxWizardOpen] = useState(false);

  const onlineWorkers = workers.filter(workerReady);
  const hasWorkers = onlineWorkers.length > 0;

  const handleRefresh = () => {
    refetchPool();
  };

  const isRefreshing = isFetchingPool;

  if (error)
    return <ErrorState message={error.message} onRetry={() => refetchPool()} />;
  if (isLoading) return <LoadingState text="Loading pool membership…" />;
  return (
    <>
      {/* Pool Header */}
      <div className="flex flex-col xl:flex-row xl:items-center xl:justify-between gap-4 border-b border-surface-border/60 pb-6">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground">
              {pool?.name || `Pool ${poolId}`}
            </h1>
            <Badge variant={hasWorkers ? "healthy" : "warning"} showDot>
              {hasWorkers ? "Connected" : "Waiting for Workers"}
            </Badge>
          </div>

          <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground mt-1.5 font-mono">
            <span>Pool ID: {pool?.id || poolId}</span>
            <span>·</span>
            <span>
              Connected Workers:{" "}
              <strong className="text-zinc-200">{onlineWorkers.length}</strong>
            </span>
            <span>·</span>
            <span className="flex items-center gap-1.5 text-zinc-400">
              <Radio
                className={`w-3 h-3 ${
                  hasWorkers
                    ? "text-emerald-400 animate-pulse"
                    : "text-amber-400"
                }`}
              />
              <span>
                {hasWorkers ? "Mesh Active" : "Waiting for workers..."}
              </span>
            </span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {pool && <DeletePoolButton poolId={pool.id} poolName={pool.name} />}
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            isLoading={isRefreshing}
            className="gap-1.5"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Refresh</span>
          </Button>

          <Link href={`/pools/${poolId}/boxes`}>
            <Button variant="outline" size="sm" className="gap-1.5">
              <Box className="w-3.5 h-3.5" />
              <span>Manage Boxes</span>
            </Button>
          </Link>

          <Button
            variant="primary"
            size="sm"
            onClick={() => setIsBoxWizardOpen(true)}
            disabled={onlineWorkers.length < 2}
            className="gap-1.5 shadow-sm"
            title={
              onlineWorkers.length < 2
                ? "At least 2 workers must be connected to allocate Boxes"
                : "Create a new compute Box"
            }
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Create Box</span>
          </Button>
        </div>
      </div>

      {/* Conditional Rendering: Empty State vs Live Worker Mesh */}
      {workers.length === 0 ? (
        <div className="py-8">
          <PoolEmptyState
            joinCode={pool?.joinCode || null}
            poolId={pool?.id}
            expiresAt={pool?.expiresAt}
            poolName={pool?.name || "your compute pool"}
          />
        </div>
      ) : (
        <div className="space-y-8 animate-in fade-in duration-300">
          {pool && (
            <ConnectionCommand
              joinCode={pool.joinCode}
              poolName={pool.name}
              poolId={pool.id}
              expiresAt={pool.expiresAt}
              joinsUsed={pool.joinsUsed}
              maxJoins={pool.maxJoins}
            />
          )}
          {/* Aggregate Resource Metrics */}
          <AggregateMetricsSection workers={workers} />

          {/* Connected Worker Service Cards */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
                  Connected Computers ({onlineWorkers.length})
                </h3>
                <p className="text-xs text-zinc-500 mt-0.5">
                  Click any worker card to inspect detailed real-time telemetry
                  graphs.
                </p>
              </div>

              <span className="text-xs font-mono text-emerald-400 flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                <span>Live Snapshots</span>
              </span>
            </div>

            <WorkerList workers={workers} />
          </div>
        </div>
      )}

      {/* Box Creation Wizard */}
      <BoxCreationWizard
        isOpen={isBoxWizardOpen}
        onClose={() => setIsBoxWizardOpen(false)}
        workers={workers}
        poolId={pool?.id}
      />
    </>
  );
}
