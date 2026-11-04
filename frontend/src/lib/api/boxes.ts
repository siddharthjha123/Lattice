import { apiClient } from "./client";
import { Box, BoxCreationRequest } from "@/types/contracts";

export async function listBoxes(): Promise<Box[]> {
  return apiClient<Box[]>("/api/boxes");
}

export async function getBox(boxId: string): Promise<Box> {
  return apiClient<Box>(`/api/boxes/${boxId}`);
}

export async function createBox(payload: BoxCreationRequest): Promise<Box> {
  return apiClient<Box>("/api/boxes", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deleteBox(boxId: string): Promise<{
  box_id: string;
  status: string;
}> {
  return apiClient(`/api/boxes/${boxId}`, {
    method: "DELETE",
  });
}
