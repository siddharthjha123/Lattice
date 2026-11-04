import { useOperatorSession } from "@/stores/authStore";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listBoxes, getBox, createBox, deleteBox } from "@/lib/api/boxes";
import { BoxCreationRequest } from "@/types/contracts";
import { toast } from "sonner";

export function useBoxes() {
  const session = useOperatorSession();
  return useQuery({
    queryKey: ["boxes"],
    enabled: session,
    queryFn: listBoxes,
    refetchInterval: 5000,
  });
}

export function useBox(boxId?: string | null) {
  const session = useOperatorSession();
  return useQuery({
    queryKey: ["box", boxId],
    queryFn: () => getBox(boxId!),
    enabled: session && Boolean(boxId),
    refetchInterval: 4000,
  });
}

export function useCreateBox() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: BoxCreationRequest) => createBox(payload),
    onSuccess: (data) => {
      toast.success(`Box "${data.name}" created successfully.`);
      queryClient.invalidateQueries({ queryKey: ["boxes"] });
      queryClient.invalidateQueries({ queryKey: ["pools"] });
      queryClient.invalidateQueries({ queryKey: ["workers"] });
    },
    onError: (err: any) => {
      toast.error(err.message || "Failed to create box");
    },
  });
}

export function useDeleteBox() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (boxId: string) => deleteBox(boxId),
    onSuccess: (_, boxId) => {
      toast.success("Box deleted successfully.");
      queryClient.invalidateQueries({ queryKey: ["boxes"] });
      queryClient.invalidateQueries({ queryKey: ["pools"] });
      queryClient.invalidateQueries({ queryKey: ["workers"] });
      queryClient.invalidateQueries({ queryKey: ["box", boxId] });
    },
    onError: (err: any) => {
      toast.error(err.message || "Failed to delete box");
    },
  });
}
