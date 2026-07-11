"use client";

import type { RunEvent } from "@spawnd/api-client";
import { useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { browserClient } from "@/lib/queries";

export type StreamStatus = "connecting" | "live" | "polling" | "done";

const MAX_EVENTS = 1_000;
const POLL_MS = 3_000;
const INVALIDATE_THROTTLE_MS = 2_000;

function sortEvents(events: RunEvent[]): RunEvent[] {
  return [...events].sort((a, b) => {
    const at = Date.parse(a.created_at);
    const bt = Date.parse(b.created_at);
    if (at !== bt) return bt - at;
    return a.id < b.id ? 1 : -1;
  });
}

/**
 * Live run events: SSE through the authenticated proxy, degrading to cursor
 * polling after repeated stream errors. Newest events first.
 */
export function useRunStream(runId: string) {
  const queryClient = useQueryClient();
  const [events, setEvents] = React.useState<RunEvent[]>([]);
  const [status, setStatus] = React.useState<StreamStatus>("connecting");
  const seenRef = React.useRef<Set<string>>(new Set());
  const lastInvalidateRef = React.useRef(0);

  React.useEffect(() => {
    seenRef.current = new Set();
    setEvents([]);
    setStatus("connecting");

    let disposed = false;
    let pollTimer: ReturnType<typeof setInterval> | null = null;
    let errorCount = 0;

    const invalidateRun = () => {
      const now = Date.now();
      if (now - lastInvalidateRef.current < INVALIDATE_THROTTLE_MS) return;
      lastInvalidateRef.current = now;
      queryClient.invalidateQueries({ queryKey: ["run", runId] });
      queryClient.invalidateQueries({ queryKey: ["runs"] });
    };

    const addEvents = (rows: RunEvent[]) => {
      const fresh = rows.filter((row) => row.id && !seenRef.current.has(row.id));
      if (fresh.length === 0) return;
      for (const row of fresh) seenRef.current.add(row.id);
      setEvents((current) => sortEvents([...fresh, ...current]).slice(0, MAX_EVENTS));
      invalidateRun();
    };

    const startPolling = () => {
      if (disposed || pollTimer) return;
      setStatus("polling");
      const poll = async () => {
        try {
          const rows = await browserClient().runs.events(runId, { limit: 200 });
          addEvents(rows);
        } catch {
          // keep polling; transient proxy/API failures recover on the next tick
        }
      };
      void poll();
      pollTimer = setInterval(poll, POLL_MS);
    };

    const source = new EventSource(
      `/api/spawnd/runs/${encodeURIComponent(runId)}/events/stream?replay=200`,
    );

    source.addEventListener("open", () => {
      if (!disposed) setStatus("live");
    });
    source.addEventListener("run-event", (message) => {
      try {
        addEvents([JSON.parse((message as MessageEvent).data) as RunEvent]);
      } catch {
        // malformed frame; ignore
      }
    });
    source.addEventListener("coordination", () => {
      invalidateRun();
    });
    source.addEventListener("done", () => {
      setStatus("done");
      source.close();
      lastInvalidateRef.current = 0;
      invalidateRun();
    });
    source.addEventListener("error", () => {
      errorCount += 1;
      if (errorCount >= 2) {
        source.close();
        startPolling();
      }
    });

    return () => {
      disposed = true;
      source.close();
      if (pollTimer) clearInterval(pollTimer);
    };
  }, [runId, queryClient]);

  return { events, status };
}
