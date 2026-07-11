"use client";

import type { RunEvent } from "@spawnd/api-client";
import { EmptyState } from "@spawnd/ui/components/empty-state";
import { RelativeTime } from "@spawnd/ui/components/relative-time";
import { Button } from "@spawnd/ui/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@spawnd/ui/components/ui/card";
import { Textarea } from "@spawnd/ui/components/ui/textarea";
import { cn } from "@spawnd/ui/lib/utils";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2Icon, MessageCircleQuestionIcon, SendIcon } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { browserClient, clarificationsQuery } from "@/lib/queries";

function question(event: RunEvent): string {
  const data = event.data ?? {};
  const candidate = data.question ?? data.message ?? data.blocker ?? data.description;
  if (typeof candidate === "string" && candidate.length > 0) return candidate;
  return JSON.stringify(data);
}

function ClarificationCard({ event }: { event: RunEvent }) {
  const queryClient = useQueryClient();
  const [response, setResponse] = React.useState("");

  const answer = useMutation({
    mutationFn: () => browserClient().runs.answerClarification(event.run_id, event.id, response),
    onSuccess: () => {
      toast.success("Response sent to the waiting agent");
      queryClient.invalidateQueries({ queryKey: ["clarifications"] });
      queryClient.invalidateQueries({ queryKey: ["run", event.run_id] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-sm">
          <span
            className={cn(
              "rounded px-1.5 py-0.5 text-[11px]",
              event.event_type === "blocker"
                ? "bg-status-failed/15 text-status-failed"
                : "bg-status-running/15 text-status-running",
            )}
          >
            {event.event_type}
          </span>
          <Link
            href={`/runs/${encodeURIComponent(event.run_id)}?agent=${encodeURIComponent(event.agent)}`}
            className="hover:text-primary"
          >
            {event.run_id} · {event.agent}
          </Link>
          <span className="ml-auto font-normal text-muted-foreground text-xs">
            <RelativeTime value={event.created_at} />
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="rounded-md bg-muted/50 px-3 py-2 font-mono text-xs leading-relaxed">
          {question(event)}
        </p>
        <Textarea
          value={response}
          onChange={(event) => setResponse(event.target.value)}
          placeholder="Type your answer for the waiting agent…"
          rows={2}
          className="font-mono text-xs"
        />
        <Button
          size="sm"
          className="self-end"
          disabled={answer.isPending || response.trim().length === 0}
          onClick={() => answer.mutate()}
        >
          {answer.isPending ? (
            <Loader2Icon className="size-3.5 animate-spin" />
          ) : (
            <SendIcon className="size-3.5" />
          )}
          Send response
        </Button>
      </CardContent>
    </Card>
  );
}

export function ClarificationsInbox({
  initialClarifications,
}: {
  initialClarifications: RunEvent[];
}) {
  const clarifications = useQuery({
    ...clarificationsQuery(),
    initialData: initialClarifications,
    refetchInterval: 10_000,
  });

  const rows = clarifications.data ?? [];
  if (rows.length === 0) {
    return (
      <EmptyState
        icon={MessageCircleQuestionIcon}
        title="No pending clarifications"
        description="When an agent asks a question or hits a blocker, it appears here until answered."
      />
    );
  }

  return (
    <div className="flex max-w-3xl flex-col gap-4">
      {rows.map((event) => (
        <ClarificationCard key={event.id} event={event} />
      ))}
    </div>
  );
}
