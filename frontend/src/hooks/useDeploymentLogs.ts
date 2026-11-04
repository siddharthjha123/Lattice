import { useOperatorSession } from "@/stores/authStore";
import { useQuery } from "@tanstack/react-query";
import { getDeploymentLogs } from "@/lib/api/deployments";

export function useDeploymentLogs(
  deploymentId?: string | null,
  options: { enabled?: boolean; refetchInterval?: number } = {},
) {
  const session = useOperatorSession();
  const { enabled = true, refetchInterval = 2000 } = options;

  return useQuery({
    queryKey: ["deployment-logs", deploymentId],
    queryFn: () => getDeploymentLogs(deploymentId!),
    enabled: session && Boolean(deploymentId) && enabled,
    refetchInterval,
  });
}
