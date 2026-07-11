import { cn } from "../lib/utils";

export interface BarListItem {
  label: string;
  value: number;
  display?: string;
  hint?: string;
}

export function BarList({
  items,
  className,
  barClassName,
}: {
  items: BarListItem[];
  className?: string;
  barClassName?: string;
}) {
  const max = Math.max(...items.map((item) => item.value), 0);
  return (
    <div className={cn("flex flex-col gap-2", className)}>
      {items.map((item) => (
        <div key={item.label} className="flex items-center gap-3">
          <span className="w-32 shrink-0 truncate font-mono text-muted-foreground text-xs">
            {item.label}
          </span>
          <span className="relative h-5 min-w-0 flex-1 overflow-hidden rounded-sm bg-muted">
            <span
              className={cn("block h-full rounded-sm bg-primary/70", barClassName)}
              style={{ width: max > 0 ? `${Math.max((item.value / max) * 100, 1)}%` : "0%" }}
            />
          </span>
          <span className="w-24 shrink-0 text-right font-mono tabular-nums text-xs">
            {item.display ?? item.value.toLocaleString()}
          </span>
          {item.hint ? (
            <span className="w-20 shrink-0 truncate text-right text-muted-foreground text-xs">
              {item.hint}
            </span>
          ) : null}
        </div>
      ))}
    </div>
  );
}
