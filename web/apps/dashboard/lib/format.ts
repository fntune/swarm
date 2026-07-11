export function formatUsd(amount: number): string {
  return `$${amount.toFixed(2)}`;
}

export function formatTokens(count: number): string {
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(1)}M`;
  if (count >= 1_000) return `${(count / 1_000).toFixed(1)}k`;
  return String(count);
}

export function formatDurationMs(ms: number): string {
  if (ms < 1_000) return `${Math.round(ms)}ms`;
  const seconds = ms / 1_000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  if (minutes < 60) return `${minutes}m ${rest}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

export function durationBetween(
  start: string | null | undefined,
  end: string | null | undefined,
): string | null {
  if (!start) return null;
  const startMs = Date.parse(start);
  const endMs = end ? Date.parse(end) : Date.now();
  if (Number.isNaN(startMs) || Number.isNaN(endMs) || endMs < startMs) return null;
  return formatDurationMs(endMs - startMs);
}

/** Compact repo label: strips scheme/credentials, keeps host/path tail. */
export function repoLabel(sourceRepo: string | null | undefined): string {
  if (!sourceRepo) return "—";
  const withoutScheme = sourceRepo.replace(/^[a-z+]+:\/\//i, "").replace(/^.*@/, "");
  const trimmed = withoutScheme.replace(/\.git$/, "").replace(/\/+$/, "");
  const segments = trimmed.split("/");
  if (segments.length <= 3) return trimmed;
  return `…/${segments.slice(-2).join("/")}`;
}

export function shortSha(sha: string | null | undefined): string {
  return sha ? sha.slice(0, 8) : "—";
}

const ACTIVE_RUN_STATUSES = new Set(["queued", "running"]);

export function runIsActive(status: string): boolean {
  return ACTIVE_RUN_STATUSES.has(status);
}

export function runIsCancellable(status: string): boolean {
  return runIsActive(status) || status === "paused";
}

export function pollInterval(statuses: string[]): number {
  return statuses.some((status) => runIsActive(status)) ? 5_000 : 30_000;
}
