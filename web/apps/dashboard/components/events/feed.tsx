"use client";

import type { RunEvent } from "@spawnd/api-client";
import { cn } from "@spawnd/ui/lib/utils";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ChevronRightIcon } from "lucide-react";
import * as React from "react";

import { type StreamStatus, useRunStream } from "@/lib/use-run-stream";

const ROW_HEIGHT = 30;

function eventTone(eventType: string): string {
  if (/(fail|error|blocker|exceeded|tripped)/.test(eventType)) return "text-status-failed";
  if (/(done|completed|response)/.test(eventType)) return "text-status-completed";
  if (/(clarification)/.test(eventType)) return "text-status-running";
  if (/(claim|queued|ready|submitted|created)/.test(eventType)) return "text-status-queued";
  return "text-muted-foreground";
}

function StreamDot({ status }: { status: StreamStatus }) {
  const label =
    status === "live"
      ? "live"
      : status === "polling"
        ? "polling"
        : status === "done"
          ? "finished"
          : "connecting";
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-[11px] text-muted-foreground">
      <span
        aria-hidden="true"
        className={cn(
          "size-1.5 rounded-full",
          status === "live" && "bg-status-completed",
          status === "polling" && "bg-status-running",
          status === "done" && "bg-status-cancelled",
          status === "connecting" && "bg-status-queued",
        )}
      />
      {label}
    </span>
  );
}

function EventRow({ event }: { event: RunEvent }) {
  const [open, setOpen] = React.useState(false);
  const hasData = event.data && Object.keys(event.data).length > 0;
  const time = new Date(event.created_at);

  return (
    <div className="border-border/60 border-b">
      <button
        type="button"
        onClick={() => hasData && setOpen((current) => !current)}
        className={cn(
          "flex w-full items-center gap-2 px-3 py-1.5 text-left",
          hasData && "hover:bg-muted/50",
        )}
      >
        <span className="shrink-0 font-mono text-[11px] text-muted-foreground tabular-nums">
          {Number.isNaN(time.getTime()) ? "—" : time.toLocaleTimeString([], { hour12: false })}
        </span>
        <span className="w-24 shrink-0 truncate font-mono text-[11px] text-muted-foreground">
          {event.agent}
        </span>
        <span className={cn("truncate font-mono text-xs", eventTone(event.event_type))}>
          {event.event_type}
        </span>
        {hasData ? (
          <ChevronRightIcon
            className={cn(
              "ml-auto size-3 shrink-0 text-muted-foreground transition-transform",
              open && "rotate-90",
            )}
          />
        ) : null}
      </button>
      {open && hasData ? (
        <pre className="overflow-x-auto bg-muted/40 px-3 py-2 font-mono text-[11px] text-muted-foreground">
          {JSON.stringify(event.data, null, 2)}
        </pre>
      ) : null}
    </div>
  );
}

export function EventFeed({ runId, className }: { runId: string; className?: string }) {
  const { events, status } = useRunStream(runId);
  const parentRef = React.useRef<HTMLDivElement | null>(null);

  const virtualizer = useVirtualizer({
    count: events.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 30,
    getItemKey: (index) => events[index]?.id ?? index,
  });

  return (
    <div className={cn("flex min-h-0 flex-col", className)}>
      <div className="flex shrink-0 items-center justify-between border-b px-3 py-2">
        <span className="font-mono text-[11px] text-muted-foreground uppercase tracking-wider">
          events
        </span>
        <StreamDot status={status} />
      </div>
      {events.length === 0 ? (
        <p className="p-4 text-muted-foreground text-sm">No events yet.</p>
      ) : (
        <div ref={parentRef} className="min-h-0 flex-1 overflow-auto">
          <div className="relative w-full" style={{ height: virtualizer.getTotalSize() }}>
            {virtualizer.getVirtualItems().map((row) => {
              const event = events[row.index];
              if (!event) return null;
              return (
                <div
                  key={row.key}
                  data-index={row.index}
                  ref={virtualizer.measureElement}
                  className="absolute top-0 left-0 w-full animate-in fade-in duration-300"
                  style={{ transform: `translateY(${row.start}px)` }}
                >
                  <EventRow event={event} />
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
