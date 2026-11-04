"use client";
import { useState, useEffect } from "react";
import { WorkerSnapshot } from "@/types/contracts";
import { usePools, usePool } from "@/hooks/usePools";
import { useCreateBox } from "@/hooks/useBoxes";
import { workerReady } from "@/lib/api/poolsAdapter";
import { fittingWorkers } from "@/lib/api/admission";
import { LargeDetailModal } from "@/components/modals/LargeDetailModal";
import { MotionSurface } from "@/components/ui/MotionSurface";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { ResourceAllocationSlider } from "./ResourceAllocationSlider";
export function BoxCreationWizard({
  isOpen,
  onClose,
  poolId,
}: {
  isOpen: boolean;
  onClose: () => void;
  workers: WorkerSnapshot[];
  poolId?: string;
}) {
  const [step, setStep] = useState(1);
  const [selectedPool, setSelectedPool] = useState(poolId || "");
  const [name, setName] = useState("");
  const [cpu, setCpu] = useState(0.5);
  const [ram, setRam] = useState(0.5);
  const [storage, setStorage] = useState(1);
  const [standby, setStandby] = useState(true);
  const [ids, setIds] = useState<string[]>([]);
  const [error, setError] = useState("");
  const pools = usePools();
  const pool = usePool(poolId || selectedPool);
  const create = useCreateBox();
  const workers = pool.data?.workers.filter(workerReady) || [];
  useEffect(() => {
    if (poolId) setSelectedPool(poolId);
  }, [poolId]);
  useEffect(() => {
    if (isOpen && workers.length >= 2 && ids.length === 0)
      setIds(workers.map((w) => w.worker_id));
  }, [isOpen, workers, ids.length]);
  const candidates = workers.filter((w) => ids.includes(w.worker_id));
  const fit = fittingWorkers(candidates, { cpu, ram, storage });
  const close = () => {
    if (create.isPending) return;
    setStep(1);
    setName("");
    setIds([]);
    setError("");
    create.reset();
    onClose();
  };
  const next = () => {
    setError("");
    if (!pool.data) return setError("Choose an existing pool.");
    if (workers.length < 2)
      return setError(
        "At least two online workers with control and relay connections are required by this dashboard.",
      );
    if (!name.trim()) return setError("Enter a Box name.");
    if (
      step >= 2 &&
      (![cpu, ram, storage].every((n) => Number.isFinite(n) && n > 0) ||
        fit.length < (standby ? 2 : 1))
    )
      return setError(
        "The complete Box must fit on a primary, and on a second worker when standby is enabled. Reduce resources or change workers.",
      );
    setStep((n) => Math.min(4, n + 1));
  };
  const submit = () => {
    if (!pool.data || fit.length < (standby ? 2 : 1) || workers.length < 2)
      return setError(
        "Eligible capacity changed. Review worker connections and resource limits.",
      );
    create.mutate(
      {
        pool_id: pool.data.id,
        name: name.trim(),
        cpu_limit_cores: cpu,
        ram_limit_gb: ram,
        storage_limit_gb: storage,
        eligible_worker_ids: candidates.map((w) => w.worker_id),
        failover_enabled: standby,
      },
      { onSuccess: close },
    );
  };
  const max = (
    field: "available_cpu_cores" | "available_ram_gb" | "available_storage_gb",
  ) => Math.max(0, ...candidates.map((w) => w[field]));
  return (
    <LargeDetailModal
      isOpen={isOpen}
      onClose={close}
      title="Create a compute Box"
      subtitle="One complete workload per primary worker; optional standby reserves a second copy."
      footer={
        <>
          <Button variant="outline" onClick={close} disabled={create.isPending}>
            Cancel
          </Button>
          {step > 1 && (
            <Button
              variant="outline"
              onClick={() => setStep((n) => n - 1)}
              disabled={create.isPending}
            >
              Back
            </Button>
          )}
          {step < 4 ? (
            <Button onClick={next}>Continue</Button>
          ) : (
            <Button onClick={submit} isLoading={create.isPending}>
              Create Box
            </Button>
          )}
        </>
      }
    >
      <div className="max-w-3xl mx-auto space-y-6">
        <ol className="flex justify-between text-xs text-zinc-400">
          {["Details", "Resources", "Placement", "Review"].map((s, i) => (
            <li
              key={s}
              className={step === i + 1 ? "text-primary font-semibold" : ""}
            >
              {i + 1}. {s}
            </li>
          ))}
        </ol>
        {(error || create.error || pool.error) && (
          <p
            role="alert"
            className="text-rose-300 text-sm border border-rose-500/30 rounded-lg p-3"
          >
            {error || create.error?.message || pool.error?.message}
          </p>
        )}
        <MotionSurface key={step} className="space-y-5">
          {step === 1 && (
            <>
              <label className="block text-sm">
                Connection pool
                <select
                  aria-label="Connection pool"
                  value={poolId || selectedPool}
                  disabled={!!poolId}
                  onChange={(e) => {
                    setSelectedPool(e.target.value);
                    setIds([]);
                  }}
                  className="block mt-2 w-full bg-surface border border-surface-border rounded-md p-2"
                >
                  <option value="">Select a pool</option>
                  {pools.data?.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-sm">
                Box name
                <Input
                  required
                  maxLength={100}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="production-api"
                />
              </label>
              <p className="text-xs text-zinc-400">
                {workers.length} fully connected workers. This dashboard
                requires two before creating a Box.
              </p>
              <label className="flex gap-3 text-sm">
                <input
                  type="checkbox"
                  checked={standby}
                  onChange={(e) => setStandby(e.target.checked)}
                />
                Reserve standby capacity for failover
              </label>
            </>
          )}
          {step === 2 && (
            <>
              <ResourceAllocationSlider
                label="CPU cores"
                unit="cores"
                min={0.1}
                step={0.1}
                max={Math.max(0.1, max("available_cpu_cores"))}
                availableTotal={max("available_cpu_cores")}
                value={cpu}
                onChange={setCpu}
              />
              <ResourceAllocationSlider
                label="RAM"
                unit="GiB"
                min={0.125}
                step={0.125}
                max={Math.max(0.125, max("available_ram_gb"))}
                availableTotal={max("available_ram_gb")}
                value={ram}
                onChange={setRam}
              />
              <ResourceAllocationSlider
                label="Storage budget"
                unit="GiB"
                min={0.1}
                step={0.1}
                max={Math.max(0.1, max("available_storage_gb"))}
                availableTotal={max("available_storage_gb")}
                value={storage}
                onChange={setStorage}
              />
              <p className="text-xs text-zinc-500">
                Values are observed free worker capacity. The controller checks
                idle reservations and final admission transactionally. Storage
                is local and monitored.
              </p>
            </>
          )}
          {step === 3 && (
            <div className="space-y-3">
              {workers.map((w) => (
                <label
                  key={w.worker_id}
                  className="flex gap-3 items-center rounded-lg p-4 border border-surface-border"
                >
                  <input
                    type="checkbox"
                    checked={ids.includes(w.worker_id)}
                    onChange={(e) =>
                      setIds((v) =>
                        e.target.checked
                          ? [...v, w.worker_id]
                          : v.filter((id) => id !== w.worker_id),
                      )
                    }
                  />
                  <div>
                    <div className="text-sm">{w.hostname}</div>
                    <div className="text-xs text-zinc-400">
                      {w.available_cpu_cores} cores ·{" "}
                      {w.available_ram_gb.toFixed(2)} GiB RAM ·{" "}
                      {w.available_storage_gb.toFixed(1)} GiB storage free
                    </div>
                  </div>
                </label>
              ))}
              <p className="text-xs text-zinc-400">
                The orchestrator selects the actual primary and funded standby.
                Resource limits are not split across workers.
              </p>
            </div>
          )}
          {step === 4 && (
            <dl className="grid grid-cols-2 gap-4 text-sm">
              <dt>Pool</dt>
              <dd>{pool.data?.name}</dd>
              <dt>Box</dt>
              <dd>{name}</dd>
              <dt>CPU / RAM / storage</dt>
              <dd>
                {cpu} cores / {ram} GiB / {storage} GiB
              </dd>
              <dt>Standby</dt>
              <dd>{standby ? "Enabled" : "Disabled"}</dd>
              <dt>Workers fitting full allocation</dt>
              <dd>{fit.length}</dd>
            </dl>
          )}
        </MotionSurface>
      </div>
    </LargeDetailModal>
  );
}
