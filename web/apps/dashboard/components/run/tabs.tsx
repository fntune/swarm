"use client";

import { cn } from "@spawnd/ui/lib/utils";
import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { segment: "", label: "dag" },
  { segment: "checks", label: "checks" },
  { segment: "artifacts", label: "artifacts" },
  { segment: "usage", label: "usage" },
  { segment: "provenance", label: "provenance" },
  { segment: "traces", label: "traces" },
] as const;

export function RunTabs({ runId }: { runId: string }) {
  const pathname = usePathname();
  const base = `/runs/${encodeURIComponent(runId)}`;

  return (
    <nav className="flex items-center gap-1 border-b px-6">
      {TABS.map((tab) => {
        const href = tab.segment ? `${base}/${tab.segment}` : base;
        const active = pathname === href;
        return (
          <Link
            key={tab.label}
            href={href}
            className={cn(
              "-mb-px border-b-2 px-3 py-2 font-mono text-xs transition-colors",
              active
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
