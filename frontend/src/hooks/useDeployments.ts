import { useOperatorSession } from "@/stores/authStore";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listDeployments,
  getDeployment,
  getDeploymentStatus,
  createDeployment,
  stopDeployment,
  redeployDeployment,
} from "@/lib/api/deployments";
import { DeploymentCreateRequest } from "@/types/contracts";
import { toast } from "sonner";
import { useRouter } from "next/navigation";

export function useDeployments() {
  const session = useOperatorSession();
  return useQuery({
    queryKey: ["deployments"],
    enabled: session,
    queryFn: listDeployments,
    refetchInterval: 4000,
  });
}

export function useDeployment(deploymentId?: string | null) {
  const session = useOperatorSession();
  return useQuery({
    queryKey: ["deployment", deploymentId],
    queryFn: () => getDeployment(deploymentId!),
    enabled: session && Boolean(deploymentId),
    refetchInterval: 3000,
  });
}

export function useDeploymentStatus(deploymentId?: string | null) {
  const session = useOperatorSession();
  return useQuery({
    queryKey: ["deployment-status", deploymentId],
    queryFn: () => getDeploymentStatus(deploymentId!),
    enabled: session && Boolean(deploymentId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      // Fast polling during build/deployment stages, slower when terminal
      if (
        status === "building" ||
        status === "deploying" ||
        status === "queued"
      ) {
        return 1500;
      }
      return 5000;
    },
  });
}

export function useCreateDeployment() {
  const queryClient = useQueryClient();
  const router = useRouter();

  return useMutation({
    mutationFn: (payload: DeploymentCreateRequest) => createDeployment(payload),
    onSuccess: (data) => {
      toast.success("Deployment queued successfully!");
      queryClient.invalidateQueries({ queryKey: ["deployments"] });
      router.push(`/deployments/${data.deployment_id}`);
    },
    onError: (err: any) => {
      toast.error(err.message || "Failed to start deployment");
    },
  });
}

export function useStopDeployment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (deploymentId: string) => stopDeployment(deploymentId),
    onSuccess: (res, deploymentId) => {
      toast.success(
        res.status === "stopped"
          ? "Deployment stopped successfully."
          : "Stop initiated. Workload is fencing safely.",
      );
      queryClient.invalidateQueries({ queryKey: ["deployments"] });
      queryClient.invalidateQueries({ queryKey: ["deployment", deploymentId] });
      queryClient.invalidateQueries({
        queryKey: ["deployment-status", deploymentId],
      });
    },
    onError: (err: any) => {
      toast.error(err.message || "Failed to stop deployment");
    },
  });
}

export function useRedeployDeployment() {
  const queryClient = useQueryClient();
  const router = useRouter();

  return useMutation({
    mutationFn: (deploymentId: string) => redeployDeployment(deploymentId),
    onSuccess: (data) => {
      toast.success("New deployment queued from previous configuration!");
      queryClient.invalidateQueries({ queryKey: ["deployments"] });
      router.push(`/deployments/${data.deployment_id}`);
    },
    onError: (err: any) => {
      toast.error(err.message || "Redeploy failed");
    },
  });
}
