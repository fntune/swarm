import { cn } from "../lib/utils";

export function formatUsd(amount: number): string {
  return `$${amount.toFixed(2)}`;
}

export function CostMeter({
  cost,
  budget,
  className,
  compact = false,
}: {
  cost: number;
  budget: number | null | undefined;
  className?: string;
  compact?: boolean;
}) {
  const ratio = budget && budget > 0 ? Math.min(cost / budget, 1) : null;
  const barColor =
    ratio === null
      ? "bg-primary"
      : ratio >= 0.85
        ? "bg-status-failed"
        : ratio >= 0.6
          ? "bg-status-running"
          : "bg-primary";

  return (
    <div className={cn("flex min-w-0 flex-col gap-1", className)}>
      <span
        className={cn(
          "font-mono tabular-nums",
          compact ? "text-xs" : "text-sm",
          ratio !== null && ratio >= 0.85 ? "text-status-failed" : "text-foreground",
        )}
      >
        {formatUsd(cost)}
        {budget ? <span className="text-muted-foreground"> / {formatUsd(budget)}</span> : null}
      </span>
      {ratio !== null ? (
        <span className="h-1 w-full overflow-hidden rounded-full bg-muted">
          <span
            className={cn("block h-full rounded-full transition-[width] duration-500", barColor)}
            style={{ width: `${Math.max(ratio * 100, 1)}%` }}
          />
        </span>
      ) : null}
    </div>
  );
}
