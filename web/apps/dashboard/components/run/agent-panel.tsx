"use client";

import type { Agent, Attempt } from "@spawnd/api-client";
import { CopyButton } from "@spawnd/ui/components/copy-button";
import { StatusBadge, statusDotClass } from "@spawnd/ui/components/status-badge";
import { Button } from "@spawnd/ui/components/ui/button";
import { Separator } from "@spawnd/ui/components/ui/separator";
import { cn } from "@spawnd/ui/lib/utils";
import { useQuery } from "@tanstack/react-query";
import { XIcon } from "lucide-react";
import type * as React from "react";

import { CheckRow } from "@/components/run/check-row";
import { durationBetween, formatTokens, formatUsd } from "@/lib/format";
import { runArtifactsQuery, runChecksQuery, runUsageQuery } from "@/lib/queries";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-2 px-4 py-3">
      <h3 className="font-mono text-[11px] text-muted-foreground uppercase tracking-wider">
        {title}
      </h3>
      {children}
    </section>
  );
}

export function AgentPanel({
  runId,
  agent,
  attempts,
  onClose,
}: {
  runId: string;
  agent: Agent;
  attempts: Attempt[];
  onClose: () => void;
}) {
  const checks = useQuery(runChecksQuery(runId));
  const artifacts = useQuery(runArtifactsQuery(runId));
  const usage = useQuery(runUsageQuery(runId));

  const agentChecks = (checks.data ?? []).filter((check) => check.agent === agent.name);
  const agentArtifacts = (artifacts.data ?? []).filter((artifact) => artifact.agent === agent.name);
  const rollup = (usage.data?.by_agent ?? []).find((entry) => entry.agent === agent.name);
  const agentAttempts = attempts.filter((attempt) => attempt.agent === agent.name);

  return (
    <div className="flex min-h-0 flex-col overflow-y-auto">
      <div className="sticky top-0 z-10 flex items-center justify-between border-b bg-background/95 px-4 py-2.5 backdrop-blur">
        <span className="flex min-w-0 items-center gap-2">
          <span className="truncate font-medium font-mono text-sm">{agent.name}</span>
          <StatusBadge status={agent.status} />
        </span>
        <Button variant="ghost" size="icon" aria-label="Close agent panel" onClick={onClose}>
          <XIcon className="size-4" />
        </Button>
      </div>

      <Section title="agent">
        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 font-mono text-xs">
          <dt className="text-muted-foreground">runtime</dt>
          <dd>{[agent.runtime, agent.model].filter(Boolean).join(" · ") || "—"}</dd>
          <dt className="text-muted-foreground">type</dt>
          <dd>
            {agent.type}
            {agent.write_allowed === false ? " · read-only" : ""}
          </dd>
          <dt className="text-muted-foreground">branch</dt>
          <dd className="flex min-w-0 items-center gap-1">
            <span className="truncate">{agent.branch ?? "—"}</span>
            {agent.branch ? <CopyButton value={agent.branch} className="size-5" /> : null}
          </dd>
          <dt className="text-muted-foreground">depends on</dt>
          <dd className="truncate">{(agent.depends_on ?? []).join(", ") || "—"}</dd>
          {agent.retry_attempt && agent.retry_attempt > 0 ? (
            <>
              <dt className="text-muted-foreground">retries</dt>
              <dd>
                {agent.retry_attempt}
                {agent.retry_count ? ` / ${agent.retry_count}` : ""}
              </dd>
            </>
          ) : null}
        </dl>
        {agent.prompt_preview ? (
          <p className="rounded-md bg-muted/50 px-2.5 py-2 font-mono text-[11px] text-muted-foreground leading-relaxed">
            {agent.prompt_preview}
          </p>
        ) : null}
      </Section>

      {agent.error ? (
        <>
          <Separator />
          <Section title="error">
            <p className="rounded-md border border-status-failed/30 bg-status-failed/10 px-2.5 py-2 font-mono text-status-failed text-xs leading-relaxed">
              {agent.error}
            </p>
          </Section>
        </>
      ) : null}

      <Separator />
      <Section title={`attempts (${agentAttempts.length})`}>
        {agentAttempts.length === 0 ? (
          <p className="text-muted-foreground text-xs">Not yet claimed by a worker.</p>
        ) : (
          <ul className="flex flex-col gap-1">
            {agentAttempts.map((attempt) => (
              <li
                key={attempt.id}
                className="flex items-center gap-2 rounded-md border px-2.5 py-1.5 font-mono text-xs"
              >
                <span
                  aria-hidden="true"
                  className={cn("size-2 rounded-full", statusDotClass(attempt.status))}
                />
                <span>#{attempt.attempt_number}</span>
                <span className="text-muted-foreground">{attempt.status}</span>
                <span
                  suppressHydrationWarning
                  className="ml-auto text-muted-foreground tabular-nums"
                >
                  {durationBetween(attempt.started_at, attempt.finished_at) ?? "—"}
                </span>
                <span className="text-muted-foreground">{attempt.worker_id ?? ""}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Separator />
      <Section title={`checks (${agentChecks.length})`}>
        {agentChecks.length === 0 ? (
          <p className="text-muted-foreground text-xs">No check executions recorded.</p>
        ) : (
          <div className="flex flex-col gap-1.5">
            {agentChecks.map((check) => (
              <CheckRow key={check.id} runId={runId} check={check} />
            ))}
          </div>
        )}
      </Section>

      <Separator />
      <Section title={`artifacts (${agentArtifacts.length})`}>
        {agentArtifacts.length === 0 ? (
          <p className="text-muted-foreground text-xs">No artifacts stored.</p>
        ) : (
          <ul className="flex flex-col gap-1 font-mono text-xs">
            {agentArtifacts.slice(0, 12).map((artifact) => (
              <li key={artifact.id} className="flex items-center gap-2">
                <span className="rounded bg-muted px-1.5 py-0.5 text-[11px]">{artifact.kind}</span>
                <span className="truncate text-muted-foreground">
                  {artifact.content_type ?? ""}
                </span>
                <span className="ml-auto text-muted-foreground tabular-nums">
                  {artifact.size_bytes != null ? `${artifact.size_bytes}b` : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      {rollup ? (
        <>
          <Separator />
          <Section title="usage">
            <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 font-mono text-xs tabular-nums">
              <dt className="text-muted-foreground">input tokens</dt>
              <dd>{formatTokens(rollup.input_tokens)}</dd>
              <dt className="text-muted-foreground">output tokens</dt>
              <dd>{formatTokens(rollup.output_tokens)}</dd>
              <dt className="text-muted-foreground">cost</dt>
              <dd>{formatUsd(rollup.amount_usd)}</dd>
            </dl>
          </Section>
        </>
      ) : null}
    </div>
  );
}
