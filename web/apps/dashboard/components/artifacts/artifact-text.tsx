"use client";

import { Skeleton } from "@spawnd/ui/components/ui/skeleton";
import { useQuery } from "@tanstack/react-query";

import { artifactContentQuery } from "@/lib/artifact-content";
import { AnsiLogPane } from "./ansi-log-pane";

export function ArtifactText({
  runId,
  artifactId,
  maxHeight = 320,
}: {
  runId: string;
  artifactId: string;
  maxHeight?: number;
}) {
  const content = useQuery(artifactContentQuery(runId, artifactId));

  if (content.isPending) {
    return <Skeleton className="h-24 w-full" />;
  }
  if (content.isError) {
    return (
      <p className="rounded-md border border-dashed px-3 py-2 text-muted-foreground text-xs">
        {content.error.message}
      </p>
    );
  }
  return (
    <AnsiLogPane
      text={content.data.text}
      redactionPolicy={content.data.redactionPolicy}
      maxHeight={maxHeight}
    />
  );
}
