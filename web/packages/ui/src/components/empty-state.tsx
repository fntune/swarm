import type { LucideIcon } from "lucide-react";

import { cn } from "../lib/utils";

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-6 py-12 text-center",
        className,
      )}
    >
      {Icon ? <Icon aria-hidden="true" className="size-8 text-muted-foreground/60" /> : null}
      <p className="font-medium text-sm">{title}</p>
      {description ? <p className="max-w-sm text-muted-foreground text-sm">{description}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
