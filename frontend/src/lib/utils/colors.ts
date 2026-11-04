/**
 * Color utilities and threshold calculation adhering to Lattice specifications:
 * Utilization: 0–60% healthy (#72B0AB/#BCDDDC), 61–80% yellow, 81–100% red
 * Health: 80–100% healthy (#72B0AB/#BCDDDC), 50–79% yellow, 0–49% red
 * Battery: 20–100% healthy (#72B0AB/#BCDDDC), 10–19% yellow, 0–9% red
 */

export function getUtilizationColor(percentage: number | null): {
  color: string;
  twText: string;
  twBg: string;
} {
  if (percentage === null || percentage === undefined) {
    return { color: "#71717a", twText: "text-zinc-400", twBg: "bg-zinc-700" };
  }
  if (percentage <= 60) {
    return {
      color: "#72B0AB",
      twText: "text-emerald-400",
      twBg: "bg-emerald-500",
    };
  }
  if (percentage <= 80) {
    return { color: "#f59e0b", twText: "text-amber-400", twBg: "bg-amber-500" };
  }
  return { color: "#ef4444", twText: "text-rose-400", twBg: "bg-rose-500" };
}

export function getHealthColor(score: number | null): {
  color: string;
  twText: string;
  twBg: string;
} {
  if (score === null || score === undefined) {
    return { color: "#71717a", twText: "text-zinc-400", twBg: "bg-zinc-700" };
  }
  if (score >= 80) {
    return {
      color: "#72B0AB",
      twText: "text-emerald-400",
      twBg: "bg-emerald-500",
    };
  }
  if (score >= 50) {
    return { color: "#f59e0b", twText: "text-amber-400", twBg: "bg-amber-500" };
  }
  return { color: "#ef4444", twText: "text-rose-400", twBg: "bg-rose-500" };
}

export function getBatteryColor(percentage: number | null): {
  color: string;
  twText: string;
  twBg: string;
} {
  if (percentage === null || percentage === undefined) {
    return { color: "#71717a", twText: "text-zinc-500", twBg: "bg-zinc-700" };
  }
  if (percentage >= 20) {
    return {
      color: "#72B0AB",
      twText: "text-emerald-400",
      twBg: "bg-emerald-500",
    };
  }
  if (percentage >= 10) {
    return { color: "#f59e0b", twText: "text-amber-400", twBg: "bg-amber-500" };
  }
  return { color: "#ef4444", twText: "text-rose-400", twBg: "bg-rose-500" };
}

// Palette of visually distinct, high-contrast colors on dark backgrounds for multi-worker graphs
export const WORKER_PALETTE = [
  "#38bdf8", // Sky blue
  "#72B0AB", // Teal / Sage
  "#f472b6", // Pink
  "#fbbf24", // Amber
  "#a78bfa", // Purple
  "#22d3ee", // Cyan
  "#f87171", // Rose
  "#818cf8", // Indigo
  "#BCDDDC", // Soft mint / Light sage
  "#fb923c", // Orange
];

export function getWorkerColor(index: number): string {
  return WORKER_PALETTE[index % WORKER_PALETTE.length];
}
