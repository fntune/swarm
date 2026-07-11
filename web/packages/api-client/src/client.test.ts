import { describe, expect, it } from "vitest";

import { createSpawndClient } from "./client";
import { SpawndApiError } from "./errors";

function fetchStub(handler: (url: string, init: RequestInit) => Response) {
  const calls: { url: string; init: RequestInit }[] = [];
  const impl = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init: init ?? {} });
    return handler(url, init ?? {});
  }) as typeof fetch;
  return { impl, calls };
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

describe("createSpawndClient", () => {
  it("attaches bearer token and builds query strings", async () => {
    const { impl, calls } = fetchStub(() => json([]));
    const client = createSpawndClient({ baseUrl: "http://api:8765", token: "tok", fetch: impl });

    await client.runs.list({ limit: 10, offset: 0, status: "running" });

    expect(calls).toHaveLength(1);
    const [call] = calls;
    if (!call) throw new Error("expected a fetch call");
    expect(call.url).toBe("http://api:8765/runs?limit=10&offset=0&status=running");
    expect(new Headers(call.init.headers).get("authorization")).toBe("Bearer tok");
  });

  it("posts JSON bodies with content type", async () => {
    const { impl, calls } = fetchStub(() => json({ run_id: "run-1" }));
    const client = createSpawndClient({ baseUrl: "http://api:8765/", token: "tok", fetch: impl });

    const result = await client.runs.submit({ plan: { name: "p", agents: [] }, run_id: "run-1" });

    expect(result.run_id).toBe("run-1");
    const [call] = calls;
    if (!call) throw new Error("expected a fetch call");
    expect(call.url).toBe("http://api:8765/runs");
    expect(call.init.method).toBe("POST");
    expect(new Headers(call.init.headers).get("content-type")).toBe("application/json");
    expect(JSON.parse(String(call.init.body))).toEqual({
      plan: { name: "p", agents: [] },
      run_id: "run-1",
    });
  });

  it("maps spawnd string-list 422 details", async () => {
    const { impl } = fetchStub(() =>
      json({ detail: ["Agent a depends on unknown agent: missing"] }, 422),
    );
    const client = createSpawndClient({ baseUrl: "http://api:8765", fetch: impl });

    const error = await client.runs
      .submit({ plan: { name: "p", agents: [] } })
      .catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(SpawndApiError);
    const apiError = error as SpawndApiError;
    expect(apiError.status).toBe(422);
    expect(apiError.validationMessages).toEqual(["Agent a depends on unknown agent: missing"]);
  });

  it("maps pydantic 422 detail objects to readable messages", async () => {
    const { impl } = fetchStub(() =>
      json(
        {
          detail: [
            { loc: ["body", "plan", "agents", 0, "name"], msg: "Field required", type: "missing" },
          ],
        },
        422,
      ),
    );
    const client = createSpawndClient({ baseUrl: "http://api:8765", fetch: impl });

    const error = (await client.runs
      .submit({ plan: { name: "p", agents: [] } })
      .catch((caught: unknown) => caught)) as SpawndApiError;

    expect(error.validationMessages).toEqual(["plan.agents.0.name: Field required"]);
  });

  it("returns raw responses for artifact content", async () => {
    const { impl } = fetchStub(
      () => new Response("log line", { status: 200, headers: { "Content-Type": "text/plain" } }),
    );
    const client = createSpawndClient({ baseUrl: "http://api:8765", token: "tok", fetch: impl });

    const response = await client.runs.artifactContent("run-1", "artifact-1");

    expect(response.status).toBe(200);
    expect(await response.text()).toBe("log line");
  });

  it("builds the SSE stream path with replay", () => {
    const client = createSpawndClient({ baseUrl: "http://api:8765" });
    expect(client.runs.eventStreamPath("run-1", { replay: 50 })).toBe(
      "runs/run-1/events/stream?replay=50",
    );
    expect(client.runs.eventStreamPath("run-1")).toBe("runs/run-1/events/stream");
  });
});
