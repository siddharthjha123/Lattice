import { useState, useRef } from "react";
import { inspectRepository } from "@/lib/api/repoInspectionAdapter";
import { RepositoryInspection } from "@/types/repository";
import { toast } from "sonner";

export function useRepositoryInspection() {
  const requestId = useRef(0);
  const [data, setData] = useState<RepositoryInspection | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const inspect = async (repoUrl: string, branch?: string) => {
    const identity = ++requestId.current;
    setData(null);
    setIsLoading(true);
    setError(null);
    try {
      const result = await inspectRepository(repoUrl, branch);
      if (identity === requestId.current) setData(result);
      return result;
    } catch (err: any) {
      const msg = err.message || "Failed to inspect repository";
      if (identity === requestId.current) setError(msg);
      toast.error(msg);
      throw err;
    } finally {
      if (identity === requestId.current) setIsLoading(false);
    }
  };

  const reset = () => {
    setData(null);
    setError(null);
    setIsLoading(false);
  };

  return {
    data,
    isLoading,
    error,
    inspect,
    reset,
  };
}
