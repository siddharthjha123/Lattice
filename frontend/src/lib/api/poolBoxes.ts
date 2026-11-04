import { Box, WorkerSnapshot } from "@/types/contracts";
/** Box responses predate pool_id. Server-enforced eligible membership identifies scope. */
export function boxesForPool(boxes: Box[], workers: WorkerSnapshot[]) {
  const members = new Set(workers.map((w) => w.worker_id));
  return boxes.filter(
    (b) =>
      b.eligible_worker_ids.length > 0 &&
      b.eligible_worker_ids.every((id) => members.has(id)),
  );
}
