"use client";

import React, { useState } from "react";
import { useParams } from "next/navigation";
import { DeploymentLogsViewer } from "@/components/deployments/DeploymentLogsViewer";
import { DeploymentStatusBadge } from "@/components/deployments/DeploymentStatusBadge";
import {
  useDeployment,
  useDeploymentStatus,
  useStopDeployment,
  useRedeployDeployment,
} from "@/hooks/useDeployments";
import { useDeploymentLogs } from "@/hooks/useDeploymentLogs";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { LatticeLoader } from "@/components/ui/LatticeLoader";
import {
  Github,
  GitBranch,
  Box as BoxIcon,
  Clock,
  ExternalLink,
  Copy,
  Check,
  RotateCcw,
  Square,
  AlertTriangle,
  CheckCircle2,
  Server,
  Layers,
} from "lucide-react";
import {
  formatDate,
  formatRelativeTime,
  truncateHash,
} from "@/lib/utils/formatters";
import { toast } from "sonner";
import Link from "next/link";
import { ConfirmDialog } from "@/components/modals/ConfirmDialog";
import { readyPublicUrl } from "@/lib/api/deploymentPlan";
import { ErrorState } from "@/components/ui/ErrorState";

export default function DeploymentDetailPage() {
  const params = useParams();
  const deploymentId = params?.deploymentId as string;

  const [action, setAction] = useState<"stop" | "redeploy" | null>(null);
  const [copiedUrl, setCopiedUrl] = useState(false);

  const {
    data: deployment,
    isLoading: isLoadingDep,
    error: deploymentError,
  } = useDeployment(deploymentId);
  const { data: statusInfo, error: statusError } =
    useDeploymentStatus(deploymentId);
  const {
    data: logsData,
    isLoading: isLoadingLogs,
    error: logsError,
  } = useDeploymentLogs(deploymentId);

  const stopMutation = useStopDeployment();
  const redeployMutation = useRedeployDeployment();

  const currentStatus = statusInfo?.status || deployment?.status || "queued";
  const isReady = currentStatus === "running";
  const isFailed = currentStatus === "failed";
  const isStopped = currentStatus === "stopped";
  const isBuilding = currentStatus === "building" || currentStatus === "queued";
  const isDeploying = currentStatus === "deploying";

  const applicationUrl = statusError ? null : readyPublicUrl(statusInfo);

  const handleCopyUrl = async () => {
    if (!applicationUrl) return;
    try {
      await navigator.clipboard.writeText(applicationUrl);
    } catch {
      toast.error("Clipboard unavailable. Copy the displayed URL manually.");
      return;
    }
    setCopiedUrl(true);
    toast.success("Application URL copied to clipboard");
    setTimeout(() => setCopiedUrl(false), 2000);
  };

  // Lifecycle Progression steps
  const lifecycleSteps = [
    { id: "queued", title: "Queued" },
    { id: "building", title: "Building Image" },
    { id: "deploying", title: "Starting Application" },
    { id: "running", title: "Ready" },
  ];

  const getStepState = (stepId: string) => {
    if (isFailed) return "pending";
    if (isStopped) return "stopped";

    if (currentStatus === "running") return "completed";

    if (currentStatus === "queued") {
      return stepId === "queued" ? "active" : "pending";
    }
    if (currentStatus === "building") {
      if (stepId === "queued") return "completed";
      if (stepId === "building") return "active";
      return "pending";
    }
    if (currentStatus === "deploying") {
      if (
        stepId === "queued" ||
        stepId === "building" ||
        stepId === "publishing"
      )
        return "completed";
      if (stepId === "deploying" || stepId === "readiness") return "active";
      return "pending";
    }
    return "pending";
  };

  if (deploymentError) return <ErrorState message={deploymentError.message} />;
  return (
    <>
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-surface-border/60 pb-6">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground font-mono">
              Deployment {truncateHash(deploymentId, 8)}
            </h1>
            <DeploymentStatusBadge status={currentStatus} />
          </div>

          <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground mt-2 font-mono">
            <span className="flex items-center gap-1.5 text-zinc-300">
              <Github className="w-3.5 h-3.5 text-zinc-400" />
              <span>{deployment?.repository_url || "—"}</span>
            </span>
            <span>·</span>
            <span className="flex items-center gap-1 text-zinc-400">
              <GitBranch className="w-3.5 h-3.5 text-zinc-500" />
              <span>{deployment?.branch || "main"}</span>
            </span>
            <span>·</span>
            <span className="flex items-center gap-1 text-zinc-400">
              <BoxIcon className="w-3.5 h-3.5 text-zinc-500" />
              <span>Box: {truncateHash(deployment?.box_id, 8)}</span>
            </span>
            <span>·</span>
            <span className="text-zinc-500">
              {formatDate(deployment?.created_at)}
            </span>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2.5">
          {!isStopped && !statusInfo?.stop_requested && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setAction("stop")}
              isLoading={stopMutation.isPending}
              className="gap-1.5 text-rose-400 border-rose-500/30 hover:bg-rose-500/10"
            >
              <Square className="w-3.5 h-3.5" />
              <span>Stop</span>
            </Button>
          )}

          <Button
            variant="outline"
            size="sm"
            onClick={() => setAction("redeploy")}
            isLoading={redeployMutation.isPending}
            className="gap-1.5"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Redeploy</span>
          </Button>

          {isReady && applicationUrl && (
            <a href={applicationUrl} target="_blank" rel="noreferrer">
              <Button variant="primary" size="sm" className="gap-1.5 shadow-sm">
                <span>Open Application</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </Button>
            </a>
          )}
        </div>
      </div>

      {/* Success Ready Banner / Application URL */}
      {isReady && applicationUrl && (
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-5 space-y-4">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className="p-2 rounded-lg bg-emerald-500/20 text-emerald-400">
                <CheckCircle2 className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-foreground">
                  Deployment Successful
                </h3>
                <p className="text-xs text-zinc-300 mt-0.5">
                  Your application has verified HTTP readiness and is accepting
                  traffic through the Control Plane proxy.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <a
                href={applicationUrl}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-emerald-500 text-black font-semibold text-xs hover:bg-emerald-400 transition-colors shadow-sm"
              >
                <span>Visit App</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
          </div>

          {/* Assigned URL box */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-3 rounded-lg bg-black/60 border border-emerald-500/20 font-mono text-xs">
            <div className="flex items-center gap-2 overflow-x-auto text-emerald-300">
              <span className="text-zinc-500 select-none">URL:</span>
              <a
                href={applicationUrl}
                target="_blank"
                rel="noreferrer"
                className="hover:underline font-bold"
              >
                {applicationUrl}
              </a>
            </div>

            <Button
              variant="ghost"
              size="sm"
              onClick={handleCopyUrl}
              className="h-7 px-2.5 text-xs text-zinc-400 hover:text-white shrink-0 gap-1"
            >
              {copiedUrl ? (
                <>
                  <Check className="w-3 h-3 text-emerald-400" />
                  <span>Copied</span>
                </>
              ) : (
                <>
                  <Copy className="w-3 h-3" />
                  <span>Copy URL</span>
                </>
              )}
            </Button>
          </div>

          <div className="text-[11px] text-zinc-400">
            The URL is assigned by the backend after HTTP readiness. Joined
            workers receive traffic through their authenticated outbound relay.
          </div>
        </div>
      )}

      {(statusError || logsError) && (
        <ErrorState
          title="Live refresh unavailable"
          message={(statusError || logsError)?.message}
        />
      )}
      {statusInfo?.stop_requested && !isStopped && (
        <p
          role="status"
          className="p-3 rounded-lg border border-amber-500/30 text-amber-200 text-sm"
        >
          Shutdown requested. Waiting for confirmed stop or fencing; resources
          remain reserved.
        </p>
      )}
      {/* Failure Banner */}
      {isFailed && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-5 space-y-2">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-rose-500/20 text-rose-400">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-rose-300">
                Deployment Failed
              </h3>
              <p className="text-xs text-zinc-300 mt-0.5">
                {statusInfo?.failure_message ||
                  "The container failed build or startup readiness checks."}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Lifecycle Progression Stepper */}
      <Card className="p-5 border border-surface-border bg-card">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-4">
          Deployment Progression
        </h4>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {lifecycleSteps.map((s, idx) => {
            const state = getStepState(s.id);
            return (
              <div
                key={s.id}
                className={`p-3 rounded-lg border flex flex-col justify-between space-y-2 transition-all ${
                  state === "completed"
                    ? "bg-emerald-500/5 border-emerald-500/20 text-foreground"
                    : state === "active"
                      ? "bg-sky-500/10 border-sky-500/40 text-foreground ring-1 ring-sky-500/30"
                      : isFailed
                        ? "bg-rose-500/5 border-rose-500/20 text-zinc-400"
                        : "bg-surface/30 border-surface-border text-zinc-500"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-mono text-zinc-500">
                    0{idx + 1}
                  </span>
                  {state === "completed" ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  ) : state === "active" ? (
                    <LatticeLoader size={16} stepMs={400} />
                  ) : (
                    <span className="w-2 h-2 rounded-full bg-zinc-700" />
                  )}
                </div>
                <div className="text-xs font-semibold">{s.title}</div>
              </div>
            );
          })}
        </div>
      </Card>

      {/* Replicas & Host Bindings */}
      {statusInfo?.replicas && statusInfo.replicas.length > 0 && (
        <Card className="p-5 border border-surface-border bg-card space-y-3">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Workload Replicas & Bindings
          </h4>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {statusInfo.replicas.map((rep) => (
              <div
                key={rep.replica_id}
                className="p-3.5 rounded-lg border border-surface-border bg-surface/30 space-y-2 text-xs"
              >
                <div className="flex items-center justify-between">
                  <div className="font-semibold text-zinc-200 flex items-center gap-2">
                    <Server className="w-3.5 h-3.5 text-primary" />
                    <span>Worker: {rep.worker_id}</span>
                  </div>
                  <Badge
                    variant={rep.status === "running" ? "healthy" : "default"}
                  >
                    {rep.role.toUpperCase()}
                  </Badge>
                </div>

                <div className="grid grid-cols-2 gap-2 text-zinc-400 pt-1 border-t border-surface-border/50 text-[11px] font-mono">
                  <div>
                    <span>Container:</span>{" "}
                    <span className="text-zinc-200">
                      {rep.container_id
                        ? truncateHash(rep.container_id, 10)
                        : "Pending"}
                    </span>
                  </div>
                  <div>
                    <span>Health:</span>{" "}
                    <span className="text-zinc-200">{rep.health}</span>
                  </div>
                </div>

                {rep.port_bindings && rep.port_bindings.length > 0 && (
                  <div className="pt-1 text-[11px] font-mono text-zinc-400">
                    <span>Host Port:</span>{" "}
                    <span className="text-emerald-400 font-bold">
                      {rep.port_bindings[0].host_ip}:
                      {rep.port_bindings[0].host_port} → :{rep.internal_port}
                    </span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      <ConfirmDialog
        isOpen={action !== null}
        onClose={() => setAction(null)}
        title={
          action === "stop"
            ? "Stop this deployment?"
            : "Redeploy this application?"
        }
        description={
          action === "stop"
            ? "The controller confirms shutdown before releasing resources."
            : "This stops the previous version and creates a new deployment with its saved configuration. Its URL will change."
        }
        confirmText={action === "stop" ? "Request stop" : "Redeploy"}
        isLoading={stopMutation.isPending || redeployMutation.isPending}
        onConfirm={() => {
          const mutation = action === "stop" ? stopMutation : redeployMutation;
          mutation.mutate(deploymentId, { onSuccess: () => setAction(null) });
        }}
      />
      {/* Real-time Logs Viewer */}
      <div className="space-y-2">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Deployment Logs
        </h3>
        <DeploymentLogsViewer
          logs={logsData?.logs || []}
          isLoading={isLoadingLogs}
          isLive={isBuilding || isDeploying || isReady}
        />
      </div>
    </>
  );
}
