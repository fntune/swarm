"use client";

import type { RunDetail } from "@spawnd/api-client";
import { useQuery } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { DagCanvas } from "@/components/dag/canvas";
import { EventFeed } from "@/components/events/feed";
import { AgentPanel } from "@/components/run/agent-panel";
import { pollInterval } from "@/lib/format";
import { runQuery } from "@/lib/queries";

export function RunWorkspace({
  runId,
  initialDetail,
}: {
  runId: string;
  initialDetail: RunDetail;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const selectedAgent = searchParams.get("agent");

  const detail = useQuery({
    ...runQuery(runId),
    initialData: initialDetail,
    refetchInterval: (query) => {
      const statuses = (query.state.data?.agents ?? []).map((agent) => agent.status);
      const runStatus = query.state.data?.run.status;
      return pollInterval([...(runStatus ? [runStatus] : []), ...statuses]);
    },
  });

  const agents = detail.data?.agents ?? [];
  const attempts = detail.data?.attempts ?? [];
  const agent = selectedAgent
    ? (agents.find((candidate) => candidate.name === selectedAgent) ?? null)
    : null;

  const selectAgent = React.useCallback(
    (name: string | null) => {
      const params = new URLSearchParams(searchParams);
      if (name) {
        params.set("agent", name);
      } else {
        params.delete("agent");
      }
      router.replace(params.size > 0 ? `${pathname}?${params}` : pathname, { scroll: false });
    },
    [router, pathname, searchParams],
  );

  return (
    <div className="grid min-h-0 flex-1 grid-rows-[minmax(280px,45%)_1fr] lg:grid-cols-[minmax(0,3fr)_minmax(320px,2fr)] lg:grid-rows-1">
      <div className="min-h-0 border-b lg:border-r lg:border-b-0">
        <DagCanvas agents={agents} selectedAgent={selectedAgent} onSelectAgent={selectAgent} />
      </div>
      <div className="flex min-h-0 flex-col">
        {agent ? (
          <AgentPanel
            runId={runId}
            agent={agent}
            attempts={attempts}
            onClose={() => selectAgent(null)}
          />
        ) : (
          <EventFeed runId={runId} className="min-h-0 flex-1" />
        )}
      </div>
    </div>
  );
}
