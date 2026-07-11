import { createSpawndClient, type SpawndClient } from "@spawnd/api-client";
import { queryOptions } from "@tanstack/react-query";

let cached: SpawndClient | null = null;

/** Browser-side client; every request flows through the authenticated Next.js proxy. */
export function browserClient(): SpawndClient {
  if (!cached) {
    cached = createSpawndClient({
      baseUrl: new URL("/api/spawnd", window.location.origin).toString(),
    });
  }
  return cached;
}

export const workersQuery = () =>
  queryOptions({
    queryKey: ["workers"],
    queryFn: () => browserClient().workers.get(),
  });

export const runsQuery = (limit = 100) =>
  queryOptions({
    queryKey: ["runs", limit],
    queryFn: () => browserClient().runs.list({ limit }),
  });

export const runQuery = (runId: string) =>
  queryOptions({
    queryKey: ["run", runId],
    queryFn: () => browserClient().runs.get(runId),
  });

export const runEventsQuery = (runId: string, limit = 200) =>
  queryOptions({
    queryKey: ["run", runId, "events", limit],
    queryFn: () => browserClient().runs.events(runId, { limit }),
  });

export const runChecksQuery = (runId: string) =>
  queryOptions({
    queryKey: ["run", runId, "checks"],
    queryFn: () => browserClient().runs.checks(runId),
  });

export const runArtifactsQuery = (runId: string) =>
  queryOptions({
    queryKey: ["run", runId, "artifacts"],
    queryFn: () => browserClient().runs.artifacts(runId),
  });

export const runUsageQuery = (runId: string) =>
  queryOptions({
    queryKey: ["run", runId, "usage"],
    queryFn: () => browserClient().runs.usage(runId),
  });

export const runProvenanceQuery = (runId: string) =>
  queryOptions({
    queryKey: ["run", runId, "provenance"],
    queryFn: () => browserClient().runs.provenance(runId),
  });

export const runTracesQuery = (runId: string) =>
  queryOptions({
    queryKey: ["run", runId, "traces"],
    queryFn: () => browserClient().runs.traces(runId),
  });

export const templatesQuery = () =>
  queryOptions({
    queryKey: ["templates"],
    queryFn: () => browserClient().templates.list(),
  });

export const schedulesQuery = () =>
  queryOptions({
    queryKey: ["schedules"],
    queryFn: () => browserClient().schedules.list(),
  });

export const clarificationsQuery = () =>
  queryOptions({
    queryKey: ["clarifications"],
    queryFn: () => browserClient().clarifications.list(),
  });
