import { type NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { TOKEN_COOKIE } from "@/lib/auth-cookie";
import { dashboardAuthMode } from "@/lib/server/auth";
import { validateApiToken } from "@/lib/server/token";

const LoginBody = z.object({ token: z.string().min(1) });

export async function POST(request: NextRequest) {
  if (dashboardAuthMode() === "tailscale") {
    return NextResponse.json(
      { error: "Token login is disabled when Tailscale authentication is enabled" },
      { status: 409 },
    );
  }
  const parsed = LoginBody.safeParse(await request.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: "API token is required" }, { status: 400 });
  }

  const validation = await validateApiToken(parsed.data.token);
  if (!validation.ok) {
    return NextResponse.json({ error: validation.error }, { status: validation.status });
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
