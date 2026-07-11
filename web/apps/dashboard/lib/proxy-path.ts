const ALLOWED_PREFIXES = new Set(["runs", "templates", "schedules", "workers", "clarifications"]);

/**
 * Maps proxy path segments to an upstream spawnd API path. Returns null for
 * anything outside the allowlisted read/write surface.
 */
export function resolveUpstreamPath(segments: string[]): string | null {
  if (segments.length === 0) return null;
  const head = segments[0];
  if (!head || !ALLOWED_PREFIXES.has(head)) return null;
  for (const segment of segments) {
    if (!segment || segment === "." || segment === ".." || segment.includes("/")) return null;
  }
  return segments.map(encodeURIComponent).join("/");
}
