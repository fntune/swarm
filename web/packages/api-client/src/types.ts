export type RunStatus =
  | "queued"
  | "running"
  | "paused"
  | "completed"
  | "failed"
  | "cost_exceeded"
  | "cancelled";

export type AgentStatus =
  | "pending"
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "timeout"
  | "paused"
  | "cancelled"
  | "cost_exceeded";

export interface Run {
  run_id: string;
  name: string | null;
  status: RunStatus;
  spec?: PlanSpec;
  spec_hash: string | null;
  total_cost_usd: number;
  max_cost_usd: number | null;
  submitted_via: string | null;
  submitted_by: string | null;
  source_repo: string | null;
  source_ref: string | null;
  cancelled_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Agent {
  run_id: string;
  name: string;
  status: AgentStatus;
  type: "worker" | "manager";
  runtime: string | null;
  model: string | null;
  write_allowed: boolean | null;
  prompt_hash: string | null;
  prompt_preview: string | null;
  check_command_hash: string | null;
  check_command_preview: string | null;
  branch: string | null;
  worktree_locator: string | null;
  worker_id: string | null;
  leased_until: string | null;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  max_cost_usd: number | null;
  error: string | null;
  depends_on: string[] | null;
  on_failure: string | null;
  retry_count: number | null;
  retry_attempt: number | null;
  last_error: string | null;
  max_subagents: number | null;
  created_at: string;
  updated_at: string;
}

export interface Attempt {
  id: string;
  run_id: string;
  agent: string;
  attempt_number: number;
  runtime: string | null;
  model: string | null;
  status: string;
  worker_id: string | null;
  heartbeat_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  error_id: string | null;
}

export interface TelemetrySummary {
  trace_span_count: number;
  last_telemetry_error: Record<string, unknown> | null;
}

export interface RunDetail {
  run: Run;
  agents: Agent[];
  attempts: Attempt[];
  telemetry: TelemetrySummary;
}

export interface RunEvent {
  id: string;
  run_id: string;
  agent: string;
  event_type: string;
  data: Record<string, unknown>;
  created_at: string;
}

export interface Check {
  id: number;
  run_id: string;
  agent: string;
  attempt_id: string | null;
  command_hash: string | null;
  command_preview: string | null;
  shell: string | null;
  cwd_locator: string | null;
  exit_code: number | null;
  signal: string | null;
  duration_ms: number | null;
  output_artifact_id: string | null;
  stdout_artifact_id: string | null;
  stderr_artifact_id: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface Artifact {
  id: string;
  run_id: string;
  agent: string | null;
  attempt_id: string | null;
  session_id: string | null;
  invocation_id: string | null;
  kind: string;
  uri: string;
  sha256: string | null;
  size_bytes: number | null;
  redaction_policy: string | null;
  content_type: string | null;
  created_at: string;
}

export interface TraceSpan {
  id: number;
  run_id: string;
  agent: string | null;
  trace_id: string;
  span_id: string;
  parent_span_id: string | null;
  name: string;
  status: string | null;
  started_at: string;
  ended_at: string | null;
  duration_ms: number | null;
  attributes: Record<string, unknown>;
  events: Record<string, unknown>[];
  export_status: string | null;
}

export interface GitProvenance {
  id: number;
  run_id: string;
  agent: string;
  attempt_id: string | null;
  base_ref: string | null;
  remote: string | null;
  base_sha: string | null;
  merge_base_sha: string | null;
  head_sha: string | null;
  branch: string | null;
  commit_sha: string | null;
  pr_url: string | null;
  pr_number: number | null;
  patch_artifact_id: string | null;
  commit_message_preview: string | null;
  changed_files_count: number | null;
  insertions_count: number | null;
  deletions_count: number | null;
  diff_stats: Record<string, unknown> | null;
  created_at: string;
}

export interface TokenUsageRow {
  id: string;
  run_id: string;
  agent: string | null;
  attempt_id: string | null;
  session_id: string | null;
  invocation_id: string | null;
  provider: string;
  model: string | null;
  scope: string;
  input_tokens: number;
  cached_input_tokens: number;
  output_tokens: number;
  reasoning_output_tokens: number;
  total_tokens: number;
  context_window: number | null;
  created_at: string;
}

export interface CostUsageRow {
  id: string;
  run_id: string;
  agent: string | null;
  provider: string;
  model: string | null;
  amount_usd: number;
  source: string;
  created_at: string;
}

export interface AgentUsageRollup {
  agent: string;
  input_tokens: number;
  cached_input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  amount_usd: number;
}

export interface RunUsage {
  token_usage: TokenUsageRow[];
  cost_usage: CostUsageRow[];
  by_agent: AgentUsageRollup[];
}

export interface RuntimeSession {
  id: string;
  attempt_id: string;
  run_id: string;
  agent: string;
  provider: string;
  runtime: string;
  provider_session_id: string | null;
  provider_thread_id: string | null;
  cwd_locator: string | null;
  model: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface RuntimeInvocation {
  id: string;
  session_id: string | null;
  attempt_id: string;
  run_id: string;
  agent: string;
  sequence: number;
  kind: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  exit_code: number | null;
  stop_reason: string | null;
  is_error: boolean;
  final_message_artifact_id: string | null;
}

export interface RuntimeError {
  id: string;
  run_id: string;
  agent: string | null;
  attempt_id: string | null;
  source: string;
  code: string | null;
  message_preview: string | null;
  retryable: boolean | null;
  created_at: string;
}

export interface RunTemplate {
  id: string;
  name: string;
  description: string | null;
  plan_template: string;
  source_repo_template: string | null;
  source_ref_template: string | null;
  created_at: string;
  updated_at: string;
}

export interface Schedule {
  id: string;
  template_id: string;
  name: string;
  status: "active" | "paused";
  interval_seconds: number;
  parameters: Record<string, unknown>;
  next_run_at: string | null;
  last_run_at: string | null;
  last_run_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkerNode {
  worker_id: string;
  hostname: string | null;
  version: string | null;
  started_at: string | null;
  heartbeat_at: string | null;
  capacity: Record<string, unknown> | null;
  status: string;
  stale: boolean;
}

export interface WorkersSnapshot {
  queue_depth: number;
  submission_queue_depth: number;
  workers: WorkerNode[];
}

/** Serialized plan accepted by POST /runs; the backend validates the full shape. */
export interface PlanSpec {
  name: string;
  agents: Record<string, unknown>[];
  defaults?: Record<string, unknown>;
  orchestration?: Record<string, unknown>;
  [key: string]: unknown;
}
