import { type NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { TOKEN_COOKIE } from "@/lib/auth-cookie";
import { apiBaseUrl } from "@/lib/server/client";

const LoginBody = z.object({ token: z.string().min(1) });

export async function POST(request: NextRequest) {
  const parsed = LoginBody.safeParse(await request.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: "API token is required" }, { status: 400 });
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${apiBaseUrl()}/workers`, {
      headers: { Authorization: `Bearer ${parsed.data.token}` },
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ error: "spawnd API is unreachable" }, { status: 502 });
  }
  if (upstream.status === 401) {
    return NextResponse.json({ error: "Invalid API token" }, { status: 401 });
  }
  if (!upstream.ok) {
    return NextResponse.json(
      { error: `spawnd API error (status ${upstream.status})` },
      { status: 502 },
    );
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.set({
    name: TOKEN_COOKIE,
    value: parsed.data.token,
    httpOnly: true,
    sameSite: "lax",
    secure: request.nextUrl.protocol === "https:",
    path: "/",
    maxAge: 60 * 60 * 24 * 7,
  });
  return response;
}
