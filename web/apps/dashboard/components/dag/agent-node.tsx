"use client";

import type { Agent } from "@spawnd/api-client";
import { statusDotClass } from "@spawnd/ui/components/status-badge";
import { cn } from "@spawnd/ui/lib/utils";
import { Handle, type NodeProps, Position } from "@xyflow/react";
import { CircleAlertIcon, RotateCcwIcon } from "lucide-react";
import { DAG_NODE_HEIGHT, DAG_NODE_WIDTH } from "@/lib/dag-layout";
import { formatUsd } from "@/lib/format";

export function AgentNode({ data, selected }: NodeProps & { data: { agent: Agent } }) {
  const agent = data.agent;
  return (
    <div
      style={{ width: DAG_NODE_WIDTH, height: DAG_NODE_HEIGHT }}
      className={cn(
        "flex cursor-pointer flex-col justify-between rounded-lg border bg-card px-3 py-2 text-left shadow-xs transition-colors",
        selected ? "border-primary ring-2 ring-ring/40" : "hover:border-primary/50",
      )}
    >
      <Handle type="target" position={Position.Left} className="!bg-border !size-2" />
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-medium font-mono text-[13px]">{agent.name}</span>
        <span className="flex shrink-0 items-center gap-1">
          {agent.retry_attempt && agent.retry_attempt > 0 ? (
            <span
              title={`retry ${agent.retry_attempt}`}
              className="inline-flex items-center gap-0.5 rounded bg-muted px-1 font-mono text-[10px] text-muted-foreground"
            >
              <RotateCcwIcon className="size-2.5" />
              {agent.retry_attempt}
            </span>
          ) : null}
          {agent.error ? <CircleAlertIcon className="size-3.5 text-status-failed" /> : null}
          <span
            aria-hidden="true"
            className={cn("size-2 rounded-full", statusDotClass(agent.status))}
          />
        </span>
      </div>
      <div className="flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
        <span className="truncate font-mono">
          {[agent.runtime, agent.model].filter(Boolean).join(" · ") || agent.type}
        </span>
        <span className="shrink-0 font-mono tabular-nums">
          {agent.cost_usd > 0 ? formatUsd(agent.cost_usd) : ""}
        </span>
      </div>
      <div className="flex items-center justify-between text-[11px]">
        <span className="font-mono text-muted-foreground lowercase">
          {agent.status.replaceAll("_", " ")}
        </span>
        {agent.write_allowed === false ? (
          <span className="rounded bg-muted px-1 font-mono text-[10px] text-muted-foreground">
            read-only
          </span>
        ) : null}
      </div>
      <Handle type="source" position={Position.Right} className="!bg-border !size-2" />
    </div>
  );
}
