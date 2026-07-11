import { type NextRequest, NextResponse } from "next/server";

import { TOKEN_COOKIE } from "@/lib/auth-cookie";
import { resolveUpstreamPath } from "@/lib/proxy-path";
import { authorizeDashboardRequest } from "@/lib/server/auth";
import { apiBaseUrl } from "@/lib/server/config";

export const dynamic = "force-dynamic";

const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "transfer-encoding",
  "content-encoding",
  "content-length",
  "te",
  "trailer",
  "upgrade",
]);

async function proxyRequest(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const authorization = authorizeDashboardRequest({
    headers: request.headers,
    cookieToken: request.cookies.get(TOKEN_COOKIE)?.value,
  });
  if (!authorization.ok) {
    return NextResponse.json({ detail: authorization.detail }, { status: authorization.status });
  }
  const { path } = await context.params;
  const upstreamPath = resolveUpstreamPath(path ?? []);
  if (!upstreamPath) {
    return NextResponse.json({ detail: "Not found" }, { status: 404 });
  }

  const url = new URL(`${apiBaseUrl()}/${upstreamPath}`);
  request.nextUrl.searchParams.forEach((value, key) => {
    url.searchParams.append(key, value);
  });

  const headers = new Headers({ Authorization: `Bearer ${authorization.token}` });
  for (const name of ["content-type", "accept", "last-event-id"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  let upstream: Response;
  try {
    const hasBody = request.method !== "GET" && request.method !== "HEAD";
    upstream = await fetch(url, {
      method: request.method,
      headers,
      body: hasBody ? request.body : undefined,
      cache: "no-store",
      signal: request.signal,
      ...(hasBody ? { duplex: "half" } : {}),
    } as RequestInit);
  } catch {
    return NextResponse.json({ detail: "spawnd API is unreachable" }, { status: 502 });
  }

  if (upstream.status === 401) {
    if (authorization.mode === "tailscale") {
      return NextResponse.json(
        { detail: "Dashboard API credentials were rejected" },
        { status: 502 },
      );
    }
    const response = NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
    response.cookies.delete(TOKEN_COOKIE);
    return response;
  }

  const responseHeaders = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key)) responseHeaders.set(key, value);
  });
  if (responseHeaders.get("content-type")?.includes("text/event-stream")) {
    responseHeaders.set("Cache-Control", "no-cache, no-transform");
    responseHeaders.set("X-Accel-Buffering", "no");
  }
  return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
}

export {
  proxyRequest as GET,
  proxyRequest as POST,
  proxyRequest as PATCH,
  proxyRequest as PUT,
  proxyRequest as DELETE,
};
