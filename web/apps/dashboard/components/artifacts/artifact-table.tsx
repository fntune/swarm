"use client";

import type { Artifact } from "@spawnd/api-client";
import { EmptyState } from "@spawnd/ui/components/empty-state";
import { RelativeTime } from "@spawnd/ui/components/relative-time";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@spawnd/ui/components/ui/table";
import { cn } from "@spawnd/ui/lib/utils";
import { useQuery } from "@tanstack/react-query";
import { PackageOpenIcon } from "lucide-react";
import * as React from "react";

import { runArtifactsQuery } from "@/lib/queries";
import { ArtifactViewerDialog } from "./artifact-viewer-dialog";

export function ArtifactTable({
  runId,
  initialArtifacts,
}: {
  runId: string;
  initialArtifacts: Artifact[];
}) {
  const [selected, setSelected] = React.useState<Artifact | null>(null);
  const artifacts = useQuery({
    ...runArtifactsQuery(runId),
    initialData: initialArtifacts,
    refetchInterval: 10_000,
  });

  const rows = artifacts.data ?? [];
  if (rows.length === 0) {
    return (
      <EmptyState
        icon={PackageOpenIcon}
        title="No artifacts stored"
        description="Redacted runtime output, final messages, patches, and check output land here."
      />
    );
  }

  return (
    <>
      <div className="overflow-x-auto rounded-lg border">
        <Table className="text-[13px]">
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>kind</TableHead>
              <TableHead>agent</TableHead>
              <TableHead>type</TableHead>
              <TableHead className="text-right">size</TableHead>
              <TableHead>redaction</TableHead>
              <TableHead>created</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((artifact) => (
              <TableRow
                key={artifact.id}
                onClick={() => setSelected(artifact)}
                className="cursor-pointer"
              >
                <TableCell>
                  <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
                    {artifact.kind}
                  </span>
                </TableCell>
                <TableCell className="font-mono text-xs">{artifact.agent ?? "_system"}</TableCell>
                <TableCell className="font-mono text-muted-foreground text-xs">
                  {artifact.content_type ?? "—"}
                </TableCell>
                <TableCell className="text-right font-mono text-muted-foreground text-xs tabular-nums">
                  {artifact.size_bytes != null ? artifact.size_bytes.toLocaleString() : "—"}
                </TableCell>
                <TableCell>
                  <span
                    className={cn(
                      "font-mono text-xs",
                      artifact.redaction_policy === "raw"
                        ? "text-status-running"
                        : "text-muted-foreground",
                    )}
                  >
                    {artifact.redaction_policy ?? "—"}
                  </span>
                </TableCell>
                <TableCell className="whitespace-nowrap text-muted-foreground">
                  <RelativeTime value={artifact.created_at} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <ArtifactViewerDialog artifact={selected} onClose={() => setSelected(null)} />
    </>
  );
}
