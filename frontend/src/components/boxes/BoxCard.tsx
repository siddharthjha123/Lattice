"use client";

import React, { useState } from "react";
import { Box } from "@/types/contracts";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/modals/ConfirmDialog";
import { LargeDetailModal } from "@/components/modals/LargeDetailModal";
import { useStopDeployment } from "@/hooks/useDeployments";
import { useDeleteBox } from "@/hooks/useBoxes";
import {
  Cpu,
  HardDrive,
  Database,
  Trash2,
  ArrowUpRight,
  ShieldCheck,
} from "lucide-react";
import { formatCores, formatGigabytes } from "@/lib/utils/formatters";
import Link from "next/link";

export function BoxCard({
  box,
  onViewDetails,
}: {
  box: Box;
  onViewDetails?: (box: Box) => void;
}) {
  const [details, setDetails] = useState(false);
  const [stopConfirm, setStopConfirm] = useState(false);
  const stop = useStopDeployment();
  const [isDeleting, setIsDeleting] = useState(false);
  const deleteBoxMutation = useDeleteBox();

  const statusVariant =
    box.status === "available"
      ? "healthy"
      : box.status === "deployed"
        ? "info"
        : box.status === "degraded"
          ? "warning"
          : "unhealthy";

  const handleDelete = async () => {
    try {
      await deleteBoxMutation.mutateAsync(box.box_id);
      setIsDeleting(false);
    } catch {
      // Handled in mutation
    }
  };

  return (
    <>
      <Card className="p-5 border border-card-border bg-card flex flex-col justify-between space-y-4 hover:border-zinc-700 transition-all shadow-sm">
        {/* Header */}
        <div>
          <div className="flex items-start justify-between gap-2">
            <div>
              <h4 className="text-base font-semibold text-foreground tracking-tight">
                {box.name}
              </h4>
              <div className="text-xs font-mono text-muted-foreground mt-0.5 truncate max-w-[200px]">
                {box.box_id}
              </div>
            </div>

            <Badge variant={statusVariant} showDot>
              {box.status}
            </Badge>
          </div>

          {/* Placement info */}
          <div className="mt-3 text-xs text-zinc-400 space-y-1">
            <div className="flex items-center gap-1.5">
              <span className="text-zinc-500">Primary Worker:</span>
              <span className="font-mono text-zinc-300 truncate">
                {box.primary_worker_id || "Pending placement"}
              </span>
            </div>
            {box.failover_enabled && (
              <div className="flex items-center gap-1.5 text-emerald-400/90">
                <ShieldCheck className="w-3.5 h-3.5" />
                <span>Standby:</span>
                <span className="font-mono text-zinc-300 truncate">
                  {box.standby_worker_id || "Unassigned"}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Resources Grid */}
        <div className="grid grid-cols-3 gap-2 py-2 border-y border-surface-border/50 text-xs">
          <div className="flex flex-col">
            <span className="text-zinc-500 flex items-center gap-1">
              <Cpu className="w-3 h-3" /> CPU
            </span>
            <span className="font-mono font-medium text-zinc-200 mt-0.5">
              {formatCores(box.cpu_limit_cores)}
            </span>
          </div>

          <div className="flex flex-col">
            <span className="text-zinc-500 flex items-center gap-1">
              <HardDrive className="w-3 h-3" /> RAM
            </span>
            <span className="font-mono font-medium text-zinc-200 mt-0.5">
              {formatGigabytes(box.ram_limit_gb)}
            </span>
          </div>

          <div className="flex flex-col">
            <span className="text-zinc-500 flex items-center gap-1">
              <Database className="w-3 h-3" /> Disk
            </span>
            <span className="font-mono font-medium text-zinc-200 mt-0.5">
              {formatGigabytes(box.storage_limit_gb)}
            </span>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center justify-between pt-1">
          {box.deployment_id ? (
            <Link
              href={`/deployments/${box.deployment_id}`}
              className="inline-flex items-center gap-1 text-xs text-accent hover:underline font-medium"
            >
              <span>Active Deployment</span>
              <ArrowUpRight className="w-3.5 h-3.5" />
            </Link>
          ) : (
            <Link
              href={`/deployments/new?boxId=${box.box_id}`}
              className="inline-flex items-center gap-1 text-xs text-primary hover:underline font-medium"
            >
              <span>Deploy App to Box</span>
              <ArrowUpRight className="w-3.5 h-3.5" />
            </Link>
          )}

          <div className="flex items-center gap-2">
            {true && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() =>
                  onViewDetails ? onViewDetails(box) : setDetails(true)
                }
                className="h-7 px-2 text-xs"
              >
                Details
              </Button>
            )}
            <Button
              variant="outline"
              size="icon"
              onClick={() => setIsDeleting(true)}
              className="h-7 w-7 text-zinc-500 hover:text-rose-400 hover:border-rose-500/30"
              disabled={!!box.deployment_id}
              title={
                box.deployment_id
                  ? "Stop the deployment before deleting this Box"
                  : "Delete Box"
              }
            >
              <Trash2 className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>
      </Card>

      <LargeDetailModal
        isOpen={details}
        onClose={() => setDetails(false)}
        title={box.name}
        subtitle={box.box_id}
      >
        <dl className="grid grid-cols-2 gap-4 text-sm">
          <dt>Status</dt>
          <dd>{box.status}</dd>
          <dt>CPU / RAM / storage budget</dt>
          <dd>
            {box.cpu_limit_cores} cores / {box.ram_limit_gb} GiB /{" "}
            {box.storage_limit_gb} GiB
          </dd>
          <dt>Primary</dt>
          <dd className="break-all">{box.primary_worker_id || "Pending"}</dd>
          <dt>Standby</dt>
          <dd className="break-all">
            {box.standby_worker_id || "Not reserved"}
          </dd>
        </dl>
        {box.deployment_id ? (
          <>
            <Link
              href={`/deployments/${box.deployment_id}`}
              className="text-primary underline"
            >
              View deployment
            </Link>
            <Button variant="destructive" onClick={() => setStopConfirm(true)}>
              Stop deployment
            </Button>
          </>
        ) : (
          <Link
            href={`/deployments/new?boxId=${box.box_id}`}
            className="text-primary underline"
          >
            Deploy an application
          </Link>
        )}
      </LargeDetailModal>
      <ConfirmDialog
        isOpen={stopConfirm}
        onClose={() => setStopConfirm(false)}
        title="Stop this Box's deployment?"
        description="The controller confirms shutdown or fencing before releasing reservations. A pending stop is not a completed stop."
        confirmText="Request stop"
        isLoading={stop.isPending}
        onConfirm={() => {
          if (box.deployment_id)
            stop.mutate(box.deployment_id, {
              onSuccess: () => setStopConfirm(false),
            });
        }}
      />
      <ConfirmDialog
        isOpen={isDeleting}
        onClose={() => setIsDeleting(false)}
        onConfirm={handleDelete}
        title={`Delete Box "${box.name}"?`}
        description="This will release the reserved capacity on the primary and standby worker nodes. This action cannot be undone."
        confirmText="Delete Box"
        isLoading={deleteBoxMutation.isPending}
      />
    </>
  );
}
