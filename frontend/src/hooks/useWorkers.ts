import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listWorkers,
  getWorker,
  disconnectWorker,
  deleteWorker,
  fetchHealth,
} from "@/lib/api/workers";
import { useTelemetryStore } from "@/stores/telemetryStore";
import { useEffect } from "react";
import { useOperatorSession } from "@/stores/authStore";
import { getPool } from "@/lib/api/poolsAdapter";
import { toast } from "sonner";

export function useWorkers(poolId?: string) {
  const enabled = useOperatorSession();
  const ingestWorkerSnapshots = useTelemetryStore(
    (state) => state.ingestWorkerSnapshots,
  );

  const query = useQuery({
    queryKey: ["workers", poolId || "all"],
    queryFn: poolId ? async () => (await getPool(poolId)).workers : listWorkers,
    enabled,
    refetchInterval: 3000,
    retry: 2,
  });

  useEffect(() => {
    if (query.data && query.data.length > 0) {
      ingestWorkerSnapshots(query.data);
    }
  }, [query.data, ingestWorkerSnapshots]);

  return query;
}

export function useWorker(workerId?: string | null) {
  const session = useOperatorSession();
  const ingest = useTelemetryStore((state) => state.ingestWorkerSnapshots);
  const query = useQuery({
    queryKey: ["worker", workerId],
    queryFn: () => getWorker(workerId!),
    enabled: session && Boolean(workerId),
    refetchInterval: 3000,
  });
  useEffect(() => {
    if (query.data) ingest([query.data]);
  }, [query.data, ingest]);
  return query;
}

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 5000,
    retry: 1,
  });
}

export function useDisconnectWorker() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (workerId: string) => disconnectWorker(workerId),
    onSuccess: (_, workerId) => {
      toast.success(
        `Worker ${workerId} is now draining and safely disconnecting.`,
      );
      queryClient.invalidateQueries({ queryKey: ["workers"] });
      queryClient.invalidateQueries({ queryKey: ["worker", workerId] });
    },
    onError: (err: any) => {
      toast.error(err.message || "Failed to disconnect worker");
    },
  });
}

export function useDeleteWorker() {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: deleteWorker,
    onSuccess: async (_, id) => {
      await cache.cancelQueries({ queryKey: ["worker", id] });
      cache.removeQueries({ queryKey: ["worker", id] });
      useTelemetryStore.setState((state) => {
        const history = { ...state.history };
        delete history[id];
        return { history };
      });
      for (const key of ["workers", "pools", "pool"])
        cache.invalidateQueries({ queryKey: [key] });
      toast.success("Worker deleted. Its previous enrollment is revoked.");
    },
    onError: (error: Error) => toast.error(error.message),
  });
}
