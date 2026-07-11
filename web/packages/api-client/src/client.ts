import { SpawndApiError } from "./errors";
import type {
  Artifact,
  Check,
  GitProvenance,
  PlanSpec,
  Run,
  RunDetail,
  RunEvent,
  RunTemplate,
  RuntimeError,
  RuntimeInvocation,
  RuntimeSession,
  RunUsage,
  Schedule,
  TraceSpan,
  WorkersSnapshot,
} from "./types";

export interface SpawndClientOptions {
  baseUrl: string;
  token?: string;
  fetch?: typeof fetch;
}

type Query = Record<string, string | number | boolean | null | undefined>;

function buildUrl(baseUrl: string, path: string, query?: Query): string {
  const url = new URL(path.replace(/^\//, ""), baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

export function createSpawndClient(options: SpawndClientOptions) {
  const fetchImpl = options.fetch ?? fetch;

  async function raw(path: string, init: RequestInit = {}, query?: Query): Promise<Response> {
    const headers = new Headers(init.headers);
    if (options.token) headers.set("Authorization", `Bearer ${options.token}`);
    if (init.body !== undefined && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    const response = await fetchImpl(buildUrl(options.baseUrl, path, query), {
      ...init,
      headers,
      cache: "no-store",
    });
    if (!response.ok) {
      throw await SpawndApiError.fromResponse(response);
    }
    return response;
  }

  async function request<T>(path: string, init: RequestInit = {}, query?: Query): Promise<T> {
    const response = await raw(path, init, query);
    return (await response.json()) as T;
  }

  return {
    runs: {
      list: (query?: { limit?: number; offset?: number; status?: string }) =>
        request<Run[]>("runs", {}, query),
      get: (runId: string) => request<RunDetail>(`runs/${runId}`),
      submit: (body: {
        plan: PlanSpec;
        run_id?: string;
        source_repo?: string;
        source_ref?: string;
      }) => request<{ run_id: string }>("runs", { method: "POST", body: JSON.stringify(body) }),
      cancel: (runId: string) =>
        request<{ cancelled: number }>(`runs/${runId}/cancel`, { method: "POST" }),
      resume: (runId: string) =>
        request<{ run_id: string; agent: string; status: string }[]>(`runs/${runId}/resume`, {
          method: "POST",
        }),
      events: (runId: string, query?: { limit?: number }) =>
        request<RunEvent[]>(`runs/${runId}/events`, {}, query),
      checks: (runId: string, query?: { agent?: string }) =>
        request<Check[]>(`runs/${runId}/checks`, {}, query),
      artifacts: (runId: string, query?: { agent?: string }) =>
        request<Artifact[]>(`runs/${runId}/artifacts`, {}, query),
      artifactContent: (runId: string, artifactId: string) =>
        raw(`runs/${runId}/artifacts/${artifactId}/content`),
      traces: (runId: string, query?: { agent?: string }) =>
        request<TraceSpan[]>(`runs/${runId}/traces`, {}, query),
      provenance: (runId: string, query?: { agent?: string }) =>
        request<GitProvenance[]>(`runs/${runId}/provenance`, {}, query),
      usage: (runId: string, query?: { agent?: string }) =>
        request<RunUsage>(`runs/${runId}/usage`, {}, query),
      sessions: (runId: string, query?: { agent?: string }) =>
        request<RuntimeSession[]>(`runs/${runId}/sessions`, {}, query),
      invocations: (runId: string, query?: { agent?: string }) =>
        request<RuntimeInvocation[]>(`runs/${runId}/invocations`, {}, query),
      errors: (runId: string, query?: { agent?: string }) =>
        request<RuntimeError[]>(`runs/${runId}/errors`, {}, query),
      clarifications: (runId: string) => request<RunEvent[]>(`runs/${runId}/clarifications`),
      answerClarification: (runId: string, clarificationId: string, response: string) =>
        request<{ clarification_id: string; status: string }>(
          `runs/${runId}/clarifications/${clarificationId}/response`,
          { method: "POST", body: JSON.stringify({ response }) },
        ),
      /** Upstream SSE path; consumed through the dashboard proxy, not EventSource-direct. */
      eventStreamPath: (runId: string, query?: { replay?: number }) => {
        const replay = query?.replay;
        return `runs/${runId}/events/stream${replay !== undefined ? `?replay=${replay}` : ""}`;
      },
    },
    templates: {
      list: (query?: { limit?: number }) => request<RunTemplate[]>("templates", {}, query),
      create: (body: {
        id: string;
        name: string;
        plan_template: string;
        description?: string;
        source_repo_template?: string;
        source_ref_template?: string;
      }) =>
        request<{ template_id: string }>("templates", {
          method: "POST",
          body: JSON.stringify(body),
        }),
      run: (templateId: string, body: { parameters?: Record<string, unknown>; run_id?: string }) =>
        request<{ run_id: string }>(`templates/${templateId}/runs`, {
          method: "POST",
          body: JSON.stringify(body),
        }),
    },
    schedules: {
      list: (query?: { limit?: number }) => request<Schedule[]>("schedules", {}, query),
      create: (body: {
        id: string;
        template_id: string;
        name: string;
        interval_seconds: number;
        parameters?: Record<string, unknown>;
        status?: "active" | "paused";
      }) =>
        request<{ schedule_id: string }>("schedules", {
          method: "POST",
          body: JSON.stringify(body),
        }),
      setStatus: (scheduleId: string, status: "active" | "paused") =>
        request<{ schedule_id: string; status: string }>(`schedules/${scheduleId}/status`, {
          method: "PATCH",
          body: JSON.stringify({ status }),
        }),
    },
    workers: {
      get: () => request<WorkersSnapshot>("workers"),
    },
    clarifications: {
      list: (query?: { limit?: number }) => request<RunEvent[]>("clarifications", {}, query),
    },
  };
}

export type SpawndClient = ReturnType<typeof createSpawndClient>;
