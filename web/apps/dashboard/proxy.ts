import { type NextRequest, NextResponse } from "next/server";

import { TOKEN_COOKIE } from "@/lib/auth-cookie";
import { authorizeDashboardRequest, dashboardAuthMode } from "@/lib/server/auth";
import { validateApiToken } from "@/lib/server/token";

export default async function proxy(request: NextRequest) {
  const token = request.cookies.get(TOKEN_COOKIE)?.value;
  const isLogin = request.nextUrl.pathname === "/login";
  if (dashboardAuthMode() === "tailscale") {
    const authorization = authorizeDashboardRequest({ headers: request.headers });
    if (!authorization.ok) {
      return new NextResponse(authorization.detail, { status: authorization.status });
    }
    if (isLogin) {
      const url = request.nextUrl.clone();
      url.pathname = "/";
      url.search = "";
      return NextResponse.redirect(url);
    }
    return NextResponse.next();
  }
  if (!token && !isLogin) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = "";
    return NextResponse.redirect(url);
  }
  if (token && isLogin) {
    const validation = await validateApiToken(token);
    if (validation.ok) {
      const url = request.nextUrl.clone();
      url.pathname = "/";
      url.search = "";
      return NextResponse.redirect(url);
    }
    const response = NextResponse.next();
    if (validation.status === 401) response.cookies.delete(TOKEN_COOKIE);
    return response;
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next|favicon\\.ico|.*\\..*).*)"],
};
