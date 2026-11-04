import { WorkerSnapshot } from "@/types/contracts";
import { workerReady } from "./poolsAdapter";
export function fittingWorkers(
  workers: WorkerSnapshot[],
  limits: { cpu: number; ram: number; storage: number },
) {
  return workers.filter(
    (w) =>
      workerReady(w) &&
      w.available_cpu_cores >= limits.cpu &&
      w.available_ram_gb >= limits.ram &&
      w.available_storage_gb >= limits.storage &&
      w.active_container_count < w.max_containers,
  );
}
