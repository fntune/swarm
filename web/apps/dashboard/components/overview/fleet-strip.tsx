"use client";

import type { Run, WorkersSnapshot } from "@spawnd/api-client";
import { AnimatedNumber } from "@spawnd/ui/components/animated-number";
import { Card, CardContent } from "@spawnd/ui/components/ui/card";
import { cn } from "@spawnd/ui/lib/utils";
import { useQuery } from "@tanstack/react-query";

import { formatUsd, pollInterval, runIsActive } from "@/lib/format";
import { runsQuery, workersQuery } from "@/lib/queries";

function Stat({
  label,
  value,
  detail,
  alert = false,
}: {
  label: string;
  value: React.ReactNode;
  detail?: string;
  alert?: boolean;
}) {
  return (
    <Card className="flex-1 py-4">
      <CardContent className="flex flex-col gap-1 px-4">
        <span className="font-mono text-[11px] text-muted-foreground uppercase tracking-wider">
          {label}
        </span>
        <span
          className={cn(
            "font-mono text-2xl tabular-nums",
            alert ? "text-status-failed" : "text-foreground",
          )}
        >
          {value}
        </span>
        {detail ? <span className="text-muted-foreground text-xs">{detail}</span> : null}
      </CardContent>
    </Card>
  );
}

export function FleetStrip({
  initialWorkers,
  initialRuns,
}: {
  initialWorkers: WorkersSnapshot;
  initialRuns: Run[];
}) {
  const runs = useQuery({
    ...runsQuery(),
    initialData: initialRuns,
    refetchInterval: (query) => pollInterval((query.state.data ?? []).map((run) => run.status)),
  });
  const workers = useQuery({
    ...workersQuery(),
    initialData: initialWorkers,
    refetchInterval: 10_000,
  });

  const runRows = runs.data ?? [];
  const snapshot = workers.data;
  const activeRuns = runRows.filter((run) => runIsActive(run.status)).length;
  const staleWorkers = (snapshot?.workers ?? []).filter((worker) => worker.stale).length;
  const dayAgo = Date.now() - 24 * 60 * 60 * 1000;
  const daySpend = runRows
    .filter((run) => Date.parse(run.created_at) >= dayAgo)
    .reduce((sum, run) => sum + (run.total_cost_usd ?? 0), 0);

  return (
    <div className="flex flex-wrap gap-3">
      <Stat
        label="active runs"
        value={<AnimatedNumber value={activeRuns} />}
        detail={`${runRows.length} loaded`}
      />
      <Stat
        label="queue depth"
        value={<AnimatedNumber value={snapshot?.queue_depth ?? 0} />}
        detail={`${snapshot?.submission_queue_depth ?? 0} submissions queued`}
      />
      <Stat
        label="workers"
        value={<AnimatedNumber value={snapshot?.workers.length ?? 0} />}
        detail={staleWorkers > 0 ? `${staleWorkers} stale` : "all heartbeats fresh"}
        alert={staleWorkers > 0}
      />
      <Stat
        label="24h spend"
        value={<AnimatedNumber value={daySpend} format={formatUsd} />}
        detail="sum of run totals"
      />
    </div>
  );
}
