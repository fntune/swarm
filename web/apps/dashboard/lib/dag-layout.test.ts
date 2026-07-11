import type { Agent } from "@spawnd/api-client";
import { describe, expect, it } from "vitest";

import { layoutDag } from "./dag-layout";

function agent(name: string, dependsOn: string[] = [], status = "pending"): Agent {
  return {
    run_id: "run-1",
    name,
    status,
    type: "worker",
    depends_on: dependsOn,
    input_tokens: 0,
    output_tokens: 0,
    cost_usd: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  } as Agent;
}

describe("layoutDag", () => {
  it("ranks a diamond left to right", () => {
    const { nodes, edges } = layoutDag([
      agent("planner"),
      agent("impl-a", ["planner"], "running"),
      agent("impl-b", ["planner"]),
      agent("reviewer", ["impl-a", "impl-b"]),
    ]);

    const x = Object.fromEntries(nodes.map((node) => [node.id, node.position.x]));
    expect(x.planner).toBeLessThan(x["impl-a"] ?? Number.NaN);
    expect(x["impl-a"]).toBe(x["impl-b"]);
    expect(x["impl-a"] ?? Number.NaN).toBeLessThan(x.reviewer ?? Number.NaN);
    expect(edges).toHaveLength(4);
  });

  it("animates only edges into running agents", () => {
    const { edges } = layoutDag([
      agent("planner", [], "completed"),
      agent("impl-a", ["planner"], "running"),
      agent("impl-b", ["planner"], "pending"),
    ]);

    expect(edges.find((edge) => edge.target === "impl-a")?.animated).toBe(true);
    expect(edges.find((edge) => edge.target === "impl-b")?.animated).toBe(false);
  });

  it("ignores dependencies on unknown agents", () => {
    const { edges } = layoutDag([agent("solo", ["ghost"])]);
    expect(edges).toHaveLength(0);
  });

  it("marks the selected node", () => {
    const { nodes } = layoutDag([agent("a"), agent("b")], "b");
    expect(nodes.find((node) => node.id === "b")?.selected).toBe(true);
    expect(nodes.find((node) => node.id === "a")?.selected).toBe(false);
  });
});
