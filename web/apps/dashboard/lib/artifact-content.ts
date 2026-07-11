import { queryOptions } from "@tanstack/react-query";

export interface ArtifactContent {
  text: string;
  redactionPolicy: string | null;
  contentType: string | null;
}

export async function fetchArtifactContent(
  runId: string,
  artifactId: string,
): Promise<ArtifactContent> {
  const response = await fetch(
    `/api/spawnd/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(artifactId)}/content`,
  );
  if (!response.ok) {
    throw new Error(
      response.status === 413
        ? "Artifact is too large to view inline"
        : `Failed to load artifact (status ${response.status})`,
    );
  }
  return {
    text: await response.text(),
    redactionPolicy: response.headers.get("x-spawnd-redaction-policy"),
    contentType: response.headers.get("content-type"),
  };
}

/** Artifact objects are immutable; cache forever. */
export const artifactContentQuery = (runId: string, artifactId: string) =>
  queryOptions({
    queryKey: ["artifact-content", runId, artifactId],
    queryFn: () => fetchArtifactContent(runId, artifactId),
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: 10 * 60 * 1000,
    retry: 1,
  });
