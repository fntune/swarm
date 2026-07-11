"use client";

import type { Check } from "@spawnd/api-client";
import { EmptyState } from "@spawnd/ui/components/empty-state";
import { useQuery } from "@tanstack/react-query";
import { ListChecksIcon } from "lucide-react";

import { CheckRow } from "@/components/run/check-row";
import { runChecksQuery } from "@/lib/queries";

export function ChecksPanel({ runId, initialChecks }: { runId: string; initialChecks: Check[] }) {
  const checks = useQuery({
    ...runChecksQuery(runId),
    initialData: initialChecks,
    refetchInterval: 10_000,
  });

  const rows = checks.data ?? [];
  if (rows.length === 0) {
    return (
      <EmptyState
        icon={ListChecksIcon}
        title="No check executions"
        description="Verification commands run by workers will appear here with exit codes and output."
      />
    );
  }

  return (
    <div className="flex flex-col gap-1.5">
      {rows.map((check) => (
        <CheckRow key={check.id} runId={runId} check={check} showAgent />
      ))}
    </div>
  );
}
