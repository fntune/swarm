import { describe, expect, it } from "vitest";

import { authorizeDashboardRequest, dashboardAuthMode } from "./auth";

const TAILSCALE_ENV = {
  SPAWND_API_TOKEN: "server-token",
  SPAWND_DASHBOARD_AUTH_MODE: "tailscale",
  SPAWND_TAILSCALE_ALLOWED_USERS: "operator@example.com, Second@Example.com",
};

describe("dashboard auth", () => {
  it("defaults to token mode", () => {
    expect(dashboardAuthMode({})).toBe("token");
  });

  it("rejects unsupported modes", () => {
    expect(() => dashboardAuthMode({ SPAWND_DASHBOARD_AUTH_MODE: "none" })).toThrow(
      "Unsupported SPAWND_DASHBOARD_AUTH_MODE",
    );
  });

  it("uses the operator cookie in token mode", () => {
    expect(
      authorizeDashboardRequest({
        headers: new Headers(),
        cookieToken: "cookie-token",
        environment: {},
      }),
    ).toEqual({ ok: true, mode: "token", token: "cookie-token" });
  });

  it("requires the operator cookie in token mode", () => {
    expect(authorizeDashboardRequest({ headers: new Headers(), environment: {} })).toMatchObject({
      ok: false,
      mode: "token",
      status: 401,
    });
  });

  it("authorizes an allowlisted Tailscale identity case-insensitively", () => {
    const headers = new Headers({ "Tailscale-User-Login": "second@example.com" });
    expect(authorizeDashboardRequest({ headers, environment: TAILSCALE_ENV })).toEqual({
      ok: true,
      mode: "tailscale",
      token: "server-token",
      userLogin: "second@example.com",
    });
  });

  it("requires a Tailscale identity", () => {
    expect(
      authorizeDashboardRequest({ headers: new Headers(), environment: TAILSCALE_ENV }),
    ).toMatchObject({ ok: false, mode: "tailscale", status: 401 });
  });

  it("rejects a Tailscale identity outside the allowlist", () => {
    const headers = new Headers({ "Tailscale-User-Login": "intruder@example.com" });
    expect(authorizeDashboardRequest({ headers, environment: TAILSCALE_ENV })).toMatchObject({
      ok: false,
      mode: "tailscale",
      status: 403,
    });
  });

  it("fails closed when the server token is missing", () => {
    expect(
      authorizeDashboardRequest({
        headers: new Headers({ "Tailscale-User-Login": "operator@example.com" }),
        environment: {
          SPAWND_DASHBOARD_AUTH_MODE: "tailscale",
          SPAWND_TAILSCALE_ALLOWED_USERS: "operator@example.com",
        },
      }),
    ).toMatchObject({ ok: false, mode: "tailscale", status: 503 });
  });

  it("fails closed when the allowlist is missing", () => {
    expect(
      authorizeDashboardRequest({
        headers: new Headers({ "Tailscale-User-Login": "operator@example.com" }),
        environment: {
          SPAWND_API_TOKEN: "server-token",
          SPAWND_DASHBOARD_AUTH_MODE: "tailscale",
        },
      }),
    ).toMatchObject({ ok: false, mode: "tailscale", status: 503 });
  });
});
