"use client";

import { ThemeToggle } from "@spawnd/ui/components/theme-toggle";
import { Button } from "@spawnd/ui/components/ui/button";
import { ChevronRightIcon, LogOutIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import * as React from "react";

function crumbs(pathname: string): { href: string; label: string }[] {
  const segments = pathname.split("/").filter(Boolean);
  const result: { href: string; label: string }[] = [{ href: "/", label: "console" }];
  let href = "";
  for (const segment of segments) {
    href += `/${segment}`;
    result.push({ href, label: decodeURIComponent(segment) });
  }
  return result;
}

export function Topbar({ canLogout, identity }: { canLogout: boolean; identity?: string }) {
  const pathname = usePathname();
  const trail = crumbs(pathname);

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.assign("/login");
  }

  return (
    <header className="sticky top-0 z-10 flex h-14 shrink-0 items-center justify-between border-b bg-background/95 px-4 backdrop-blur">
      <nav className="flex min-w-0 items-center gap-1 font-mono text-[13px] text-muted-foreground">
        {trail.map((crumb, index) => (
          <React.Fragment key={crumb.href}>
            {index > 0 ? <ChevronRightIcon className="size-3.5 shrink-0" /> : null}
            {index === trail.length - 1 ? (
              <span className="truncate text-foreground">{crumb.label}</span>
            ) : (
              <Link href={crumb.href} className="truncate hover:text-foreground">
                {crumb.label}
              </Link>
            )}
          </React.Fragment>
        ))}
      </nav>
      <div className="flex items-center gap-1">
        {identity ? (
          <span className="hidden font-mono text-xs text-muted-foreground sm:inline">
            {identity}
          </span>
        ) : null}
        <ThemeToggle />
        {canLogout ? (
          <Button
            variant="ghost"
            size="icon"
            aria-label="Sign out"
            className="text-muted-foreground"
            onClick={logout}
          >
            <LogOutIcon className="size-4" />
          </Button>
        ) : null}
      </div>
    </header>
  );
}
