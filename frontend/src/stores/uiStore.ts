import { create } from "zustand";

interface UiState {
  isDownloadModalOpen: boolean;
  isCreatePoolModalOpen: boolean;
  activeWorkerDetailId: string | null;
  isAggregateModalOpen: boolean;
  aggregateMetricType: "cpu" | "memory" | "battery" | "health";

  openDownloadModal: () => void;
  closeDownloadModal: () => void;
  openCreatePoolModal: () => void;
  closeCreatePoolModal: () => void;
  openWorkerDetail: (workerId: string) => void;
  closeWorkerDetail: () => void;
  openAggregateModal: (metric: "cpu" | "memory" | "battery" | "health") => void;
  closeAggregateModal: () => void;
}

export const useUiStore = create<UiState>((set) => ({
  isDownloadModalOpen: false,
  isCreatePoolModalOpen: false,
  activeWorkerDetailId: null,
  isAggregateModalOpen: false,
  aggregateMetricType: "cpu",

  openDownloadModal: () => set({ isDownloadModalOpen: true }),
  closeDownloadModal: () => set({ isDownloadModalOpen: false }),
  openCreatePoolModal: () => set({ isCreatePoolModalOpen: true }),
  closeCreatePoolModal: () => set({ isCreatePoolModalOpen: false }),
  openWorkerDetail: (workerId) => set({ activeWorkerDetailId: workerId }),
  closeWorkerDetail: () => set({ activeWorkerDetailId: null }),
  openAggregateModal: (metric) =>
    set({ isAggregateModalOpen: true, aggregateMetricType: metric }),
  closeAggregateModal: () => set({ isAggregateModalOpen: false }),
}));
