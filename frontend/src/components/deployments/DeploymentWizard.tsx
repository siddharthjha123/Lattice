"use client";

import { buildDeploymentRequest } from "@/lib/api/deploymentPlan";
import { parseGitHubUrl } from "@/lib/api/repoInspectionAdapter";
import { useWorkers } from "@/hooks/useWorkers";
import { MotionSurface } from "@/components/ui/MotionSurface";
import React, { useState } from "react";
import {
  Box,
  ApplicationType,
  DeploymentCreateRequest,
} from "@/types/contracts";
import { useBoxes } from "@/hooks/useBoxes";
import { useRepositoryInspection } from "@/hooks/useRepositoryInspection";
import { useCreateDeployment } from "@/hooks/useDeployments";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { LatticeLoader } from "@/components/ui/LatticeLoader";
import { RepositoryInspectionCard } from "./RepositoryInspectionCard";
import {
  Github,
  Search,
  Box as BoxIcon,
  Cpu,
  HardDrive,
  Database,
  ArrowRight,
  ArrowLeft,
  Rocket,
  CheckCircle2,
  Plus,
  Trash2,
  AlertCircle,
} from "lucide-react";
import { formatCores, formatGigabytes } from "@/lib/utils/formatters";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

export function DeploymentWizard() {
  const searchParams = useSearchParams();
  const preselectedBoxId = searchParams.get("boxId") || "";

  const [step, setStep] = useState<1 | 2 | 3 | 4 | 5>(1);

  // Form states
  const [repoUrl, setRepoUrl] = useState(
    "https://github.com/render-examples/flask-hello-world",
  );
  const [selectedBranch, setSelectedBranch] = useState("main");
  const [selectedBoxId, setSelectedBoxId] = useState<string>(preselectedBoxId);
  const [appType, setAppType] = useState<ApplicationType>("python");
  const [startupCommand, setStartupCommand] = useState(
    '["gunicorn","app:app","--bind","0.0.0.0:8000"]',
  );
  const [internalPort, setInternalPort] = useState<number>(8000);
  const [readinessPath, setReadinessPath] = useState("/");
  const [envVars, setEnvVars] = useState<Array<{ key: string; value: string }>>(
    [],
  );

  const {
    data: boxes = [],
    isLoading: isLoadingBoxes,
    error: boxesError,
  } = useBoxes();
  const {
    data: inspection,
    isLoading: isInspecting,
    inspect,
    error: inspectionError,
  } = useRepositoryInspection();
  const [validationError, setValidationError] = useState("");
  const workerQuery = useWorkers();
  const createDeploymentMutation = useCreateDeployment();

  const handleValidateRepo = async () => {
    if (!repoUrl.trim()) return;
    try {
      const result = await inspect(repoUrl.trim());
      setSelectedBranch(result.defaultBranch);
      setAppType(result.applicationType);
      if (
        result.suggestedStartCommand &&
        result.suggestedStartCommand.length > 0
      ) {
        setStartupCommand(JSON.stringify(result.suggestedStartCommand));
      }
      if (result.suggestedInternalPort) {
        setInternalPort(result.suggestedInternalPort);
      }
      setReadinessPath(result.suggestedReadinessPath || "/");
      setStep(2);
    } catch {
      // Handled in inspection hook
    }
  };

  const handleBranchChange = async (branch: string) => {
    setSelectedBranch(branch);
    try {
      await inspect(repoUrl, branch);
    } catch {
      // Ignored
    }
  };

  const handleAddEnvVar = () => {
    setEnvVars([...envVars, { key: "", value: "" }]);
  };

  const handleRemoveEnvVar = (idx: number) => {
    setEnvVars(envVars.filter((_, i) => i !== idx));
  };

  const handleEnvChange = (
    idx: number,
    field: "key" | "value",
    val: string,
  ) => {
    const updated = [...envVars];
    updated[idx][field] = val;
    setEnvVars(updated);
  };

  const handleDeploy = async () => {
    if (!selectedBoxId) return;

    const envMap: Record<string, string> = {};
    envVars.forEach(({ key, value }) => {
      if (key.trim()) envMap[key.trim()] = value;
    });

    try {
      if (!eligibleBoxes.some((b) => b.box_id === selectedBoxId))
        throw new Error(
          "The selected Box is no longer available. Return to Box selection.",
        );
      const payload = buildDeploymentRequest({
        repoUrl,
        branch: selectedBranch,
        boxId: selectedBoxId,
        appType,
        command: startupCommand,
        port: internalPort,
        readiness: readinessPath,
        env: envVars,
      });
      setValidationError("");
      createDeploymentMutation.mutate(payload);
    } catch (err) {
      setValidationError(
        err instanceof Error
          ? err.message
          : "Invalid deployment configuration.",
      );
    }
  };
  const eligibleBoxes = boxes.filter(
    (b) =>
      b.status === "available" &&
      !b.deployment_id &&
      workerQuery.data?.some(
        (w) => w.worker_id === b.primary_worker_id && w.status === "online",
      ),
  );

  const selectedBox = boxes.find((b) => b.box_id === selectedBoxId);

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      {boxesError && (
        <p role="alert" className="text-rose-300 text-sm">
          {boxesError.message}
        </p>
      )}
      {/* Wizard Header / Steps */}
      <div className="border-b border-surface-border pb-4">
        <h2 className="text-xl font-bold tracking-tight text-foreground">
          Deploy a Git Repository
        </h2>
        <p className="text-xs text-muted-foreground mt-1">
          Distribute containerized workloads across your connected developer
          mesh
        </p>

        {/* Steps indicator */}
        <div className="flex items-center justify-between mt-6">
          {[
            { num: 1, title: "Repository" },
            { num: 2, title: "Inspection" },
            { num: 3, title: "Select Box" },
            { num: 4, title: "Build Config" },
            { num: 5, title: "Deploy" },
          ].map((s) => {
            const isCurrent = step === s.num;
            const isPast = step > s.num;
            return (
              <div key={s.num} className="flex items-center gap-2">
                <div
                  className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-semibold ${
                    isCurrent
                      ? "bg-primary text-black font-bold"
                      : isPast
                        ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                        : "bg-surface text-muted-foreground"
                  }`}
                >
                  {isPast ? "✓" : s.num}
                </div>
                <span
                  className={`text-xs font-medium hidden sm:inline ${
                    isCurrent ? "text-foreground" : "text-muted-foreground"
                  }`}
                >
                  {s.title}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {(validationError || createDeploymentMutation.error) && (
        <p role="alert" className="text-sm text-rose-300">
          {validationError || createDeploymentMutation.error?.message}
        </p>
      )}
      {inspectionError && (
        <p role="alert" className="text-sm text-amber-300">
          {inspectionError}
        </p>
      )}
      {/* Step 1: Connect Repository */}
      <MotionSurface key={step}>
        {step === 1 && (
          <div className="rounded-xl border border-surface-border bg-card p-6 space-y-6">
            <div>
              <h3 className="text-sm font-semibold text-foreground uppercase tracking-wider">
                Step 1 — Connect GitHub Repository
              </h3>
              <p className="text-xs text-muted-foreground mt-1">
                Provide a public GitHub repository URL to initiate build
                synthesis and dependency inspection.
              </p>
            </div>

            <div className="space-y-2">
              <label className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">
                GitHub Repository URL
              </label>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Github className="w-4 h-4 absolute left-3 top-2.5 text-zinc-500" />
                  <Input
                    placeholder="https://github.com/username/repository"
                    value={repoUrl}
                    onChange={(e) => {
                      setRepoUrl(e.target.value);
                      setValidationError("");
                    }}
                    className="pl-9 font-mono"
                    autoFocus
                  />
                </div>
                <Button
                  variant="primary"
                  onClick={handleValidateRepo}
                  isLoading={isInspecting}
                  disabled={!repoUrl.trim()}
                  className="gap-2 shrink-0"
                >
                  <Search className="w-4 h-4" />
                  <span>Validate & Inspect</span>
                </Button>
              </div>
            </div>
          </div>
        )}

        {step === 1 && (
          <Button
            variant="outline"
            onClick={() => {
              if (!parseGitHubUrl(repoUrl)) {
                setValidationError(
                  "Enter a valid public GitHub repository URL first.",
                );
                return;
              }
              setStep(3);
            }}
          >
            Continue with manual configuration
          </Button>
        )}
        {step >= 3 && (
          <label className="block text-xs text-zinc-400">
            Git branch
            <Input
              value={selectedBranch}
              onChange={(e) => setSelectedBranch(e.target.value)}
              placeholder="main"
            />
          </label>
        )}
        {/* Step 2: Repository Inspection */}
        {step === 2 && inspection && (
          <div className="space-y-6">
            <RepositoryInspectionCard
              inspection={inspection}
              selectedBranch={selectedBranch}
              onBranchChange={handleBranchChange}
            />

            <div className="flex items-center justify-between pt-2">
              <Button variant="ghost" onClick={() => setStep(1)}>
                <ArrowLeft className="w-4 h-4 mr-1.5" /> Back
              </Button>
              <Button
                variant="primary"
                onClick={() => setStep(3)}
                className="gap-2"
              >
                <span>Select Box</span>
                <ArrowRight className="w-4 h-4" />
              </Button>
            </div>
          </div>
        )}

        {/* Step 3: Select Box */}
        {step === 3 && (
          <div className="rounded-xl border border-surface-border bg-card p-6 space-y-6">
            <div>
              <h3 className="text-sm font-semibold text-foreground uppercase tracking-wider">
                Step 3 — Select Deployment Box
              </h3>
              <p className="text-xs text-muted-foreground mt-1">
                Choose an allocated compute Box with sufficient CPU, RAM, and
                storage limits.
              </p>
            </div>

            {isLoadingBoxes ? (
              <div className="py-8 flex flex-col items-center justify-center gap-3 text-xs text-muted-foreground">
                <LatticeLoader size={48} />
                <span>Loading available Boxes...</span>
              </div>
            ) : eligibleBoxes.length === 0 ? (
              <div className="rounded-lg border border-dashed border-surface-border p-8 text-center space-y-4 bg-surface/20">
                <div className="w-12 h-12 rounded-full bg-surface border border-surface-border mx-auto flex items-center justify-center text-zinc-500">
                  <AlertCircle className="w-6 h-6 text-amber-400" />
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-foreground">
                    No Available Boxes
                  </h4>
                  <p className="text-xs text-muted-foreground mt-1 max-w-sm mx-auto">
                    All provisioned Boxes are currently claimed by active
                    deployments, or no Boxes have been created yet.
                  </p>
                </div>
                <Link href="/pools">
                  <Button variant="primary" size="sm" className="gap-1.5">
                    <Plus className="w-3.5 h-3.5" />
                    <span>Create Box in Pool</span>
                  </Button>
                </Link>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                {eligibleBoxes.map((box) => {
                  const isSelected = selectedBoxId === box.box_id;
                  return (
                    <div
                      key={box.box_id}
                      onClick={() => setSelectedBoxId(box.box_id)}
                      className={`p-4 rounded-lg border text-left cursor-pointer transition-all ${
                        isSelected
                          ? "bg-surface-active border-primary/50 text-foreground ring-1 ring-primary/40"
                          : "bg-surface/30 border-surface-border text-muted-foreground hover:border-zinc-700"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-sm text-foreground">
                          {box.name}
                        </span>
                        <input
                          type="radio"
                          name="selectedBox"
                          aria-label={box.name}
                          checked={isSelected}
                          onChange={() => setSelectedBoxId(box.box_id)}
                          className="text-primary focus:ring-primary"
                        />
                      </div>
                      <div className="text-xs font-mono text-zinc-500 mt-0.5 truncate">
                        {box.box_id}
                      </div>

                      <div className="grid grid-cols-3 gap-2 text-xs pt-3 mt-3 border-t border-surface-border/50 text-zinc-400">
                        <div>
                          <span className="text-[10px] text-zinc-500 block">
                            CPU
                          </span>
                          <span className="font-mono text-zinc-200">
                            {formatCores(box.cpu_limit_cores)}
                          </span>
                        </div>
                        <div>
                          <span className="text-[10px] text-zinc-500 block">
                            RAM
                          </span>
                          <span className="font-mono text-zinc-200">
                            {formatGigabytes(box.ram_limit_gb)}
                          </span>
                        </div>
                        <div>
                          <span className="text-[10px] text-zinc-500 block">
                            Disk
                          </span>
                          <span className="font-mono text-zinc-200">
                            {formatGigabytes(box.storage_limit_gb)}
                          </span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            <div className="flex items-center justify-between pt-2 border-t border-surface-border">
              <Button variant="ghost" onClick={() => setStep(2)}>
                <ArrowLeft className="w-4 h-4 mr-1.5" /> Back
              </Button>
              <Button
                variant="primary"
                disabled={!selectedBoxId}
                onClick={() => setStep(4)}
                className="gap-2"
              >
                <span>Build Configuration</span>
                <ArrowRight className="w-4 h-4" />
              </Button>
            </div>
          </div>
        )}

        {/* Step 4: Build Configuration */}
        {step === 4 && (
          <div className="rounded-xl border border-surface-border bg-card p-6 space-y-6">
            <div>
              <h3 className="text-sm font-semibold text-foreground uppercase tracking-wider">
                Step 4 — Build & Runtime Configuration
              </h3>
              <p className="text-xs text-muted-foreground mt-1">
                Review and adjust runtime parameters, container start commands,
                ports, and environment variables.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Runtime Type */}
              <div>
                <label className="block text-xs font-semibold text-zinc-300 uppercase tracking-wider mb-1.5">
                  Runtime Target
                </label>
                <select
                  aria-label="Application runtime"
                  value={appType}
                  onChange={(e) =>
                    setAppType(e.target.value as ApplicationType)
                  }
                  className="w-full rounded-md border border-surface-border bg-input px-3 py-2 text-xs font-mono text-foreground focus:outline-none focus:border-accent"
                >
                  <option value="python">
                    Python 3.12 (FastAPI / WSGI / ASGI)
                  </option>
                  <option value="node">
                    Node.js 22 (Next.js / Express / Standalone)
                  </option>
                </select>
              </div>

              {/* Internal Port */}
              <div>
                <label className="block text-xs font-semibold text-zinc-300 uppercase tracking-wider mb-1.5">
                  Container Internal Port
                </label>
                <Input
                  type="number"
                  value={internalPort}
                  onChange={(e) =>
                    setInternalPort(parseInt(e.target.value) || 8000)
                  }
                  className="font-mono"
                />
              </div>
            </div>

            {/* Startup Command (JSON argument array) */}
            <div>
              <label className="block text-xs font-semibold text-zinc-300 uppercase tracking-wider mb-1.5">
                Startup Command (JSON argument array)
              </label>
              <Input
                value={startupCommand}
                onChange={(e) => setStartupCommand(e.target.value)}
                aria-label="Startup command JSON array"
                placeholder='["gunicorn","app:app","--bind","0.0.0.0:8000"]'
                className="font-mono"
              />
            </div>

            {/* Readiness Path */}
            <div>
              <label className="block text-xs font-semibold text-zinc-300 uppercase tracking-wider mb-1.5">
                HTTP Readiness Probe Path
              </label>
              <Input
                value={readinessPath}
                onChange={(e) => setReadinessPath(e.target.value)}
                aria-label="Readiness path"
                placeholder="/"
                className="font-mono"
              />
            </div>

            {/* Environment Variables */}
            <div className="space-y-3 pt-2 border-t border-surface-border/50">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">
                  Environment Variables
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleAddEnvVar}
                  className="h-7 text-xs gap-1"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>Add Variable</span>
                </Button>
              </div>

              {envVars.length === 0 ? (
                <div className="text-xs text-zinc-500 italic py-2">
                  No environment variables configured.
                </div>
              ) : (
                <div className="space-y-2">
                  {envVars.map((env, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <Input
                        aria-label="Environment variable name"
                        placeholder="KEY"
                        value={env.key}
                        onChange={(e) =>
                          handleEnvChange(i, "key", e.target.value)
                        }
                        className="font-mono text-xs uppercase"
                      />
                      <Input
                        type="password"
                        aria-label="Environment variable value"
                        placeholder="VALUE"
                        value={env.value}
                        onChange={(e) =>
                          handleEnvChange(i, "value", e.target.value)
                        }
                        className="font-mono text-xs"
                      />
                      <button
                        onClick={() => handleRemoveEnvVar(i)}
                        className="text-zinc-500 hover:text-rose-400 p-2"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="flex items-center justify-between pt-2 border-t border-surface-border">
              <Button variant="ghost" onClick={() => setStep(3)}>
                <ArrowLeft className="w-4 h-4 mr-1.5" /> Back
              </Button>
              <Button
                variant="primary"
                onClick={() => setStep(5)}
                className="gap-2"
              >
                <span>Review Deployment</span>
                <ArrowRight className="w-4 h-4" />
              </Button>
            </div>
          </div>
        )}

        {/* Step 5: Review & Deploy */}
        {step === 5 && (
          <div className="rounded-xl border border-surface-border bg-card p-6 space-y-6">
            <div>
              <h3 className="text-sm font-semibold text-foreground uppercase tracking-wider">
                Step 5 — Review and Deploy
              </h3>
              <p className="text-xs text-muted-foreground mt-1">
                Verify configuration before sending deployment instruction to
                the Control Plane.
              </p>
            </div>

            <div className="rounded-lg border border-surface-border bg-surface/30 p-5 space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                <div>
                  <span className="text-zinc-500 block">
                    Repository & Branch
                  </span>
                  <span className="font-mono font-medium text-zinc-200">
                    {repoUrl} ({selectedBranch})
                  </span>
                </div>

                <div>
                  <span className="text-zinc-500 block">
                    Assigned Compute Box
                  </span>
                  <span className="font-mono font-medium text-zinc-200">
                    {selectedBox?.name} ({selectedBox?.box_id})
                  </span>
                </div>

                <div>
                  <span className="text-zinc-500 block">
                    Application Runtime
                  </span>
                  <span className="font-mono font-medium text-zinc-200 uppercase">
                    {appType}
                  </span>
                </div>

                <div>
                  <span className="text-zinc-500 block">
                    Port & Readiness Path
                  </span>
                  <span className="font-mono font-medium text-zinc-200">
                    :{internalPort} (probe: {readinessPath})
                  </span>
                </div>
              </div>

              <div className="border-t border-surface-border/50 pt-3 text-xs">
                <span className="text-zinc-500 block mb-1">
                  Start Command (JSON argument array):
                </span>
                <code className="px-2.5 py-1 rounded bg-black/60 font-mono text-emerald-400 block truncate">
                  {startupCommand}
                </code>
              </div>
            </div>

            <div className="flex items-center justify-between pt-2 border-t border-surface-border">
              <Button variant="ghost" onClick={() => setStep(4)}>
                <ArrowLeft className="w-4 h-4 mr-1.5" /> Back
              </Button>
              <Button
                variant="primary"
                onClick={handleDeploy}
                isLoading={createDeploymentMutation.isPending}
                className="gap-2 px-6"
              >
                <Rocket className="w-4 h-4" />
                <span>Deploy Workload</span>
              </Button>
            </div>
          </div>
        )}
      </MotionSurface>
    </div>
  );
}
