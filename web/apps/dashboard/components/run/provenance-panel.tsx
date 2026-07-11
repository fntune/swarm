"use client";

import type { GitProvenance } from "@spawnd/api-client";
import { CopyButton } from "@spawnd/ui/components/copy-button";
import { EmptyState } from "@spawnd/ui/components/empty-state";
import { Card, CardContent, CardHeader, CardTitle } from "@spawnd/ui/components/ui/card";
import { useQuery } from "@tanstack/react-query";
import { ExternalLinkIcon, GitBranchIcon } from "lucide-react";

import { shortSha } from "@/lib/format";
import { runProvenanceQuery } from "@/lib/queries";

function ShaField({ label, sha }: { label: string; sha: string | null }) {
  return (
    <div className="flex items-center gap-1 font-mono text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span>{shortSha(sha)}</span>
      {sha ? <CopyButton value={sha} className="size-5" /> : null}
    </div>
  );
}

export function ProvenancePanel({
  runId,
  initialProvenance,
}: {
  runId: string;
  initialProvenance: GitProvenance[];
}) {
  const provenance = useQuery({
    ...runProvenanceQuery(runId),
    initialData: initialProvenance,
    refetchInterval: 15_000,
  });

  const rows = provenance.data ?? [];
  if (rows.length === 0) {
    return (
      <EmptyState
        icon={GitBranchIcon}
        title="No git provenance"
        description="Branches, commits, and diff stats recorded by workers will appear here."
      />
    );
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {rows.map((row) => {
        const diffStats =
          row.diff_stats && typeof row.diff_stats === "object"
            ? Object.entries(row.diff_stats as Record<string, unknown>)
            : [];
        return (
          <Card key={row.id}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 font-mono text-sm">
                <span className="truncate">{row.agent}</span>
                {row.pr_url ? (
                  <a
                    href={row.pr_url}
                    target="_blank"
                    rel="noreferrer"
                    className="ml-auto inline-flex items-center gap-1 text-primary text-xs hover:underline"
                  >
                    PR {row.pr_number ? `#${row.pr_number}` : ""}
                    <ExternalLinkIcon className="size-3" />
                  </a>
                ) : null}
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              {row.branch ? (
                <div className="flex items-center gap-1 font-mono text-xs">
                  <GitBranchIcon className="size-3 text-muted-foreground" />
                  <span className="truncate">{row.branch}</span>
                  <CopyButton value={row.branch} className="size-5" />
                </div>
              ) : null}
              <div className="flex flex-wrap gap-x-4 gap-y-1">
                <ShaField label="base" sha={row.base_sha} />
                <ShaField label="head" sha={row.head_sha} />
                {row.commit_sha ? <ShaField label="commit" sha={row.commit_sha} /> : null}
              </div>
              {row.commit_message_preview ? (
                <p className="rounded-md bg-muted/50 px-2.5 py-1.5 font-mono text-muted-foreground text-xs">
                  {row.commit_message_preview}
                </p>
              ) : null}
              <div className="flex items-center gap-3 font-mono text-xs tabular-nums">
                <span className="text-muted-foreground">
                  {row.changed_files_count ?? 0} file{row.changed_files_count === 1 ? "" : "s"}
                </span>
                <span className="text-status-completed">+{row.insertions_count ?? 0}</span>
                <span className="text-status-failed">−{row.deletions_count ?? 0}</span>
              </div>
              {diffStats.length > 0 ? (
                <dl className="flex flex-col gap-0.5 border-t pt-2 font-mono text-[11px]">
                  {diffStats.slice(0, 20).map(([file, stat]) => (
                    <div key={file} className="flex justify-between gap-3">
                      <dt className="truncate text-muted-foreground">{file}</dt>
                      <dd className="shrink-0 tabular-nums">{String(stat)}</dd>
                    </div>
                  ))}
                </dl>
              ) : null}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
