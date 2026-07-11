import { apiBaseUrl } from "./config";

export type TokenValidation = { ok: true } | { ok: false; error: string; status: 401 | 502 };

/** Validate an operator token against the deployed API. */
export async function validateApiToken(token: string): Promise<TokenValidation> {
  let upstream: Response;
  try {
    upstream = await fetch(`${apiBaseUrl()}/workers`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
  } catch {
    return { ok: false, error: "spawnd API is unreachable", status: 502 };
  }
  if (upstream.status === 401) {
    return { ok: false, error: "Invalid API token", status: 401 };
  }
  if (!upstream.ok) {
    return {
      ok: false,
      error: `spawnd API error (status ${upstream.status})`,
      status: 502,
    };
  }
  return { ok: true };
}
