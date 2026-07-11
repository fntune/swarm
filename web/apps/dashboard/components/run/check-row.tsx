"use client";

import type { Check } from "@spawnd/api-client";
import { cn } from "@spawnd/ui/lib/utils";
import { ChevronRightIcon } from "lucide-react";
import * as React from "react";

import { ArtifactText } from "@/components/artifacts/artifact-text";
import { formatDurationMs } from "@/lib/format";

export function CheckRow({
  runId,
  check,
  showAgent = false,
}: {
  runId: string;
  check: Check;
  showAgent?: boolean;
}) {
  const [open, setOpen] = React.useState(false);
  const outputIds = [check.stdout_artifact_id, check.stderr_artifact_id].filter(
    (id): id is string => Boolean(id),
  );
  if (outputIds.length === 0 && check.output_artifact_id) {
    outputIds.push(check.output_artifact_id);
  }
  const hasOutput = outputIds.length > 0;

  return (
    <div className="rounded-md border">
      <button
        type="button"
        onClick={() => hasOutput && setOpen((current) => !current)}
        className={cn(
          "flex w-full items-center gap-2 px-2.5 py-1.5 text-left",
          hasOutput && "hover:bg-muted/50",
        )}
      >
        <span
          className={cn(
            "shrink-0 rounded px-1.5 font-mono text-[11px] tabular-nums",
            check.exit_code === 0
              ? "bg-status-completed/15 text-status-completed"
              : "bg-status-failed/15 text-status-failed",
          )}
        >
          {check.exit_code === null && check.signal
            ? `sig ${check.signal}`
            : `exit ${check.exit_code ?? "?"}`}
        </span>
        {showAgent ? (
          <span className="w-28 shrink-0 truncate font-mono text-muted-foreground text-xs">
            {check.agent}
          </span>
        ) : null}
        <span className="min-w-0 flex-1 truncate font-mono text-xs">
          {check.command_preview ?? "—"}
        </span>
        <span className="shrink-0 font-mono text-[11px] text-muted-foreground tabular-nums">
          {check.duration_ms != null ? formatDurationMs(check.duration_ms) : ""}
        </span>
        {hasOutput ? (
          <ChevronRightIcon
            className={cn(
              "size-3 shrink-0 text-muted-foreground transition-transform",
              open && "rotate-90",
            )}
          />
        ) : null}
      </button>
      {open ? (
        <div className="flex flex-col gap-2 border-t p-2">
          {outputIds.map((artifactId) => (
            <ArtifactText key={artifactId} runId={runId} artifactId={artifactId} maxHeight={280} />
          ))}
        </div>
      ) : null}
    </div>
  );
}
