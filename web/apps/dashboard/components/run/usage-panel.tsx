"use client";

import type { RunUsage } from "@spawnd/api-client";
import { BarList } from "@spawnd/ui/components/bar-list";
import { EmptyState } from "@spawnd/ui/components/empty-state";
import { Card, CardContent, CardHeader, CardTitle } from "@spawnd/ui/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@spawnd/ui/components/ui/table";
import { useQuery } from "@tanstack/react-query";
import { CoinsIcon } from "lucide-react";

import { formatTokens, formatUsd } from "@/lib/format";
import { runUsageQuery } from "@/lib/queries";

export function UsagePanel({ runId, initialUsage }: { runId: string; initialUsage: RunUsage }) {
  const usage = useQuery({
    ...runUsageQuery(runId),
    initialData: initialUsage,
    refetchInterval: 10_000,
  });

  const data = usage.data;
  const byAgent = data?.by_agent ?? [];
  if (byAgent.length === 0) {
    return (
      <EmptyState
        icon={CoinsIcon}
        title="No usage recorded"
        description="Token and cost rows appear once agents start executing."
      />
    );
  }

  const totalCost = byAgent.reduce((sum, entry) => sum + entry.amount_usd, 0);
  const totalTokens = byAgent.reduce((sum, entry) => sum + entry.total_tokens, 0);

  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="font-mono text-[11px] text-muted-foreground uppercase tracking-wider">
              cost by agent · {formatUsd(totalCost)} total
            </CardTitle>
          </CardHeader>
          <CardContent>
            <BarList
              items={byAgent
                .filter((entry) => entry.amount_usd > 0)
                .sort((a, b) => b.amount_usd - a.amount_usd)
                .map((entry) => ({
                  label: entry.agent,
                  value: entry.amount_usd,
                  display: formatUsd(entry.amount_usd),
                }))}
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="font-mono text-[11px] text-muted-foreground uppercase tracking-wider">
              tokens by agent · {formatTokens(totalTokens)} total
            </CardTitle>
          </CardHeader>
          <CardContent>
            <BarList
              items={byAgent
                .filter((entry) => entry.total_tokens > 0)
                .sort((a, b) => b.total_tokens - a.total_tokens)
                .map((entry) => ({
                  label: entry.agent,
                  value: entry.total_tokens,
                  display: formatTokens(entry.total_tokens),
                  hint: `${formatTokens(entry.input_tokens)} in / ${formatTokens(entry.output_tokens)} out`,
                }))}
            />
          </CardContent>
        </Card>
      </div>
      {data && data.token_usage.length > 0 ? (
        <div className="overflow-x-auto rounded-lg border">
          <Table className="text-[13px]">
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>agent</TableHead>
                <TableHead>provider</TableHead>
                <TableHead>model</TableHead>
                <TableHead>scope</TableHead>
                <TableHead className="text-right">input</TableHead>
                <TableHead className="text-right">cached</TableHead>
                <TableHead className="text-right">output</TableHead>
                <TableHead className="text-right">total</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.token_usage.map((row) => (
                <TableRow key={row.id}>
                  <TableCell className="font-mono text-xs">{row.agent ?? "_system"}</TableCell>
                  <TableCell className="font-mono text-muted-foreground text-xs">
                    {row.provider}
                  </TableCell>
                  <TableCell className="font-mono text-muted-foreground text-xs">
                    {row.model ?? "—"}
                  </TableCell>
                  <TableCell className="font-mono text-muted-foreground text-xs">
                    {row.scope}
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs tabular-nums">
                    {row.input_tokens.toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right font-mono text-muted-foreground text-xs tabular-nums">
                    {row.cached_input_tokens.toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs tabular-nums">
                    {row.output_tokens.toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs tabular-nums">
                    {row.total_tokens.toLocaleString()}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : null}
    </div>
  );
}
