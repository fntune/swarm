export type DashboardAuthMode = "token" | "tailscale";

export interface DashboardAuthEnvironment {
  [name: string]: string | undefined;
  SPAWND_API_TOKEN?: string;
  SPAWND_DASHBOARD_AUTH_MODE?: string;
  SPAWND_TAILSCALE_ALLOWED_USERS?: string;
}

export type DashboardAuthorization =
  | {
      ok: true;
      mode: DashboardAuthMode;
      token: string;
      userLogin?: string;
    }
  | {
      ok: false;
      mode: DashboardAuthMode;
      detail: string;
      status: 401 | 403 | 503;
    };

const TAILSCALE_USER_LOGIN_HEADER = "tailscale-user-login";

/** Resolve the dashboard authentication mode, rejecting unknown configuration. */
export function dashboardAuthMode(
  environment: DashboardAuthEnvironment = process.env,
): DashboardAuthMode {
  const mode = environment.SPAWND_DASHBOARD_AUTH_MODE?.trim() || "token";
  if (mode !== "token" && mode !== "tailscale") {
    throw new Error(`Unsupported SPAWND_DASHBOARD_AUTH_MODE: ${mode}`);
  }
  return mode;
}

/** Return the Tailscale login injected by Serve, if present. */
export function tailscaleUserLogin(headers: Headers): string | null {
  return headers.get(TAILSCALE_USER_LOGIN_HEADER)?.trim() || null;
}

/** Resolve the API credential after authenticating the dashboard request. */
export function authorizeDashboardRequest({
  headers,
  cookieToken,
  environment = process.env,
}: {
  headers: Headers;
  cookieToken?: string;
  environment?: DashboardAuthEnvironment;
}): DashboardAuthorization {
  const mode = dashboardAuthMode(environment);
  if (mode === "token") {
    if (!cookieToken) {
      return { ok: false, mode, detail: "Unauthorized", status: 401 };
    }
    return { ok: true, mode, token: cookieToken };
  }

  const token = environment.SPAWND_API_TOKEN?.trim();
  if (!token) {
    return {
      ok: false,
      mode,
      detail: "Tailscale authentication requires SPAWND_API_TOKEN",
      status: 503,
    };
  }
  const allowedUsers = new Set(
    (environment.SPAWND_TAILSCALE_ALLOWED_USERS ?? "")
      .split(",")
      .map((user) => user.trim().toLowerCase())
      .filter(Boolean),
  );
  if (allowedUsers.size === 0) {
    return {
      ok: false,
      mode,
      detail: "Tailscale authentication requires SPAWND_TAILSCALE_ALLOWED_USERS",
      status: 503,
    };
  }

  const userLogin = tailscaleUserLogin(headers);
  if (!userLogin) {
    return { ok: false, mode, detail: "Tailscale identity is required", status: 401 };
  }
  if (!allowedUsers.has(userLogin.toLowerCase())) {
    return { ok: false, mode, detail: "Tailscale identity is not authorized", status: 403 };
  }
  return { ok: true, mode, token, userLogin };
}
