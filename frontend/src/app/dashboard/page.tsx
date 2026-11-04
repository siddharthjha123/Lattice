"use client";

import React, { useState } from "react";
import { AggregateMetricsSection } from "@/components/metrics/AggregateMetricsSection";
import { WorkerList } from "@/components/workers/WorkerList";
import { BoxCard } from "@/components/boxes/BoxCard";
import { DeploymentTable } from "@/components/deployments/DeploymentTable";
import { BoxCreationWizard } from "@/components/boxes/BoxCreationWizard";
import { LoadingState } from "@/components/ui/LoadingState";
import { ErrorState } from "@/components/ui/ErrorState";
import { useWorkers } from "@/hooks/useWorkers";
import { useBoxes } from "@/hooks/useBoxes";
import { useDeployments } from "@/hooks/useDeployments";
import { useUiStore } from "@/stores/uiStore";
import { useAuthStore } from "@/stores/authStore";
import { Button } from "@/components/ui/Button";
import {
  Rocket,
  Plus,
  Box as BoxIcon,
  Server,
  ArrowRight,
  Radio,
} from "lucide-react";
import Link from "next/link";

export default function DashboardPage() {
  const user = useAuthStore((state) => state.user);
  const openCreatePoolModal = useUiStore((state) => state.openCreatePoolModal);
  const [isBoxWizardOpen, setIsBoxWizardOpen] = useState(false);

  const {
    data: workers = [],
    error: workerError,
    isLoading: loadingWorkers,
  } = useWorkers();
  const {
    data: boxes = [],
    error: boxError,
    isLoading: loadingBoxes,
  } = useBoxes();
  const {
    data: deployments = [],
    error: deploymentError,
    isLoading: loadingDeployments,
  } = useDeployments();

  if (loadingWorkers || loadingBoxes || loadingDeployments)
    return <LoadingState text="Loading controller inventory…" />;
  const onlineWorkers = workers.filter((w) => w.status === "online");

  if (workerError || boxError || deploymentError)
    return (
      <ErrorState
        message={(workerError || boxError || deploymentError)?.message}
      />
    );
  return (
    <>
      {/* Top Banner / Welcome */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-surface-border/60 pb-6">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground">
            Overview
          </h1>
          <p className="text-xs sm:text-sm text-muted-foreground mt-1">
            Welcome back, {user.name}. Your distributed compute mesh is active
            across {onlineWorkers.length} connected machines.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={openCreatePoolModal}
            className="gap-1.5"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Create Pool</span>
          </Button>

          <Link href="/deployments/new">
            <Button variant="primary" size="sm" className="gap-1.5 shadow-sm">
              <Rocket className="w-3.5 h-3.5" />
              <span>Deploy App</span>
            </Button>
          </Link>
        </div>
      </div>

      {/* Aggregate Resource Metrics Section */}
      <AggregateMetricsSection workers={workers} />

      {/* Connected Computers Section */}
      <div className="space-y-4 pt-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              Connected Workers
            </h3>
            <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-surface border border-surface-border text-zinc-300">
              {onlineWorkers.length} active
            </span>
          </div>

          <Link
            href="/pools"
            className="text-xs text-accent hover:underline flex items-center gap-1 font-medium"
          >
            <span>View All Pools</span>
            <ArrowRight className="w-3 h-3" />
          </Link>
        </div>

        {workers.length === 0 ? (
          <div className="rounded-xl border border-dashed border-surface-border p-8 text-center bg-surface/20 space-y-3">
            <div className="w-10 h-10 rounded-full bg-surface border border-surface-border mx-auto flex items-center justify-center text-zinc-500">
              <Radio className="w-5 h-5 text-primary animate-pulse" />
            </div>
            <h4 className="text-sm font-semibold text-foreground">
              No Worker Computers Connected
            </h4>
            <p className="text-xs text-muted-foreground max-w-sm mx-auto">
              Join your first computer using the Lattice CLI to start
              contributing CPU and memory.
            </p>
            <Link href="/pools/default">
              <Button variant="outline" size="sm" className="mt-2">
                Open Connection Wizard
              </Button>
            </Link>
          </div>
        ) : (
          <WorkerList workers={workers} />
        )}
      </div>

      {/* Allocated Boxes Section */}
      <div className="space-y-4 pt-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              Compute Boxes
            </h3>
            <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-surface border border-surface-border text-zinc-300">
              {boxes.length} allocated
            </span>
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={() => setIsBoxWizardOpen(true)}
            className="gap-1.5 h-7 text-xs"
          >
            <Plus className="w-3 h-3" />
            <span>Create Box</span>
          </Button>
        </div>

        {boxes.length === 0 ? (
          <div className="rounded-xl border border-dashed border-surface-border p-8 text-center bg-surface/20 space-y-3">
            <div className="w-10 h-10 rounded-full bg-surface border border-surface-border mx-auto flex items-center justify-center text-zinc-500">
              <BoxIcon className="w-5 h-5 text-zinc-400" />
            </div>
            <h4 className="text-sm font-semibold text-foreground">
              No Compute Boxes Created
            </h4>
            <p className="text-xs text-muted-foreground max-w-sm mx-auto">
              Boxes carve out dedicated CPU, RAM, and storage limits from your
              worker mesh for deploying applications.
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsBoxWizardOpen(true)}
              className="mt-2"
            >
              Create First Box
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

      {/* Recent Deployments Table */}
      <div className="space-y-4 pt-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              Recent Deployments
            </h3>
            <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-surface border border-surface-border text-zinc-300">
              {deployments.length} total
            </span>
          </div>

          <Link
            href="/deployments"
            className="text-xs text-accent hover:underline flex items-center gap-1 font-medium"
          >
            <span>View All Deployments</span>
            <ArrowRight className="w-3 h-3" />
          </Link>
        </div>

        <DeploymentTable deployments={deployments.slice(0, 5)} />
      </div>

      {/* Box Creation Modal */}
      <BoxCreationWizard
        isOpen={isBoxWizardOpen}
        onClose={() => setIsBoxWizardOpen(false)}
        workers={workers}
      />
    </>
  );
}
