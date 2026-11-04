export function formatRelativeTime(dateString?: string | null): string {
  if (!dateString) return "Never";
  try {
    const then = new Date(dateString).getTime();
    if (!Number.isFinite(then)) return "Not available";
    const now = Date.now();
    const diffSec = Math.max(0, Math.floor((now - then) / 1000));

    if (diffSec < 5) return "Just now";
    if (diffSec < 60) return `${diffSec} seconds ago`;
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHour = Math.floor(diffMin / 60);
    if (diffHour < 24) return `${diffHour}h ago`;
    const diffDay = Math.floor(diffHour / 24);
    return `${diffDay}d ago`;
  } catch {
    return dateString;
  }
}

export function formatDate(dateString?: string | null): string {
  if (!dateString) return "—";
  try {
    const d = new Date(dateString);
    return d.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  } catch {
    return dateString;
  }
}

export function formatShortDate(dateString?: string | null): string {
  if (!dateString) return "—";
  try {
    const d = new Date(dateString);
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return dateString;
  }
}

export function formatPercent(val?: number | null): string {
  if (val === null || val === undefined || isNaN(val)) return "N/A";
  return `${Math.round(val)}%`;
}

export function formatCores(cores?: number | null): string {
  if (cores === null || cores === undefined) return "Not available";
  return cores === 1 ? "1 core" : `${cores} cores`;
}

export function formatGigabytes(gb?: number | null): string {
  if (gb === null || gb === undefined) return "Not available";
  return `${gb.toFixed(1).replace(/\.0$/, "")} GiB`;
}

export function truncateHash(hash?: string | null, length: number = 7): string {
  if (!hash) return "—";
  return hash.slice(0, length);
}
