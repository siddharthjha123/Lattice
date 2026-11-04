/** Real pool endpoints; enrollment codes only exist after backend create/rotate. */
import { apiClient } from "./client";
import {
  ConnectionPool,
  PoolRecord,
  PoolStatus,
  PoolCreationPayload,
} from "@/types/pool";
const codes = new Map<string, { code: string; expiresAt: string }>();
export function clearPoolCodes() {
  codes.clear();
}
export function workerReady(w: import("@/types/contracts").WorkerSnapshot) {
  return (
    w.status === "online" &&
    w.control_connected === true &&
    w.application_relay_connected === true
  );
}
function adapt(
  record: PoolRecord,
  workers: PoolStatus["workers"] = [],
): ConnectionPool {
  if (record.pool_code)
    codes.set(record.pool_id, {
      code: record.pool_code,
      expiresAt: record.join_code_expires_at,
    });
  else if (codes.get(record.pool_id)?.expiresAt !== record.join_code_expires_at)
    codes.delete(record.pool_id);
  const workerCount = workers.filter(workerReady).length;
  return {
    id: record.pool_id,
    name: record.name,
    joinCode: codes.get(record.pool_id)?.code || null,
    workerCount,
    status: workerCount ? "connected" : "waiting",
    createdAt: record.created_at,
    expiresAt: record.join_code_expires_at,
    joinsUsed: record.joins_used,
    maxJoins: record.max_joins,
    workers,
  };
}
export async function getPool(poolId: string) {
  const records = await apiClient<PoolRecord[]>("/api/pools");
  const record =
    poolId === "default"
      ? records[0]
      : records.find((p) => p.pool_id === poolId);
  if (!record)
    throw new Error("Pool not found. Create or select a pool first.");
  const status = await apiClient<PoolStatus>(
    `/api/pools/${encodeURIComponent(record.pool_id)}/status`,
  );
  return adapt(status, status.workers);
}
export async function listPools() {
  const records = await apiClient<PoolRecord[]>("/api/pools");
  return Promise.all(
    records.map(async (r) => {
      const status = await apiClient<PoolStatus>(
        `/api/pools/${r.pool_id}/status`,
      );
      return adapt(status, status.workers);
    }),
  );
}
export async function createPool(payload: PoolCreationPayload) {
  return adapt(
    await apiClient<PoolRecord>("/api/pools", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  );
}
export async function rotatePoolCode(id: string) {
  return adapt(
    await apiClient<PoolRecord>(`/api/pools/${id}/rotate-code`, {
      method: "POST",
    }),
  );
}

export async function deletePool(id: string): Promise<void> {
  await apiClient<void>(`/api/pools/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  codes.delete(id);
}
