"use client";

import type { WorkersSnapshot } from "@spawnd/api-client";
import { AnimatedNumber } from "@spawnd/ui/components/animated-number";
import { EmptyState } from "@spawnd/ui/components/empty-state";
import { RelativeTime } from "@spawnd/ui/components/relative-time";
import { Card, CardContent } from "@spawnd/ui/components/ui/card";
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
import { ServerOffIcon } from "lucide-react";

import { workersQuery } from "@/lib/queries";

function QueueStat({ label, value }: { label: string; value: number }) {
  return (
    <Card className="flex-1 py-4">
      <CardContent className="flex flex-col gap-1 px-4">
        <span className="font-mono text-[11px] text-muted-foreground uppercase tracking-wider">
          {label}
        </span>
        <span className="font-mono text-2xl tabular-nums">
          <AnimatedNumber value={value} />
        </span>
      </CardContent>
    </Card>
  );
}

export function WorkerTable({ initialWorkers }: { initialWorkers: WorkersSnapshot }) {
  const workers = useQuery({
    ...workersQuery(),
    initialData: initialWorkers,
    refetchInterval: 10_000,
  });

  const snapshot = workers.data;
  const rows = snapshot?.workers ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap gap-3">
        <QueueStat label="ready-agent queue" value={snapshot?.queue_depth ?? 0} />
        <QueueStat label="submission queue" value={snapshot?.submission_queue_depth ?? 0} />
        <QueueStat label="worker nodes" value={rows.length} />
      </div>
      {rows.length === 0 ? (
        <EmptyState
          icon={ServerOffIcon}
          title="No workers registered"
          description="Start a spawnd worker pointed at this backend and its heartbeat will appear here."
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <Table className="text-[13px]">
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>worker</TableHead>
                <TableHead>hostname</TableHead>
                <TableHead>status</TableHead>
                <TableHead>heartbeat</TableHead>
                <TableHead>started</TableHead>
                <TableHead className="text-right">capacity</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((worker) => (
                <TableRow key={worker.worker_id} className={cn(worker.stale && "opacity-70")}>
                  <TableCell className="font-mono">{worker.worker_id}</TableCell>
                  <TableCell className="font-mono text-muted-foreground text-xs">
                    {worker.hostname ?? "—"}
                  </TableCell>
                  <TableCell>
                    <span
                      className={cn(
                        "inline-flex items-center gap-1.5 rounded-md border bg-card px-2 py-0.5 font-mono text-xs",
                        worker.stale ? "text-status-failed" : "text-foreground",
                      )}
                    >
                      <span
                        aria-hidden="true"
                        className={cn(
                          "size-2 rounded-full",
                          worker.stale ? "bg-status-failed" : "bg-status-completed",
                        )}
                      />
                      {worker.stale ? "stale" : worker.status}
                    </span>
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-muted-foreground">
                    <RelativeTime value={worker.heartbeat_at} refreshSeconds={10} />
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-muted-foreground">
                    <RelativeTime value={worker.started_at} />
                  </TableCell>
                  <TableCell className="text-right font-mono text-muted-foreground text-xs">
                    {worker.capacity ? JSON.stringify(worker.capacity) : "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
