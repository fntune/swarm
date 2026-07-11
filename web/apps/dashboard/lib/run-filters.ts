import type { RunStatus } from "@spawnd/api-client";

export const RUN_FILTERS = [
  "all",
  "running",
  "queued",
  "completed",
  "failed",
  "paused",
  "cancelled",
] as const;

export type RunFilter = (typeof RUN_FILTERS)[number];

export function parseRunFilter(value: string | null): RunFilter {
  return RUN_FILTERS.find((candidate) => candidate === value) ?? "all";
}

export function statusesForRunFilter(filter: RunFilter): RunStatus[] | undefined {
  if (filter === "all") return undefined;
  if (filter === "failed") return ["failed", "cost_exceeded"];
  return [filter];
}
