"use client";

import { ForkGlyph, Logo } from "@spawnd/ui/components/logo";
import { cn } from "@spawnd/ui/lib/utils";
import { useQuery } from "@tanstack/react-query";
import {
  CalendarClockIcon,
  LayersIcon,
  LayoutGridIcon,
  MessageCircleQuestionIcon,
  PanelLeftCloseIcon,
  PanelLeftOpenIcon,
  PlayIcon,
  ServerIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import * as React from "react";

import { clarificationsQuery } from "@/lib/queries";

const NAV = [
  { href: "/", label: "Overview", icon: LayoutGridIcon },
  { href: "/new", label: "New run", icon: PlayIcon },
  { href: "/templates", label: "Templates", icon: LayersIcon },
  { href: "/schedules", label: "Schedules", icon: CalendarClockIcon },
  { href: "/workers", label: "Workers", icon: ServerIcon },
  { href: "/clarifications", label: "Clarifications", icon: MessageCircleQuestionIcon },
] as const;

const COLLAPSE_KEY = "spawnd:sidebar-collapsed";

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = React.useState(false);

  React.useEffect(() => {
    setCollapsed(localStorage.getItem(COLLAPSE_KEY) === "1");
  }, []);

  const clarifications = useQuery({ ...clarificationsQuery(), refetchInterval: 30_000 });
  const pendingCount = clarifications.data?.length ?? 0;

  function toggle() {
    setCollapsed((current) => {
      localStorage.setItem(COLLAPSE_KEY, current ? "0" : "1");
      return !current;
    });
  }

  return (
    <aside
      className={cn(
        "sticky top-0 flex h-screen shrink-0 flex-col border-r bg-card transition-[width] duration-200",
        collapsed ? "w-14" : "w-52",
      )}
    >
      <div
        className={cn("flex h-14 items-center border-b px-4", collapsed && "justify-center px-0")}
      >
        <Link href="/" aria-label="Overview">
          {collapsed ? <ForkGlyph className="size-5 text-primary" /> : <Logo />}
        </Link>
      </div>
      <nav className="flex flex-1 flex-col gap-1 p-2">
        {NAV.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              title={item.label}
              className={cn(
                "flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] transition-colors",
                active
                  ? "bg-accent font-medium text-accent-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
                collapsed && "justify-center px-0",
              )}
            >
              <item.icon className="size-4 shrink-0" />
              {!collapsed && <span className="truncate">{item.label}</span>}
              {item.href === "/clarifications" && pendingCount > 0 ? (
                <span
                  className={cn(
                    "ml-auto rounded-full bg-primary px-1.5 font-mono text-[11px] text-primary-foreground tabular-nums",
                    collapsed && "absolute top-1 right-1 ml-0 px-1",
                  )}
                >
                  {pendingCount}
                </span>
              ) : null}
            </Link>
          );
        })}
      </nav>
      <div className="border-t p-2">
        <button
          type="button"
          onClick={toggle}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className={cn(
            "flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] text-muted-foreground hover:bg-muted hover:text-foreground",
            collapsed && "justify-center px-0",
          )}
        >
          {collapsed ? (
            <PanelLeftOpenIcon className="size-4" />
          ) : (
            <>
              <PanelLeftCloseIcon className="size-4" />
              <span>Collapse</span>
            </>
          )}
        </button>
      </div>
    </aside>
  );
}
