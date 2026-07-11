"use client";

import { formatDistanceToNowStrict } from "date-fns";
import * as React from "react";

import { cn } from "../lib/utils";

export function RelativeTime({
  value,
  className,
  refreshSeconds = 30,
}: {
  value: string | Date | null | undefined;
  className?: string;
  refreshSeconds?: number;
}) {
  const [, forceTick] = React.useReducer((tick: number) => tick + 1, 0);

  React.useEffect(() => {
    const interval = setInterval(forceTick, refreshSeconds * 1000);
    return () => clearInterval(interval);
  }, [refreshSeconds]);

  if (!value) {
    return <span className={cn("text-muted-foreground", className)}>—</span>;
  }
  const date = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) {
    return <span className={cn("text-muted-foreground", className)}>—</span>;
  }
  return (
    <time
      dateTime={date.toISOString()}
      title={date.toLocaleString()}
      suppressHydrationWarning
      className={className}
    >
      {formatDistanceToNowStrict(date, { addSuffix: true })}
    </time>
  );
}
