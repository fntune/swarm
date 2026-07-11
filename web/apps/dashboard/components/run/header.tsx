"use client";

import type { RunDetail } from "@spawnd/api-client";
import { CopyButton } from "@spawnd/ui/components/copy-button";
import { CostMeter } from "@spawnd/ui/components/cost-meter";
import { StatusBadge } from "@spawnd/ui/components/status-badge";
import { Button } from "@spawnd/ui/components/ui/button";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2Icon, OctagonXIcon, RotateCcwIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { pollInterval, repoLabel, runIsCancellable } from "@/lib/format";
import { browserClient, runQuery } from "@/lib/queries";
import { LiveDuration } from "./live-duration";

export function RunHeader({ runId, initialDetail }: { runId: string; initialDetail: RunDetail }) {
  const queryClient = useQueryClient();
  const detail = useQuery({
    ...runQuery(runId),
    initialData: initialDetail,
    refetchInterval: (query) => {
      const status = query.state.data?.run.status;
      return status ? pollInterval([status]) : 30_000;
    },
  });
  const [confirmingCancel, setConfirmingCancel] = React.useState(false);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["run", runId] });
    queryClient.invalidateQueries({ queryKey: ["runs"] });
  };

  const cancel = useMutation({
    mutationFn: () => browserClient().runs.cancel(runId),
    onSuccess: (result) => {
      toast.success(`Cancelled ${result.cancelled} agent${result.cancelled === 1 ? "" : "s"}`);
      invalidate();
    },
    onError: (error: Error) => toast.error(error.message),
    onSettled: () => setConfirmingCancel(false),
  });

  const resume = useMutation({
    mutationFn: () => browserClient().runs.resume(runId),
    onSuccess: (resumed) => {
      toast.success(
        resumed.length > 0
          ? `Resumed ${resumed.length} agent${resumed.length === 1 ? "" : "s"}`
          : "Nothing to resume",
      );
      invalidate();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const run = detail.data?.run ?? initialDetail.run;
  const cancellable = runIsCancellable(run.status);
  const resumable = run.status === "paused" || run.status === "failed";

  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b px-6 py-4">
      <div className="flex min-w-0 flex-col gap-1">
        <span className="flex items-center gap-1.5">
          <h1 className="truncate font-mono font-semibold text-lg">{run.run_id}</h1>
          <CopyButton value={run.run_id} />
          <StatusBadge status={run.status} />
        </span>
        <span className="flex items-center gap-3 font-mono text-muted-foreground text-xs">
          {run.name && run.name !== run.run_id ? <span>{run.name}</span> : null}
          <span>
            {repoLabel(run.source_repo)}
            {run.source_ref ? `@${run.source_ref}` : ""}
          </span>
          <LiveDuration start={run.created_at} end={run.finished_at} className="tabular-nums" />
        </span>
      </div>
      <CostMeter cost={run.total_cost_usd ?? 0} budget={run.max_cost_usd} className="w-44" />
      <div className="ml-auto flex items-center gap-2">
        {resumable ? (
          <Button
            variant="outline"
            size="sm"
            disabled={resume.isPending}
            onClick={() => resume.mutate()}
          >
            {resume.isPending ? (
              <Loader2Icon className="size-3.5 animate-spin" />
            ) : (
              <RotateCcwIcon className="size-3.5" />
            )}
            Resume
          </Button>
        ) : null}
        {cancellable ? (
          <Button
            variant={confirmingCancel ? "destructive" : "outline"}
            size="sm"
            disabled={cancel.isPending}
            onClick={() => (confirmingCancel ? cancel.mutate() : setConfirmingCancel(true))}
            onBlur={() => setConfirmingCancel(false)}
          >
            {cancel.isPending ? (
              <Loader2Icon className="size-3.5 animate-spin" />
            ) : (
              <OctagonXIcon className="size-3.5" />
            )}
            {confirmingCancel ? "Confirm cancel" : "Cancel"}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
