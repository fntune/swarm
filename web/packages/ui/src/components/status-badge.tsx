import { cn } from "../lib/utils";

const STATUS_DOTS: Record<string, string> = {
  queued: "bg-status-queued",
  pending: "bg-status-cancelled",
  running: "bg-status-running",
  completed: "bg-status-completed",
  failed: "bg-status-failed",
  timeout: "bg-status-failed",
  cost_exceeded: "bg-status-failed",
  paused: "bg-status-paused",
  cancelled: "bg-status-cancelled",
};

export function statusDotClass(status: string): string {
  return STATUS_DOTS[status] ?? "bg-status-cancelled";
}

/**
 * Status is always a static colored dot plus label — never animated.
 */
export function StatusBadge({
  status,
  className,
  label,
}: {
  status: string;
  className?: string;
  label?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border bg-card px-2 py-0.5 font-mono text-xs lowercase",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className={cn("size-2 shrink-0 rounded-full", statusDotClass(status))}
      />
      {label ?? status.replaceAll("_", " ")}
    </span>
  );
}
