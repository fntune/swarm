import { type NextRequest, NextResponse } from "next/server";

import { TOKEN_COOKIE } from "@/lib/auth-cookie";

export default function proxy(request: NextRequest) {
  const token = request.cookies.get(TOKEN_COOKIE)?.value;
  const isLogin = request.nextUrl.pathname === "/login";
  if (!token && !isLogin) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = "";
    return NextResponse.redirect(url);
  }
  if (token && isLogin) {
    const url = request.nextUrl.clone();
    url.pathname = "/";
    url.search = "";
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next|favicon\\.ico|.*\\..*).*)"],
};
