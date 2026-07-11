"use client";

import type { Artifact } from "@spawnd/api-client";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@spawnd/ui/components/ui/dialog";
import { Skeleton } from "@spawnd/ui/components/ui/skeleton";
import { useQuery } from "@tanstack/react-query";
import { DownloadIcon } from "lucide-react";

import { artifactContentQuery } from "@/lib/artifact-content";
import { AnsiLogPane } from "./ansi-log-pane";
import { DiffViewer } from "./diff-viewer";

const MAX_INLINE_BYTES = 1_000_000;

function isDiffArtifact(artifact: Artifact): boolean {
  return (
    artifact.kind === "patch" ||
    artifact.kind === "diff" ||
    (artifact.content_type ?? "").includes("x-diff") ||
    (artifact.content_type ?? "").includes("x-patch")
  );
}

function Viewer({ artifact }: { artifact: Artifact }) {
  const content = useQuery(artifactContentQuery(artifact.run_id, artifact.id));

  if (content.isPending) {
    return <Skeleton className="h-48 w-full" />;
  }
  if (content.isError) {
    return (
      <p className="rounded-md border border-dashed px-3 py-4 text-muted-foreground text-sm">
        {content.error.message}
      </p>
    );
  }
  if (isDiffArtifact(artifact)) {
    return <DiffViewer patch={content.data.text} />;
  }
  return (
    <AnsiLogPane
      text={content.data.text}
      redactionPolicy={content.data.redactionPolicy}
      maxHeight={520}
    />
  );
}

export function ArtifactViewerDialog({
  artifact,
  onClose,
}: {
  artifact: Artifact | null;
  onClose: () => void;
}) {
  const tooLarge = (artifact?.size_bytes ?? 0) > MAX_INLINE_BYTES;
  const downloadHref = artifact
    ? `/api/spawnd/runs/${encodeURIComponent(artifact.run_id)}/artifacts/${encodeURIComponent(artifact.id)}/download`
    : "#";

  return (
    <Dialog open={artifact !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="flex max-h-[85vh] flex-col sm:max-w-4xl">
        {artifact ? (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2 font-mono text-sm">
                <span className="rounded bg-muted px-1.5 py-0.5 text-xs">{artifact.kind}</span>
                <span className="truncate">{artifact.agent ?? "_system"}</span>
              </DialogTitle>
              <DialogDescription className="flex items-center gap-3 font-mono text-xs">
                <span>{artifact.content_type ?? "unknown type"}</span>
                <span>{artifact.size_bytes != null ? `${artifact.size_bytes}b` : ""}</span>
                <span>{artifact.redaction_policy === "raw" ? "raw capture" : "redacted"}</span>
                <a
                  href={downloadHref}
                  download
                  className="ml-auto inline-flex items-center gap-1 text-primary hover:underline"
                >
                  <DownloadIcon className="size-3" />
                  download
                </a>
              </DialogDescription>
            </DialogHeader>
            <div className="min-h-0 flex-1 overflow-y-auto">
              {tooLarge ? (
                <p className="rounded-md border border-dashed px-3 py-6 text-center text-muted-foreground text-sm">
                  This artifact is larger than 1 MB — use the download link instead of inline
                  viewing.
                </p>
              ) : (
                <Viewer artifact={artifact} />
              )}
            </div>
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
