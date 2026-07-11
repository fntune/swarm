"use client";

import type { Run } from "@spawnd/api-client";
import { CostMeter } from "@spawnd/ui/components/cost-meter";
import { EmptyState } from "@spawnd/ui/components/empty-state";
import { RelativeTime } from "@spawnd/ui/components/relative-time";
import { StatusBadge } from "@spawnd/ui/components/status-badge";
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
import { RocketIcon } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { durationBetween, pollInterval, repoLabel } from "@/lib/format";
import { runsQuery } from "@/lib/queries";

const FILTERS = ["all", "running", "queued", "completed", "failed", "paused", "cancelled"] as const;

export function RunTable({ initialRuns }: { initialRuns: Run[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const filter = searchParams.get("status") ?? "all";

  const runs = useQuery({
    ...runsQuery(),
    initialData: initialRuns,
    refetchInterval: (query) => pollInterval((query.state.data ?? []).map((run) => run.status)),
  });

  const rows = (runs.data ?? []).filter((run) => {
    if (filter === "all") return true;
    if (filter === "failed") return run.status === "failed" || run.status === "cost_exceeded";
    return run.status === filter;
  });

  function setFilter(next: string) {
    const params = new URLSearchParams(searchParams);
    if (next === "all") {
      params.delete("status");
    } else {
      params.set("status", next);
    }
    router.replace(params.size > 0 ? `${pathname}?${params}` : pathname, { scroll: false });
  }

  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center gap-1.5">
        {FILTERS.map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => setFilter(value)}
            className={cn(
              "rounded-md border px-2.5 py-1 font-mono text-xs transition-colors",
              filter === value
                ? "border-primary/40 bg-accent text-accent-foreground"
                : "border-transparent text-muted-foreground hover:border-border hover:text-foreground",
            )}
          >
            {value}
          </button>
        ))}
      </div>
      {rows.length === 0 ? (
        <EmptyState
          icon={RocketIcon}
          title={filter === "all" ? "No runs yet" : `No ${filter} runs`}
          description="Submit a plan from the CLI or the New run page and it will appear here."
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <Table className="text-[13px]">
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>run</TableHead>
                <TableHead>status</TableHead>
                <TableHead>cost</TableHead>
                <TableHead>source</TableHead>
                <TableHead>created</TableHead>
                <TableHead className="text-right">duration</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((run) => (
                <TableRow key={run.run_id} className="group">
                  <TableCell className="max-w-64">
                    <Link
                      href={`/runs/${run.run_id}`}
                      className="block truncate font-medium font-mono text-foreground group-hover:text-primary"
                    >
                      {run.run_id}
                    </Link>
                    {run.name && run.name !== run.run_id ? (
                      <span className="block truncate text-muted-foreground text-xs">
                        {run.name}
                      </span>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={run.status} />
                  </TableCell>
                  <TableCell className="w-40">
                    <CostMeter compact cost={run.total_cost_usd ?? 0} budget={run.max_cost_usd} />
                  </TableCell>
                  <TableCell className="max-w-48">
                    <span className="block truncate font-mono text-muted-foreground text-xs">
                      {repoLabel(run.source_repo)}
                      {run.source_ref ? `@${run.source_ref}` : ""}
                    </span>
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-muted-foreground">
                    <RelativeTime value={run.created_at} />
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-right font-mono text-muted-foreground tabular-nums">
                    <span suppressHydrationWarning>
                      {durationBetween(run.created_at, run.finished_at) ?? "—"}
                    </span>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </section>
  );
}
