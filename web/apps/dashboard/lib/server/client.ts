import { createSpawndClient, type SpawndClient } from "@spawnd/api-client";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { TOKEN_COOKIE } from "@/lib/auth-cookie";

export function apiBaseUrl(): string {
  const url = process.env.SPAWND_API_URL;
  if (!url) {
    throw new Error("SPAWND_API_URL is required (e.g. http://localhost:8765)");
  }
  return url.replace(/\/$/, "");
}

/** Server-component client bound to the operator's cookie token; redirects to login when absent. */
export async function getSpawndClient(): Promise<SpawndClient> {
  const store = await cookies();
  const token = store.get(TOKEN_COOKIE)?.value;
  if (!token) {
    redirect("/login");
  }
  return createSpawndClient({ baseUrl: apiBaseUrl(), token });
}
