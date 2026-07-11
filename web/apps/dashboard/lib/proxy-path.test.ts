import { describe, expect, it } from "vitest";

import { resolveUpstreamPath } from "./proxy-path";

describe("resolveUpstreamPath", () => {
  it("allows the spawnd read/write surface", () => {
    expect(resolveUpstreamPath(["runs"])).toBe("runs");
    expect(resolveUpstreamPath(["runs", "run-1", "events", "stream"])).toBe(
      "runs/run-1/events/stream",
    );
    expect(resolveUpstreamPath(["workers"])).toBe("workers");
    expect(resolveUpstreamPath(["templates", "tpl-1", "runs"])).toBe("templates/tpl-1/runs");
    expect(resolveUpstreamPath(["schedules", "sched-1", "status"])).toBe(
      "schedules/sched-1/status",
    );
    expect(resolveUpstreamPath(["clarifications"])).toBe("clarifications");
  });

  it("rejects everything outside the allowlist", () => {
    expect(resolveUpstreamPath([])).toBeNull();
    expect(resolveUpstreamPath(["healthz"])).toBeNull();
    expect(resolveUpstreamPath(["metrics"])).toBeNull();
    expect(resolveUpstreamPath(["webhooks", "github", "tpl"])).toBeNull();
    expect(resolveUpstreamPath(["submissions"])).toBeNull();
  });

  it("rejects traversal and malformed segments", () => {
    expect(resolveUpstreamPath(["runs", ".."])).toBeNull();
    expect(resolveUpstreamPath(["runs", "."])).toBeNull();
    expect(resolveUpstreamPath(["runs", ""])).toBeNull();
    expect(resolveUpstreamPath(["runs", "a/b"])).toBeNull();
  });

  it("encodes segments for the upstream URL", () => {
    expect(resolveUpstreamPath(["runs", "run with space"])).toBe("runs/run%20with%20space");
  });
});
