import { useEffect } from "react";
import { useTelemetryStore } from "@/stores/telemetryStore";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listPools,
  getPool,
  createPool,
  rotatePoolCode,
  deletePool,
} from "@/lib/api/poolsAdapter";
import { useOperatorSession } from "@/stores/authStore";
import { toast } from "sonner";
export function usePools() {
  const enabled = useOperatorSession();
  return useQuery({
    queryKey: ["pools"],
    queryFn: listPools,
    enabled,
    refetchInterval: 5000,
  });
}
export function usePool(id: string) {
  const enabled = useOperatorSession();
  const query = useQuery({
    queryKey: ["pool", id],
    queryFn: () => getPool(id),
    enabled: enabled && !!id,
    refetchInterval: 3000,
  });
  const ingest = useTelemetryStore((s) => s.ingestWorkerSnapshots);
  useEffect(() => {
    if (query.data) ingest(query.data.workers);
  }, [query.data, ingest]);
  return query;
}
export function useCreatePool() {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: createPool,
    onSuccess: (pool) => {
      cache.setQueryData(["pool", pool.id], pool);
      cache.invalidateQueries({ queryKey: ["pools"] });
      toast.success(`Pool "${pool.name}" created.`);
    },
    onError: (err: Error) => toast.error(err.message),
  });
}
export function useRotatePoolCode() {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: rotatePoolCode,
    onSuccess: (pool) => {
      cache.setQueryData(
        ["pool", pool.id],
        (old: import("@/types/pool").ConnectionPool | undefined) =>
          old
            ? {
                ...old,
                ...pool,
                workers: old.workers,
                workerCount: old.workerCount,
                status: old.status,
              }
            : pool,
      );
      cache.invalidateQueries({ queryKey: ["pool", pool.id] });
      cache.invalidateQueries({ queryKey: ["pools"] });
      toast.success(
        "Enrollment code rotated. Existing worker credentials remain valid.",
      );
    },
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useDeletePool() {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: deletePool,
    onSuccess: async (_, id) => {
      await cache.cancelQueries({ queryKey: ["pool", id] });
      cache.removeQueries({ queryKey: ["pool", id] });
      cache.invalidateQueries({ queryKey: ["pools"] });
      toast.success("Pool deleted. Its enrollment code is revoked.");
    },
    onError: (error: Error) => toast.error(error.message),
  });
}
