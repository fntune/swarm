import { headers } from "next/headers";

import { Sidebar } from "@/components/shell/sidebar";
import { Topbar } from "@/components/shell/topbar";
import { dashboardAuthMode, tailscaleUserLogin } from "@/lib/server/auth";

export default async function ConsoleLayout({ children }: { children: React.ReactNode }) {
  const mode = dashboardAuthMode();
  const identity = mode === "tailscale" ? tailscaleUserLogin(await headers()) : undefined;
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar canLogout={mode === "token"} identity={identity ?? undefined} />
        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  );
}
