"use client";

import type { TraceSpan } from "@spawnd/api-client";
import { EmptyState } from "@spawnd/ui/components/empty-state";
import { cn } from "@spawnd/ui/lib/utils";
import { useQuery } from "@tanstack/react-query";
import { ActivityIcon } from "lucide-react";

import { formatDurationMs } from "@/lib/format";
import { runTracesQuery } from "@/lib/queries";

const MAX_SPANS = 500;

export function TracesPanel({
  runId,
  initialTraces,
}: {
  runId: string;
  initialTraces: TraceSpan[];
}) {
  const traces = useQuery({
    ...runTracesQuery(runId),
    initialData: initialTraces,
    refetchInterval: 15_000,
  });

  const spans = (traces.data ?? []).slice(0, MAX_SPANS);
  if (spans.length === 0) {
    return (
      <EmptyState
        icon={ActivityIcon}
        title="No trace spans mirrored"
        description="Enable orchestration.telemetry in the plan to mirror redacted OTel spans into Postgres."
      />
    );
  }

  const starts = spans.map((span) => Date.parse(span.started_at)).filter((t) => !Number.isNaN(t));
  const minStart = Math.min(...starts);
  const maxEnd = Math.max(
    ...spans.map((span) =>
      span.ended_at ? Date.parse(span.ended_at) : Date.parse(span.started_at),
    ),
  );
  const window = Math.max(maxEnd - minStart, 1);

  return (
    <div className="flex flex-col gap-3">
      {(traces.data?.length ?? 0) > MAX_SPANS ? (
        <p className="font-mono text-muted-foreground text-xs">
          Showing first {MAX_SPANS} of {traces.data?.length} spans.
        </p>
      ) : null}
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="border-b text-left font-mono text-muted-foreground text-xs">
              <th className="px-3 py-2 font-normal">span</th>
              <th className="px-3 py-2 font-normal">agent</th>
              <th className="px-3 py-2 font-normal">status</th>
              <th className="w-32 px-3 py-2 text-right font-normal">duration</th>
              <th className="w-[35%] px-3 py-2 font-normal">timeline</th>
            </tr>
          </thead>
          <tbody>
            {spans.map((span) => {
              const start = Date.parse(span.started_at);
              const duration =
                span.duration_ms ?? (span.ended_at ? Date.parse(span.ended_at) - start : 0);
              const offsetPct = Number.isNaN(start) ? 0 : ((start - minStart) / window) * 100;
              const widthPct = Math.max((duration / window) * 100, 0.5);
              const failed = (span.status ?? "").toLowerCase() === "error";
              return (
                <tr key={span.id} className="border-b last:border-0 hover:bg-muted/40">
                  <td className="max-w-64 truncate px-3 py-1.5 font-mono text-xs">{span.name}</td>
                  <td className="px-3 py-1.5 font-mono text-muted-foreground text-xs">
                    {span.agent ?? "—"}
                  </td>
                  <td
                    className={cn(
                      "px-3 py-1.5 font-mono text-xs",
                      failed ? "text-status-failed" : "text-muted-foreground",
                    )}
                  >
                    {span.status ?? "—"}
                  </td>
                  <td className="px-3 py-1.5 text-right font-mono text-muted-foreground text-xs tabular-nums">
                    {formatDurationMs(duration)}
                  </td>
                  <td className="px-3 py-1.5">
                    <div className="relative h-3 w-full rounded-sm bg-muted">
                      <div
                        className={cn(
                          "absolute top-0 h-full rounded-sm",
                          failed ? "bg-status-failed/70" : "bg-primary/60",
                        )}
                        style={{
                          left: `${offsetPct}%`,
                          width: `${Math.min(widthPct, 100 - offsetPct)}%`,
                        }}
                      />
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
