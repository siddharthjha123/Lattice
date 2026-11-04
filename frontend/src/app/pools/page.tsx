"use client";

import React from "react";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { DeletePoolButton } from "@/components/pools/DeletePoolButton";
import { usePools } from "@/hooks/usePools";
import { useUiStore } from "@/stores/uiStore";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Network, Plus, Radio, CheckCircle2, ArrowRight } from "lucide-react";
import Link from "next/link";
import { formatDate } from "@/lib/utils/formatters";

export default function PoolsPage() {
  const { data: pools = [], error, isLoading, refetch } = usePools();
  const openCreatePoolModal = useUiStore((state) => state.openCreatePoolModal);

  if (error)
    return <ErrorState message={error.message} onRetry={() => refetch()} />;
  if (isLoading) return <LoadingState text="Loading pools…" />;
  return (
    <>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-surface-border/60 pb-6">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground">
            Connection Pools
          </h1>
          <p className="text-xs sm:text-sm text-muted-foreground mt-1">
            Manage distributed worker groups, aggregate compute clusters, and
            generate node admission tokens.
          </p>
        </div>

        <Button
          variant="primary"
          size="sm"
          onClick={openCreatePoolModal}
          className="gap-1.5 shadow-sm"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>Create Connection Pool</span>
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {pools.map((pool) => {
          const isConnected = pool.workerCount > 0;

          return (
            <Card
              key={pool.id}
              className="p-5 border border-card-border bg-card hover:border-zinc-700 transition-all flex flex-col justify-between space-y-4 shadow-sm group"
            >
              <div>
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2.5">
                    <div className="p-2 rounded-lg bg-surface border border-surface-border text-primary group-hover:border-primary/40 transition-colors">
                      <Network className="w-4 h-4" />
                    </div>
                    <div>
                      <h4 className="text-base font-semibold text-foreground tracking-tight">
                        {pool.name}
                      </h4>
                      <div className="text-xs font-mono text-zinc-500 mt-0.5">
                        {pool.id}
                      </div>
                    </div>
                  </div>

                  <Badge variant={isConnected ? "healthy" : "warning"} showDot>
                    {isConnected ? "Connected" : "Waiting for Workers"}
                  </Badge>
                </div>
              </div>

              {/* Pool stats & join command snippet */}
              <div className="space-y-3 pt-3 border-t border-surface-border/50 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-zinc-500">Connected Workers:</span>
                  <span className="font-mono font-semibold text-zinc-200">
                    {pool.workerCount}
                  </span>
                </div>

                <div className="p-2 rounded bg-black/60 border border-surface-border/60 font-mono text-[11px] text-zinc-300 flex items-center justify-between">
                  <span className="truncate">
                    {pool.joinCode
                      ? "Enrollment code available in this session"
                      : "Saved enrollment code required"}
                  </span>
                </div>
              </div>

              <div className="flex justify-end">
                <DeletePoolButton poolId={pool.id} poolName={pool.name} />
              </div>
              <div className="pt-2 flex items-center justify-between text-xs">
                <span className="text-[11px] text-zinc-500">
                  Created {formatDate(pool.createdAt)}
                </span>
                <Link
                  href={`/pools/${pool.id}`}
                  className="text-primary hover:underline flex items-center gap-1 font-medium"
                >
                  <span>Open Pool</span>
                  <ArrowRight className="w-3 h-3" />
                </Link>
              </div>
            </Card>
          );
        })}
      </div>
    </>
  );
}
