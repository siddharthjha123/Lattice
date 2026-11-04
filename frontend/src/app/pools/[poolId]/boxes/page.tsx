"use client";

import React, { useState } from "react";
import { useParams } from "next/navigation";
import { BoxCard } from "@/components/boxes/BoxCard";
import { BoxCreationWizard } from "@/components/boxes/BoxCreationWizard";
import { usePool } from "@/hooks/usePools";
import { boxesForPool } from "@/lib/api/poolBoxes";
import { workerReady } from "@/lib/api/poolsAdapter";
import { ErrorState } from "@/components/ui/ErrorState";
import { useBoxes } from "@/hooks/useBoxes";
import { useWorkers } from "@/hooks/useWorkers";
import { Button } from "@/components/ui/Button";
import { Plus, Box as BoxIcon, ArrowLeft } from "lucide-react";
import Link from "next/link";
import { formatCores, formatGigabytes } from "@/lib/utils/formatters";

export default function PoolBoxesPage() {
  const params = useParams();
  const poolId = (params?.poolId as string) || "default";

  const {
    data: allBoxes = [],
    isLoading: isLoadingBoxes,
    error,
    refetch,
  } = useBoxes();
  const poolQuery = usePool(poolId);
  const workers = poolQuery.data?.workers || [];
  const boxes = boxesForPool(allBoxes, workers);

  const [isWizardOpen, setIsWizardOpen] = useState(false);
  const onlineWorkers = workers.filter(workerReady);

  // Sum total resources carved into Boxes
  const totalAllocatedCpu = boxes.reduce(
    (acc, b) => acc + (b.cpu_limit_cores || 0),
    0,
  );
  const totalAllocatedRam = boxes.reduce(
    (acc, b) => acc + (b.ram_limit_gb || 0),
    0,
  );
  const totalAllocatedStorage = boxes.reduce(
    (acc, b) => acc + (b.storage_limit_gb || 0),
    0,
  );

  if (error || poolQuery.error)
    return (
      <ErrorState
        message={(error || poolQuery.error)?.message}
        onRetry={() => {
          refetch();
          poolQuery.refetch();
        }}
      />
    );
  return (
    <>
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-surface-border/60 pb-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Link
              href={`/pools/${poolId}`}
              className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 font-medium"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Back to Pool</span>
            </Link>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground">
            Compute Boxes
          </h1>
          <p className="text-xs sm:text-sm text-muted-foreground mt-1">
            Allocated execution sandboxes carved from connected worker nodes
            with hard CPU and memory boundaries.
          </p>
        </div>

        <Button
          variant="primary"
          size="sm"
          onClick={() => setIsWizardOpen(true)}
          disabled={onlineWorkers.length < 2}
          className="gap-1.5 shadow-sm"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>Create Box</span>
        </Button>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="rounded-lg border border-surface-border bg-card p-4">
          <span className="text-xs text-muted-foreground uppercase font-medium">
            Total Allocated CPU
          </span>
          <div className="text-xl font-bold font-mono text-zinc-100 mt-1">
            {formatCores(totalAllocatedCpu)}
          </div>
        </div>

        <div className="rounded-lg border border-surface-border bg-card p-4">
          <span className="text-xs text-muted-foreground uppercase font-medium">
            Total Allocated RAM
          </span>
          <div className="text-xl font-bold font-mono text-zinc-100 mt-1">
            {formatGigabytes(totalAllocatedRam)}
          </div>
        </div>

        <div className="rounded-lg border border-surface-border bg-card p-4">
          <span className="text-xs text-muted-foreground uppercase font-medium">
            Total Allocated Storage
          </span>
          <div className="text-xl font-bold font-mono text-zinc-100 mt-1">
            {formatGigabytes(totalAllocatedStorage)}
          </div>
        </div>
      </div>

      {/* Boxes Grid */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            All Boxes ({boxes.length})
          </h3>
        </div>

        {isLoadingBoxes ? (
          <div className="py-12 text-center text-xs text-muted-foreground">
            Loading provisioned Boxes...
          </div>
        ) : boxes.length === 0 ? (
          <div className="rounded-xl border border-dashed border-surface-border p-12 text-center bg-surface/20 space-y-4 max-w-md mx-auto">
            <div className="w-12 h-12 rounded-full bg-surface border border-surface-border mx-auto flex items-center justify-center text-zinc-500">
              <BoxIcon className="w-6 h-6 text-zinc-400" />
            </div>
            <div>
              <h4 className="text-sm font-semibold text-foreground">
                No Compute Boxes Yet
              </h4>
              <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                A Box represents an allocated compute environment with dedicated
                CPU and RAM reservations across your workers.
              </p>
            </div>
            <Button
              variant="primary"
              size="sm"
              onClick={() => setIsWizardOpen(true)}
              disabled={onlineWorkers.length < 2}
            >
              Create Box
            </Button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {boxes.map((box) => (
              <BoxCard key={box.box_id} box={box} />
            ))}
          </div>
        )}
      </div>

      <BoxCreationWizard
        isOpen={isWizardOpen}
        onClose={() => setIsWizardOpen(false)}
        workers={workers}
        poolId={poolQuery.data?.id}
      />
    </>
  );
}
