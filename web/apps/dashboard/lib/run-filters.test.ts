import { describe, expect, it } from "vitest";

import { parseRunFilter, statusesForRunFilter } from "./run-filters";

describe("run filters", () => {
  it("maps failure filters to both terminal failure statuses", () => {
    expect(statusesForRunFilter("failed")).toEqual(["failed", "cost_exceeded"]);
  });

  it("falls back to the unfiltered view for unknown query values", () => {
    expect(parseRunFilter("unknown")).toBe("all");
    expect(statusesForRunFilter("all")).toBeUndefined();
  });
});
