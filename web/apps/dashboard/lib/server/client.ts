import { createSpawndClient, type SpawndClient } from "@spawnd/api-client";
import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";

import { TOKEN_COOKIE } from "@/lib/auth-cookie";
import { authorizeDashboardRequest } from "./auth";
import { apiBaseUrl } from "./config";

/** Server-component client bound to the authenticated operator request. */
export async function getSpawndClient(): Promise<SpawndClient> {
  const [cookieStore, headerStore] = await Promise.all([cookies(), headers()]);
  const authorization = authorizeDashboardRequest({
    headers: headerStore,
    cookieToken: cookieStore.get(TOKEN_COOKIE)?.value,
  });
  if (!authorization.ok && authorization.mode === "token") {
    redirect("/login");
  }
  if (!authorization.ok) {
    throw new Error(authorization.detail);
  }
  return createSpawndClient({ baseUrl: apiBaseUrl(), token: authorization.token });
}
