"use client";

import * as React from "react";

import { durationBetween } from "@/lib/format";

export function LiveDuration({
  start,
  end,
  className,
}: {
  start: string | null | undefined;
  end: string | null | undefined;
  className?: string;
}) {
  const [, forceTick] = React.useReducer((tick: number) => tick + 1, 0);

  React.useEffect(() => {
    if (end) return;
    const interval = setInterval(forceTick, 1_000);
    return () => clearInterval(interval);
  }, [end]);

  return (
    <span suppressHydrationWarning className={className}>
      {durationBetween(start, end) ?? "—"}
    </span>
  );
}
