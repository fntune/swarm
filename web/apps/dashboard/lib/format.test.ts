import { describe, expect, it } from "vitest";

import {
  durationBetween,
  formatDurationMs,
  formatTokens,
  formatUsd,
  pollInterval,
  repoLabel,
  runIsCancellable,
  shortSha,
} from "./format";

describe("format helpers", () => {
  it("formats USD", () => {
    expect(formatUsd(0)).toBe("$0.00");
    expect(formatUsd(4.2)).toBe("$4.20");
  });

  it("formats token counts", () => {
    expect(formatTokens(950)).toBe("950");
    expect(formatTokens(41_200)).toBe("41.2k");
    expect(formatTokens(2_500_000)).toBe("2.5M");
  });

  it("formats durations", () => {
    expect(formatDurationMs(420)).toBe("420ms");
    expect(formatDurationMs(12_300)).toBe("12.3s");
    expect(formatDurationMs(95_000)).toBe("1m 35s");
    expect(formatDurationMs(3_750_000)).toBe("1h 2m");
  });

  it("computes duration between timestamps", () => {
    expect(durationBetween("2026-01-01T00:00:00Z", "2026-01-01T00:01:35Z")).toBe("1m 35s");
    expect(durationBetween(null, null)).toBeNull();
    expect(durationBetween("2026-01-01T00:01:00Z", "2026-01-01T00:00:00Z")).toBeNull();
  });

  it("labels repos compactly", () => {
    expect(repoLabel("https://github.com/acme/widgets.git")).toBe("github.com/acme/widgets");
    expect(repoLabel("git@github.com:acme/widgets.git")).toBe("github.com:acme/widgets");
    expect(repoLabel("/Users/dev/projects/deep/nested/repo")).toBe("…/nested/repo");
    expect(repoLabel(null)).toBe("—");
  });

  it("shortens SHAs", () => {
    expect(shortSha("0123456789abcdef")).toBe("01234567");
    expect(shortSha(null)).toBe("—");
  });

  it("picks poll cadence from run activity", () => {
    expect(pollInterval(["completed", "running"])).toBe(5_000);
    expect(pollInterval(["completed", "failed"])).toBe(30_000);
  });

  it("allows operators to cancel active and paused runs", () => {
    expect(runIsCancellable("running")).toBe(true);
    expect(runIsCancellable("paused")).toBe(true);
    expect(runIsCancellable("completed")).toBe(false);
  });
});
