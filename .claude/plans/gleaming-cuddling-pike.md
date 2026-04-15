# swarm multi-runtime restructure

## Context

`~/dev/swarm` is a Python multi-agent orchestration framework currently hardcoded to the Claude Agent SDK. The goal: make it run **OpenAI Agents SDK workers** as a first-class second runtime, add a **live mode** for single-run agent handoffs without YAML/SQLite ceremony, and — critically — **restructure the package aggressively now, while it's pre-production**, rather than bolt features onto the existing shape.

### What changed vs the earlier draft

The earlier draft of this plan treated the work as a cautious 4-phase refactor with a "zero behavior change" Phase 1 and back-compat shims preserving `run_worker`/`run_manager` re-exports, the `session_id` column name, and the existing `AgentConfig` shape. The user has now explicitly said: *"Treat this entire plan as one atomic and breaking change. The current codebase is not in production. If we can cut deeper slices for better modularity, separation of concerns, and hierarchy, we should do that now."*

This unlocks structural changes the earlier draft deferred:
- **Delete `runtime/` as a top-level axis.** Today's `runtime/executor.py` is simultaneously vendor adapter, prompt builder, DB mutator, and log writer ([executor.py:13,72,101,125](/Users/sour4bh/dev/swarm/swarm/runtime/executor.py)). Split along concerns, not along "runtime stuff goes here."
- **Batch vs live are sibling packages.** SQLite, DAG scheduling, merge, and log files are batch-only. Pipeline/handoff and in-memory coordination are live-only. Forcing both through one "runtime" layer is what makes the current code cramped.
- **Adapters as subpackages.** Each vendor (Claude, OpenAI, mock) owns its own executor + tool wrapper + capability map + code-tool implementations. Flat `adapters/claude.py` would re-create today's `tools/factory.py` cramping problem.
- **Merge `Toolset`/`RoleTemplate` → `AgentProfile`.** A role is conceptually a named toolset + system prompt + model defaults. Two dataclasses for one idea is duplication.
- **Replace `AgentConfig` with `ResolvedAgent` + `RunContext`.** Today `AgentConfig` leaks workspace, env, parent lineage, and shared context into every layer ([executor.py:37](/Users/sour4bh/dev/swarm/swarm/runtime/executor.py)). A resolved-agent value (immutable, from plan spec) plus a run context (mutable, per-execution services) is the clean shape.
- **`Workspace` ADT up front.** One-agent-per-worktree is baked into config, scheduler, DB schema, and merge cleanup. Use `Workspace = GitWorktree | Cwd | TempDir` now, and in batch store `workspace_id` (not raw `worktree` on the agent row).
- **`CoordinationBackend` protocol, not just a message bus.** `request_clarification` polls SQLite for replies ([tools/worker.py:20](/Users/sour4bh/dev/swarm/swarm/tools/worker.py)); `spawn_worker` inserts child agents directly ([tools/manager.py:38](/Users/sour4bh/dev/swarm/swarm/tools/manager.py)). That's more than pub/sub — it's supervisor ops plus request/reply. Abstract it. Batch implements it via SQLite; live implements it via asyncio queues.
- **Split the batch schema into `nodes`, `attempts`, `workspaces`.** The current `agents` row mixes immutable config (prompt, deps, check, model) with mutable runtime state (status, iteration, cost, session_id), which is why retry currently mutates the same row in place ([scheduler.py:305](/Users/sour4bh/dev/swarm/swarm/runtime/scheduler.py)). Split to unblock retry history and shared-workspace patterns.
- **Delete `session_id` entirely.** It's captured transiently in `run_worker` ([executor.py:145,283](/Users/sour4bh/dev/swarm/swarm/runtime/executor.py)) but never persisted back or used for orchestration. Pure dead state.
- **Delete all migration code.** Pre-production, fresh schemas only. Fail fast if a legacy DB is detected; tell the user to `swarm clean --all`.
- **Event stream, not `Observer` protocol.** One `emit(SwarmEvent)` sink. Batch writes events to SQLite/log files; live prints or forwards them. Fat observer protocols accrete adapter-specific hooks.
- **Delete `run_worker_mock`, replace with `MockExecutor` adapter.** Batch and live both use the same execution surface.
- **Delete `gitops/merge.py:spawn_resolver` entirely (confirmed).** It imports `run_worker` directly and hardcodes `Path.cwd()` — exactly the shape we're removing. Dropped from the `auto` conflict resolution strategy for this PR; `merge --strategy auto` falls back to `manual` when a conflict needs an agent, with a clear error message. Re-added in a follow-up PR once a stable scheduler API for one-off sub-plans exists.

### What the restructure unlocks

The user's `~/.claude/skills/` directory (notably `debt`, `audit-fix-loop`, `swarm-audit`, `evolve`) already encodes cross-vendor workflows that orchestrate Claude + Codex/GPT-5 interactively inside Claude Code sessions. Today they can't run as batch swarm plans because swarm has no OpenAI runtime. After this restructure:

- A YAML plan can mix `runtime: claude` and `runtime: openai` agents with dependencies between them.
- A Python script can `from swarm.live import pipeline` and run a Claude→OpenAI handoff in 20 lines, no YAML.
- Role = profile, so a `reviewer` profile is read-only on both vendors via one declaration.
- Retry history is queryable (previous attempts persist as rows in `attempts`), unblocking audit/optimization reports.
- Shared workspaces (N reviewers reading one worktree) are possible because workspace is its own entity, not baked into the agent row.

### Scope envelope

**In scope for this atomic change:**
- Full package restructure (new module tree below)
- `AgentProfile` / `ResolvedAgent` / `RunContext` / `ExecutionResult` / `CoordinationBackend` / `Workspace` / event stream primitives
- Claude adapter ported to the new shape
- OpenAI adapter added (new optional dep)
- Mock adapter extracted
- Batch mode backed by SQLite (`nodes` / `attempts` / `workspaces` tables) and the `SqliteCoordinationBackend`
- Live mode backed by the `InMemoryCoordinationBackend`, two examples: `cross_check.py`, `debt.py`
- CLI commands updated to the new paths (no new commands in this cut, but `swarm run`/`status`/`logs`/`merge`/`resume`/`clean`/`dashboard`/`db`/`roles` all work)
- Tests updated (nothing preserved from back-compat; everything rewritten to the new shape)

**Out of scope for this atomic change (deferred to follow-ups):**
- Cross-vendor OTel tracing unification — nice to have, not load-bearing
- `swarm report <run_id>` — the optimization report from the `swarm-audit` skill
- MCP bridge (shared tool pool exposed as in-process MCP to Claude and stdio MCP to OpenAI)
- Skill → plan YAML converter
- Durable pause/resume with external hooks (`createHook`-style)
- Manager-in-live-mode (the in-memory backend simply doesn't support `CoordOp.SPAWN` for now; add later)

**Note on file location**: this plan is written to `~/.claude/plans/gleaming-cuddling-pike.md` to satisfy plan mode. Canonical home after plan mode exits is `~/dev/swarm/.claude/plans/gleaming-cuddling-pike.md`. Sync after approval.

---

## Target architecture

```
swarm/
  cli.py                       Click entrypoint; dispatches to batch/live
  core/
    agent.py                   AgentRequest (YAML-facing), ResolvedAgent, Limits
    profiles.py                AgentProfile, PROFILE_REGISTRY, builtin profiles
    capabilities.py            Capability enum, CANONICAL_CAPABILITY_ORDER
    execution.py               Executor ABC, RunContext, ExecutionResult, AdapterRegistry
    coordination.py            CoordOp enum, CoordinationBackend Protocol, CoordResult
    events.py                  SwarmEvent ADT, EventSink Protocol, event types
    workspace.py               Workspace ADT, WorkspaceProvider Protocol
    errors.py                  SwarmError hierarchy
  adapters/
    claude/
      __init__.py              registers ClaudeExecutor
      executor.py              ClaudeExecutor(Executor)
      tools.py                 Claude @tool wrappers around CoordOps
      builtins.py              CLAUDE_CAPABILITY_MAP, _expand_tools()
    openai/
      __init__.py              registers OpenAIExecutor (conditional on import)
      executor.py              OpenAIExecutor(Executor)
      tools.py                 OpenAI @function_tool wrappers around CoordOps
      code_tools.py            read_file/edit_file/run_shell/grep/glob @function_tools
    mock/
      __init__.py              registers MockExecutor
      executor.py              MockExecutor(Executor) — replaces run_worker_mock
  batch/
    plan.py                    PlanSpec, PlanDefaults, resolution rules
    input.py                   YAML parse, inline-plan builder, validation
    dag.py                     Dependency graph, topological sort, cycle detection
    scheduler.py               Parallel execution, circuit breaker, stuck detection
    sqlite.py                  SqliteCoordinationBackend + batch persistence + schema
    logs.py                    Per-agent log file management
    merge.py                   Branch consolidation, conflict resolution (sans spawn_resolver)
  live/
    pipeline.py                pipeline(), handoff()
    bridge.py                  as_claude_tool(), as_openai_tool() — split bridge helpers
    in_memory.py               InMemoryCoordinationBackend (asyncio queues)
  workspaces/
    git.py                     GitWorktree provider
    cwd.py                     Cwd provider
    temp.py                    TempDir provider
  examples/
    cross_check.py             Claude generator → OpenAI reviewer (hello world)
    debt.py                    Port of the `debt` skill as a live pipeline
```

**Gone from the tree:**
- `swarm/runtime/` — split into `adapters/`, `batch/`, `core/execution.py`
- `swarm/tools/` — split into `adapters/<vendor>/tools.py` (vendor wrappers) and `core/coordination.py` (backend protocol)
- `swarm/models/` — `specs.py` moves to `core/agent.py` + `batch/plan.py`; `state.py` is deleted (unused)
- `swarm/storage/` — `db.py` moves to `batch/sqlite.py`; `logs.py` moves to `batch/logs.py`; `paths.py` absorbed into `batch/sqlite.py`
- `swarm/gitops/` — `worktrees.py` moves to `workspaces/git.py`; `merge.py` moves to `batch/merge.py`
- `swarm/io/` — `parser.py` / `plan_builder.py` / `validation.py` collapse into `batch/input.py`
- `swarm/roles.py` — becomes `core/profiles.py`

---

## Core primitives

Designing these right is the load-bearing work of this refactor. Everything else is mechanical file moves.

### `core/agent.py`

```python
from dataclasses import dataclass, field
from typing import Any, Literal
from swarm.core.capabilities import Capability
from swarm.core.profiles import AgentProfile

@dataclass
class Limits:
    """Hard caps on an agent run. Resolved once from plan defaults + agent overrides."""
    max_iterations: int = 30
    max_cost_usd: float = 5.0

@dataclass(frozen=True)
class AgentRequest:
    """YAML-facing authoring shape. Produced by batch/input.py or by hand in live mode."""
    name: str
    prompt: str
    profile: str | None = None              # references PROFILE_REGISTRY
    runtime: Literal["claude","openai","mock"] | None = None
    model: str | None = None
    capabilities: frozenset[Capability] | None = None   # override profile capabilities
    limits: Limits | None = None
    check: str | None = None
    depends_on: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    output_schema: dict | None = None       # for OpenAI structured output
    parent: str | None = None               # set by scheduler for child agents

@dataclass(frozen=True)
class ResolvedAgent:
    """Fully resolved, immutable snapshot handed to an Executor. No defaults fall-through."""
    name: str
    prompt: str
    runtime: str
    model: str
    profile: AgentProfile
    capabilities: frozenset[Capability]
    limits: Limits
    check: str
    env: dict[str, str]
    output_schema: dict | None
    parent: str | None
    tree_path: str                          # "root.mgr.worker-1"
```

### `core/profiles.py`

```python
from dataclasses import dataclass, field
from swarm.core.capabilities import Capability, DEFAULT_CODING_CAPS, READONLY_CAPS

@dataclass(frozen=True)
class AgentProfile:
    name: str
    description: str
    prompt_preamble: str
    capabilities: frozenset[Capability] = field(default_factory=frozenset)
    coord_ops: frozenset[str] = field(default_factory=frozenset)   # which CoordOps this profile can call
    default_model: str | None = None
    default_check: str | None = None
    read_only: bool = False

PROFILE_REGISTRY: dict[str, AgentProfile] = {}

def register_profile(p: AgentProfile) -> None:
    PROFILE_REGISTRY[p.name] = p

def get_profile(name: str) -> AgentProfile:
    return PROFILE_REGISTRY[name]

# Builtin profiles — the 7 roles collapse to profiles with explicit capabilities and coord_ops.
# Reviewer becomes read-only-plus-shell (caps = FILE_READ | GLOB | GREP | SHELL, read_only=True)
# so it can still run tests/linters. Manager becomes an `orchestrator` profile with
# coord_ops = {spawn, status, respond, cancel, complete, pending_clarifications, mark_plan_complete}.
# `implementer` is the default profile when an agent doesn't pick one.
```

The 7 existing role names (`architect`, `implementer`, `tester`, `reviewer`, `debugger`, `refactorer`, `documenter`) all port to profiles. `implementer` gets the default coding caps. Manager-style work is a new `orchestrator` profile with `coord_ops={"spawn","status","respond","complete"}` and full coding caps. The old `type: manager` field goes away.

**Reviewer profile — confirmed read-only-plus-shell.** `reviewer` gets `read_only=True` and `capabilities = {FILE_READ, GLOB, GREP, SHELL}`. No `FILE_WRITE`, no `FILE_EDIT`. The `SHELL` capability is retained so a reviewer can run `pytest`, `ruff check`, `tsc --noEmit`, etc., to verify the code it's reviewing — that's the whole point of review, not just eyeballing diffs. `READONLY_CAPS` in `core/capabilities.py` is therefore `{FILE_READ, GLOB, GREP, SHELL}`, not `{FILE_READ, GLOB, GREP}`. If anyone wants a truly no-side-effect reviewer, they override `capabilities:` explicitly in the plan. This is the one intentional behavior change; today's reviewer has full coding caps.

### `core/execution.py`

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar, Literal
from swarm.core.agent import ResolvedAgent
from swarm.core.coordination import CoordinationBackend
from swarm.core.events import EventSink
from swarm.core.workspace import Workspace

@dataclass
class RunContext:
    """Per-execution services handed to an adapter. Not stored; constructed fresh per run."""
    run_id: str
    workspace: Workspace
    coord: CoordinationBackend
    events: EventSink
    cwd: str                    # resolved from workspace

@dataclass
class ExecutionResult:
    status: Literal["completed","failed","timeout","cancelled","cost_exceeded"]
    final_text: str
    cost_usd: float
    cost_source: Literal["sdk","estimated"]
    vendor_session_id: str | None = None
    structured_output: Any = None
    files_modified: list[str] | None = None
    error: str | None = None

class Executor(ABC):
    runtime: ClassVar[str]
    @abstractmethod
    async def run(self, agent: ResolvedAgent, ctx: RunContext) -> ExecutionResult: ...

EXECUTOR_REGISTRY: dict[str, Executor] = {}

def register(executor: Executor) -> None:
    EXECUTOR_REGISTRY[executor.runtime] = executor

def get_executor(runtime: str) -> Executor:
    if runtime not in EXECUTOR_REGISTRY:
        raise KeyError(f"No executor registered for runtime={runtime}. Registered: {list(EXECUTOR_REGISTRY)}")
    return EXECUTOR_REGISTRY[runtime]
```

Two things to notice vs the earlier draft:
- Executor takes `(agent, ctx)`, not `(config, toolset, observer)`. The agent is immutable and self-contained. The ctx carries everything mutable.
- Manager vs worker vanishes as a distinction. An orchestrator profile that has `coord_ops={"spawn",...}` gets different coord tools wired up by the adapter, but it's still one `Executor.run` call.

### `core/coordination.py`

```python
from enum import Enum
from typing import Any, Protocol
from dataclasses import dataclass

class CoordOp(str, Enum):
    # Worker-initiated
    MARK_COMPLETE = "mark_complete"
    REPORT_PROGRESS = "report_progress"
    REPORT_BLOCKER = "report_blocker"
    REQUEST_CLARIFICATION = "request_clarification"
    # Orchestrator-initiated
    SPAWN = "spawn"
    STATUS = "status"
    RESPOND = "respond"
    CANCEL = "cancel"
    PENDING_CLARIFICATIONS = "pending_clarifications"
    MARK_PLAN_COMPLETE = "mark_plan_complete"

@dataclass
class CoordResult:
    text: str
    success: bool = True
    data: dict | None = None

class CoordinationBackend(Protocol):
    async def mark_complete(self, run_id: str, agent: str, summary: str) -> CoordResult: ...
    async def report_progress(self, run_id: str, agent: str, status: str, milestone: str | None) -> CoordResult: ...
    async def report_blocker(self, run_id: str, agent: str, issue: str, timeout: int) -> CoordResult: ...
    async def request_clarification(self, run_id: str, agent: str, question: str, escalate_to: str, timeout: int) -> CoordResult: ...
    async def spawn(self, run_id: str, parent: str, request: "AgentRequest") -> CoordResult: ...
    async def status(self, run_id: str, parent: str, name: str | None) -> CoordResult: ...
    async def respond(self, run_id: str, parent: str, clarification_id: str, response: str) -> CoordResult: ...
    async def cancel(self, run_id: str, parent: str, name: str) -> CoordResult: ...
    async def pending_clarifications(self, run_id: str, parent: str) -> CoordResult: ...
    async def mark_plan_complete(self, run_id: str, agent: str, summary: str) -> CoordResult: ...
    def supports(self, op: CoordOp) -> bool: ...

    # Capability gate — live mode's InMemoryBackend returns False for SPAWN in v1.
```

Two backends:
- `batch/sqlite.py:SqliteCoordinationBackend` — writes to the new `nodes`/`attempts`/event tables.
- `live/in_memory.py:InMemoryCoordinationBackend` — asyncio queues for request/reply; raises `NotSupportedError` on `spawn()` in v1.

Coord tools in `adapters/claude/tools.py` and `adapters/openai/tools.py` are thin Claude/OpenAI SDK wrappers around `ctx.coord.<op>(...)`. The wrapper handles the SDK's content-block / function_tool conventions; the actual logic lives on the backend.

### `core/events.py`

```python
from dataclasses import dataclass
from typing import Literal, Protocol, Union

@dataclass
class AgentStarted:
    run_id: str; agent: str; runtime: str

@dataclass
class IterationTick:
    run_id: str; agent: str; iteration: int

@dataclass
class LogText:
    run_id: str; agent: str; text: str

@dataclass
class CostUpdate:
    run_id: str; agent: str; cost_usd: float; source: Literal["sdk","estimated"]

@dataclass
class CoordCall:
    run_id: str; agent: str; op: str; payload: dict

@dataclass
class AgentCompleted:
    run_id: str; agent: str; status: str; error: str | None

SwarmEvent = Union[AgentStarted, IterationTick, LogText, CostUpdate, CoordCall, AgentCompleted]

class EventSink(Protocol):
    def emit(self, event: SwarmEvent) -> None: ...

class NullSink:
    def emit(self, event): pass

class SqliteSink:
    """Batch sink. Writes events to the events table AND forwards LogText to per-agent log files."""
    def __init__(self, run_id: str, db_path: str, logs_dir: str): ...
    def emit(self, event): ...

class StdoutSink:
    """Live sink. Prints events to stdout (or a user-provided writer)."""
    def emit(self, event): ...
```

### `core/workspace.py`

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Union

@dataclass(frozen=True)
class GitWorktree:
    path: Path
    branch: str
    base_branch: str
    workspace_id: str  # "wt-<uuid>"

@dataclass(frozen=True)
class Cwd:
    path: Path
    workspace_id: str  # "cwd"

@dataclass(frozen=True)
class TempDir:
    path: Path
    workspace_id: str  # "tmp-<uuid>"
    # Cleanup handled by context manager

Workspace = Union[GitWorktree, Cwd, TempDir]

class WorkspaceProvider(Protocol):
    async def allocate(self, run_id: str, agent_name: str) -> Workspace: ...
    async def release(self, workspace: Workspace, keep: bool = False) -> None: ...
```

Three providers in `workspaces/`:
- `workspaces/git.py:GitWorktreeProvider` — uses the existing `gitops/worktrees.py` logic, relocated.
- `workspaces/cwd.py:CwdProvider` — returns `Cwd(Path.cwd(), "cwd")`. Zero isolation.
- `workspaces/temp.py:TempDirProvider` — `tempfile.TemporaryDirectory()` wrapping.

### `core/errors.py`

```python
class SwarmError(Exception): ...

class SwarmExecutorError(SwarmError):
    def __init__(self, message: str, retryable: bool = False, cost_so_far: float = 0.0):
        super().__init__(message)
        self.retryable = retryable
        self.cost_so_far = cost_so_far

class CoordinationNotSupported(SwarmError):
    """Raised when a backend doesn't support a coord op (e.g., live mode + spawn)."""
    def __init__(self, backend: str, op: str):
        super().__init__(f"{backend} does not support {op}")
        self.backend = backend
        self.op = op

class PlanValidationError(SwarmError): ...

class WorkspaceError(SwarmError): ...
```

---

## Batch schema (new shape)

The old `agents` table mixed immutable config and mutable state. Split:

```sql
-- Immutable per-node config, one row per agent in the plan
CREATE TABLE nodes (
    run_id TEXT NOT NULL,
    name TEXT NOT NULL,
    plan_name TEXT NOT NULL,
    runtime TEXT NOT NULL,          -- "claude" | "openai" | "mock"
    profile TEXT NOT NULL,          -- references PROFILE_REGISTRY
    model TEXT NOT NULL,
    prompt TEXT NOT NULL,
    check_command TEXT NOT NULL,
    depends_on TEXT NOT NULL,       -- JSON list
    max_iterations INTEGER NOT NULL,
    max_cost_usd REAL NOT NULL,
    parent TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (run_id, name)
);

-- Mutable execution state, one row per attempt (so retries preserve history)
CREATE TABLE attempts (
    attempt_id TEXT PRIMARY KEY,    -- uuid
    run_id TEXT NOT NULL,
    node_name TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    status TEXT NOT NULL,           -- "pending" | "running" | "completed" | "failed" | "timeout" | "cancelled" | "cost_exceeded"
    iteration INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    cost_source TEXT NOT NULL DEFAULT 'sdk',
    vendor_session_id TEXT,
    workspace_id TEXT,              -- FK to workspaces
    error TEXT,
    started_at TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id, node_name) REFERENCES nodes(run_id, name)
);

-- Workspaces as their own entity (unblocks shared-workspace patterns)
CREATE TABLE workspaces (
    workspace_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    kind TEXT NOT NULL,             -- "worktree" | "cwd" | "tempdir"
    path TEXT NOT NULL,
    branch TEXT,                    -- null for cwd/tempdir
    base_branch TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Event log for the EventSink
CREATE TABLE events (
    event_id TEXT PRIMARY KEY,      -- uuid
    run_id TEXT NOT NULL,
    agent TEXT,                     -- null for run-level events
    event_type TEXT NOT NULL,
    data TEXT NOT NULL,             -- JSON
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Coordination responses (replaces the clarification response table)
CREATE TABLE coord_responses (
    response_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    request_event_id TEXT NOT NULL,
    response_text TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (request_event_id) REFERENCES events(event_id)
);

PRAGMA user_version = 1;
```

No migration path. `batch/sqlite.py` creates fresh schemas; if it detects an existing table structure at `user_version=0` (the old shape), it raises `SwarmError("Legacy run database detected. Run `swarm clean --all` first.")`. Pre-production; users have nothing to lose.

---

## Execution shape: one PR, seven commits

One PR, a dependency-ordered stack of 7 commits, each a coherent boundary. **Commit discipline (confirmed): final commit only.** Intermediate commits are pure logical checkpoints — they may not even `python -c "import swarm"` cleanly, because the file moves and the call-site rewrites that chase them are deliberately split across commits to keep the diff reviewable. The final commit is the single all-green gate: `python -c "import swarm"` succeeds, `pytest tests/` is clean, the CLI smoke tests pass. Reviewers should read the PR top-to-bottom, not try to bisect mid-stack.

This also resolves the commit-3 / commit-4 ordering nit from the earlier draft: commit 3 ships `batch/scheduler.py` with no real adapter registered yet and its tests would fail at that point; commit 4 lands `adapters/claude/` and re-enables them; commit 5 lands the mock adapter; everything turns green at commit 7.

### Commit 1 — Package skeleton + `core/`

Create the new directory tree. Create all `__init__.py` files. Create `core/` modules with the primitive definitions:
- `core/agent.py` (`AgentRequest`, `ResolvedAgent`, `Limits`)
- `core/profiles.py` (`AgentProfile`, `PROFILE_REGISTRY`, `register_profile`, `get_profile`, + 7 builtin profiles ported from `roles.py`)
- `core/capabilities.py` (`Capability`, `CANONICAL_CAPABILITY_ORDER`, `DEFAULT_CODING_CAPS`, `READONLY_CAPS`)
- `core/execution.py` (`Executor`, `RunContext`, `ExecutionResult`, `EXECUTOR_REGISTRY`, `register`, `get_executor`)
- `core/coordination.py` (`CoordOp`, `CoordinationBackend`, `CoordResult`)
- `core/events.py` (event ADT + `EventSink` + `NullSink`)
- `core/workspace.py` (`Workspace`, `GitWorktree`, `Cwd`, `TempDir`, `WorkspaceProvider`)
- `core/errors.py` (`SwarmError` hierarchy)

`core/profiles.py` builtin profiles: `implementer` (default; full coding caps), `reviewer` (read-only-plus-shell: `{FILE_READ, GLOB, GREP, SHELL}`, `read_only=True`), `tester`, `architect`, `debugger`, `refactorer`, `documenter`, and a new `orchestrator` profile (full coding caps + `coord_ops={spawn, status, respond, cancel, pending_clarifications, mark_plan_complete, mark_complete}`).

Commit 1 may not import cleanly on its own — `core/profiles.py` references `core/capabilities.py`, and the rest of the package still imports old paths. That's fine under the "final commit only" discipline.

### Commit 2 — `workspaces/` + `batch/sqlite.py` schema

Move the existing `gitops/worktrees.py` into `workspaces/git.py` as a `GitWorktreeProvider` wrapping the current logic. Add `workspaces/cwd.py` and `workspaces/temp.py`. Delete `swarm/gitops/worktrees.py`.

Create `batch/sqlite.py` with the new 5-table schema (`nodes`, `attempts`, `workspaces`, `events`, `coord_responses`), path helpers (`get_run_dir`, `get_db_path`, `get_logs_dir`), and the `SqliteSink` event implementation. Delete `swarm/storage/db.py`, `swarm/storage/paths.py`.

Create `batch/logs.py` with the per-agent log file helpers (ported from `storage/logs.py`, minus the unused `log_to_agent_file`).

Create `batch/sqlite.py:SqliteCoordinationBackend` implementing the full `CoordinationBackend` protocol against the new tables. Ports the logic from `tools/worker.py` and `tools/manager.py` but writes to `nodes`/`attempts`/`events`/`coord_responses` instead of the old `agents` table.

Tests: `tests/test_batch_sqlite.py` — schema smoke, each coord op round-trips.

### Commit 3 — `batch/plan.py`, `batch/input.py`, `batch/dag.py`, `batch/scheduler.py`

Move plan authoring + resolution + scheduling into `batch/`.
- `batch/plan.py` — `PlanSpec`, `PlanDefaults`, and the resolution function that turns an `AgentRequest` + plan defaults into a `ResolvedAgent`.
- `batch/input.py` — YAML parser, inline plan builder, validation (absorbs `io/parser.py`, `io/plan_builder.py`, `io/validation.py`).
- `batch/dag.py` — dependency graph + topological sort (moves from `core/deps.py` — yes, core is too deep; it's a batch-only concern).
- `batch/scheduler.py` — the poll loop, circuit breaker, stuck detection. Rewritten to use `get_executor(agent.runtime).run(agent, ctx)`, where `ctx.coord` is a `SqliteCoordinationBackend` and `ctx.events` is a `SqliteSink`. `_init_db` creates fresh nodes/workspaces rows from the resolved agents.

Delete `swarm/runtime/scheduler.py`, `swarm/io/`, `swarm/core/deps.py`.

Tests: `tests/test_batch_plan.py`, `tests/test_batch_input.py`, `tests/test_batch_dag.py`, `tests/test_batch_scheduler.py` (with a stub executor — no SDK deps).

### Commit 4 — `adapters/claude/` (port existing Claude logic to new shape)

- `adapters/claude/executor.py` — `ClaudeExecutor(Executor)` that takes `(agent, ctx)`, builds `ClaudeAgentOptions` from `agent.capabilities` (expanded via `adapters/claude/builtins.py`) and the coord wrappers from `adapters/claude/tools.py`, invokes `ClaudeSDKClient`, emits events to `ctx.events`, returns `ExecutionResult`.
- `adapters/claude/builtins.py` — `CLAUDE_CAPABILITY_MAP` (the `FILE_READ → ["Read"]` / `FILE_WRITE → ["Write","Edit"]` / ... map) and `_expand_tools(caps)` using `CANONICAL_CAPABILITY_ORDER`.
- `adapters/claude/tools.py` — `build_coord_server(ctx, coord_ops)` that builds an MCP server with `@tool`-wrapped closures around `ctx.coord.<op>(...)`. Handles the Claude content-block return format.
- `adapters/claude/__init__.py` — `from . import executor; register(executor.ClaudeExecutor())`.

Delete `swarm/runtime/executor.py`, `swarm/tools/worker.py`, `swarm/tools/manager.py`, `swarm/tools/factory.py`. Delete `swarm/runtime/` entirely.

Note: `batch/merge.py` isn't touched yet in commit 4; it lands in commit 5. The `spawn_resolver` call site in the old `gitops/merge.py` is simply part of the code being deleted, not something commit 4 needs to preserve.

Tests: `tests/adapters/test_claude_executor.py` with a mocked `ClaudeSDKClient`. `tests/sdklive/test_claude_integration.py` for a real API run through the full dispatcher.

### Commit 5 — `adapters/openai/` + `adapters/mock/` + `batch/merge.py`

- `adapters/openai/executor.py` — `OpenAIExecutor(Executor)` wrapping `agents.Agent` / `agents.Runner`. Budget enforcement as soft cap (poll `RunResult.usage` after each turn, compute cost from inline price table, `cost_source="estimated"`).
- `adapters/openai/tools.py` — `build_coord_tools(ctx, coord_ops)` returning `@function_tool`-decorated closures around `ctx.coord.<op>(...)`.
- `adapters/openai/code_tools.py` — `@function_tool` parity for `read_file`, `edit_file`, `run_shell`, `grep`, `glob`. Filters by the agent's capability set.
- `adapters/openai/__init__.py` — `try: from . import executor; register(executor.OpenAIExecutor()); except ImportError: pass` so the base install works without the `openai-agents` extra.
- `adapters/mock/executor.py` — `MockExecutor(Executor)` that just runs the `check` command in the workspace and reports success/failure. Replaces `run_worker_mock`.
- `adapters/mock/__init__.py` — registers `MockExecutor`.

`batch/merge.py` — moved from `gitops/merge.py`. `spawn_resolver` and its call sites are **deleted outright**. The `auto` merge strategy no longer attempts agent-driven conflict resolution; on conflict it raises `MergeConflictError` with a clear message instructing the user to run `swarm merge --strategy manual` and resolve by hand. Re-added as a follow-up PR once the scheduler exposes a stable "run a one-off sub-plan and wait" API. Update `--strategy` help text and the CLI error output to reflect this.

Delete `swarm/gitops/` entirely after moving anything remaining into `batch/merge.py`.

`pyproject.toml` — add `openai-agents` and `openai` to the `[project.optional-dependencies]` under a new `openai` extra.

Tests: `tests/adapters/test_openai_executor.py` with mocked `Runner`. `tests/adapters/test_mock_executor.py`. `tests/sdklive/test_openai_integration.py` with a real API key. `tests/sdklive/test_mixed_runtime_plan.py` — one Claude + one OpenAI agent with `depends_on`.

### Commit 6 — `live/` + `examples/`

- `live/in_memory.py` — `InMemoryCoordinationBackend` using asyncio queues. `supports(CoordOp.SPAWN)` returns False; `spawn()` raises `CoordinationNotSupported`. Everything else (request/reply for `request_clarification`, etc.) works.
- `live/pipeline.py`:
  ```python
  async def pipeline(
      steps: list[AgentRequest],
      workspace: Literal["cwd","worktree","tempdir"] = "cwd",   # default cwd — matches how skills and scripts run today
      keep: bool = False,                                       # only meaningful for worktree/tempdir
      event_sink: EventSink | None = None,                      # defaults to StdoutSink
  ) -> list[ExecutionResult]: ...
  async def handoff(a: AgentRequest, b: AgentRequest, **kwargs) -> ExecutionResult: ...
  ```
- `live/bridge.py` — two explicit helpers, no auto-detection:
  ```python
  def as_claude_tool(agent: AgentRequest) -> Any: ...    # returns a Claude SDK @tool-decorated closure
  def as_openai_tool(agent: AgentRequest) -> Any: ...    # returns an OpenAI Agents SDK @function_tool-decorated closure
  ```
  Each closure runs a fresh nested `pipeline([agent])` when invoked, using the outer call's run context. Callers pick the target vendor explicitly — no union return type, no import-order magic.
- `examples/cross_check.py` — Claude generator → OpenAI reviewer with a Pydantic `ReviewFindings` output schema.
- `examples/debt.py` — port of the `debt` skill: `git diff HEAD~1` → parallel Claude audit (reviewer profile, read-only) → OpenAI cross-reference (structured `TechnicalDebtReport`) → Claude fixers on high+medium → verify with `pytest` + `ruff check`.

Tests: `tests/live/test_pipeline.py` (mock adapters), `tests/live/test_bridge.py` (both `as_claude_tool` and `as_openai_tool` exercised with mocked SDKs), `tests/sdklive/test_cross_check_example.py`, `tests/sdklive/test_debt_example.py`.

### Commit 7 — `cli.py` rewrite + test sweep + deletion pass

- `swarm/cli.py` — update all commands to the new paths:
  - `swarm run -f plan.yaml` → `batch.input.parse_plan_file` → `batch.plan.resolve` → `batch.scheduler.run_plan`
  - `swarm run -p "..."` → `batch.input.build_inline_plan`
  - `swarm status [run_id] [--json]` → reads from `nodes` + `attempts` (latest attempt per node)
  - `swarm logs <run_id> -a <agent>` → reads from `batch/logs.py` file helper
  - `swarm merge <run_id>` → `batch.merge.merge_run`; `--strategy auto` errors on conflict with a `Run swarm merge --strategy manual` message (spawn_resolver is gone)
  - `swarm cancel <run_id>` → writes cancel events, scheduler picks them up
  - `swarm dashboard <run_id>` → live tail on events table
  - `swarm clean [run_id] [--all]` → deletes run dirs
  - `swarm db <run_id> [query]` → queries the new schema
  - **`swarm roles [name]` is renamed to `swarm profiles [name]` as a clean break — no alias.** `swarm roles` is removed outright; any script or skill that used it breaks and must be updated. This is a known CLI break, called out in the PR description and the README changelog.
  - `swarm resume <run_id>` — see resume semantics below.
  - `swarm run ... --mock` selects the `mock` runtime via plan overrides (replaces the old mock code path).

### Default runtime resolution

When an agent doesn't specify `runtime:`, the scheduler resolves in this order:
1. The plan's `defaults.runtime` if set
2. The `SWARM_DEFAULT_RUNTIME` environment variable if set (`claude` | `openai` | `mock`)
3. Hard fallback: `claude`

Invalid values at any layer fail loudly with `PlanValidationError`. Tests cover all three layers plus the invalid-value path.

### Resume semantics

`swarm resume <run_id>` walks `nodes` for the run, and for each node inspects the latest `attempts` row (highest `attempt_number`):
- status in {`completed`}: skip
- status in {`pending`, `running`, `failed`, `timeout`, `cancelled`, `cost_exceeded`}: **insert a new `attempts` row** with `attempt_number = prev + 1`, `status='pending'`, fresh `workspace_id` (from a fresh allocation), `started_at=NULL`. The scheduler then picks it up like any other pending node.

This unifies resume and retry under one mechanism — every execution is an attempt, history is preserved, and the audit trail across the new `attempts` table is clean. Cost and iteration counters reset to zero for the new attempt; the previous row's counters stay frozen as history.
- Delete `swarm/roles.py`, `swarm/runtime/`, `swarm/tools/`, `swarm/models/`, `swarm/storage/`, `swarm/gitops/`, `swarm/io/`, `swarm/core/deps.py` (the file; `core/` the package stays) — anything that wasn't already deleted in earlier commits.
- Sweep `tests/` — delete tests that reference the old modules (`test_executor.py`, `test_tools.py`, `test_scheduler.py` old version, `test_roles.py`, `test_db.py`, `test_git.py`, `test_merge.py`, `test_deps.py`, `test_parser.py`), replace with the new tests written in commits 2–6. Keep `test_cli.py` but rewrite to hit the new CLI paths.
- Update `CLAUDE.md`, `README.md`, `PLAN.md` to reflect the new package layout.
- Update `pyproject.toml` `[tool.hatch.build.targets.wheel]` packages list.

Tests: `pytest tests/` — all green. `pytest tests/sdklive/` — green with both API keys.

---

## Deletion list (for reference)

Modules deleted outright:
- `swarm/runtime/executor.py` (AgentConfig → ResolvedAgent+RunContext; run_worker/run_manager/spawn_worker/spawn_manager → Executor.run)
- `swarm/runtime/scheduler.py` (moved to `batch/scheduler.py`, rewritten for new coord backend)
- `swarm/runtime/` (whole directory)
- `swarm/tools/worker.py`, `swarm/tools/manager.py`, `swarm/tools/factory.py`, `swarm/tools/__init__.py` (moved to adapter subpackages and coord backend)
- `swarm/tools/` (whole directory)
- `swarm/models/specs.py`, `swarm/models/state.py` (`state.py` was unused; `specs.py` split between `core/agent.py` and `batch/plan.py`)
- `swarm/models/` (whole directory)
- `swarm/storage/db.py`, `swarm/storage/paths.py`, `swarm/storage/logs.py` (moved to `batch/sqlite.py` and `batch/logs.py`)
- `swarm/storage/` (whole directory)
- `swarm/gitops/worktrees.py`, `swarm/gitops/merge.py` (moved to `workspaces/git.py` and `batch/merge.py`)
- `swarm/gitops/` (whole directory)
- `swarm/io/parser.py`, `swarm/io/plan_builder.py`, `swarm/io/validation.py` (collapsed into `batch/input.py`)
- `swarm/io/` (whole directory)
- `swarm/roles.py` (moved to `core/profiles.py`, 7 roles become profiles)
- `swarm/core/deps.py` (moved to `batch/dag.py`)

Fields / concepts deleted from the public surface:
- `session_id` column (was never persisted back; adapters return `vendor_session_id` on `ExecutionResult` but it's not stored)
- `AgentSpec.type: Literal["worker","manager"]` (manager is now a profile with `spawn` coord ops)
- `Toolset.kind` (never existed; would have been introduced by the earlier draft)
- `RunConfig`, `Milestone`, `ManagerSettings` (all defined in `models/specs.py` but unused by the runtime)
- `event_injection` field, `on_complete` field (unused)
- `run_worker_mock` (replaced by `MockExecutor`)
- `gitops/merge.py:spawn_resolver` — **dropped entirely** from the `auto` merge strategy. On conflict, `swarm merge --strategy auto` raises a clean `MergeConflictError` pointing the user to `--strategy manual`. Re-added in a follow-up PR once the scheduler exposes a one-off-sub-plan API.
- `storage/logs.py:log_to_agent_file` (unused)
- All DB migration code — fresh schemas only; legacy DBs fail fast with a clean-up instruction

---

## Verification

**No per-commit gate** (confirmed). Intermediate commits may not import and their tests may fail — the stack is graded as a whole.

**Final PR gate** (all must be green before merge):

- [ ] `pytest tests/` — all tests pass under the new layout
- [ ] `pytest tests/sdklive/` — with `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` set
- [ ] `swarm run -f test-plan.yaml --mock` — mock CLI path works end-to-end (uses `MockExecutor`)
- [ ] `swarm run -p "test: true"` — inline plan, default runtime resolves to `claude` via the env-var fallback chain
- [ ] `SWARM_DEFAULT_RUNTIME=openai swarm run -p "test: true"` — env var flips the default
- [ ] `swarm run -p "audit: Find bugs" -p "review: ..." --sequential` — inline sequential plan works
- [ ] `swarm status`, `swarm logs`, `swarm merge`, `swarm clean`, `swarm dashboard`, `swarm profiles` — all CLI commands work under the new paths
- [ ] `swarm roles` — errors with "unknown command" (rename confirmed, no alias)
- [ ] `swarm resume <run_id>` — inserts a fresh `attempts` row per incomplete node (`attempt_number = prev + 1`) and completes the run
- [ ] `swarm merge <run_id> --strategy auto` on a conflict — raises `MergeConflictError` with the manual-resolution instruction
- [ ] A `reviewer`-profile agent can successfully run `pytest` and `ruff check` in its workspace (shell capability retained)
- [ ] A `reviewer`-profile agent attempting `Write` or `Edit` gets a capability-denied error
- [ ] `live.pipeline([...])` with no `workspace=` kwarg runs against `cwd` (default)
- [ ] `live.as_claude_tool(req)` and `live.as_openai_tool(req)` both produce wrappers that round-trip through their respective SDKs in the bridge tests
- [ ] `python examples/cross_check.py` — produces a reviewed patch via live mode
- [ ] `python examples/debt.py` — on a seeded repo with a deliberate bug, produces a fix
- [ ] `pip install -e .` (without the openai extra) — base install works, `from swarm.adapters import claude` succeeds, `from swarm.adapters import openai` raises ImportError cleanly
- [ ] `pip install -e ".[openai]"` — OpenAI adapter loads, mixed-runtime plan runs end-to-end
- [ ] `grep -rn "from swarm.runtime\|from swarm.tools\|from swarm.models\|from swarm.storage\|from swarm.gitops\|from swarm.io\|from swarm.roles" swarm/ tests/` — zero matches (nothing left importing the old paths)
- [ ] `grep -rn "session_id" swarm/ --include='*.py'` — zero matches (column gone)
- [ ] `grep -rn "os.environ.get.*SWARM_PARENT\|os.environ.get.*SWARM_TREE" swarm/` — zero matches (env leak fixed by passing via `ResolvedAgent`/`RunContext`)
- [ ] `grep -rn "AgentConfig\|run_worker\|run_manager\|spawn_worker_mock\|run_worker_mock" swarm/` — zero matches
- [ ] A legacy `.swarm/runs/*/swarm.db` file triggers a clean `SwarmError` with instructions to `swarm clean --all`, not a cryptic SQL error
- [ ] README tagline and `CLAUDE.md` both reflect "Claude + OpenAI"

---

## Out of scope (explicit deferrals)

- **Cross-vendor OTel tracing unification.** Nice to have. OpenAI SDK ships with tracing by default; Claude exports OTel via env vars. Wiring a shared `run_id` across both is additive and can land in a follow-up PR without structural changes.
- **`swarm report <run_id>` command.** The optimization report from the user's `swarm-audit` skill Phase 7 (per-agent utilization, bottlenecks, suggested next-run config). Pure query on the events table. Follow-up PR.
- **MCP bridge** — shared function registry exposed as Claude in-process MCP and OpenAI stdio MCP. Only pays off once swarm has concrete shared tools to justify it. Follow-up PR, minimum 3 shared tools first.
- **Skill → plan YAML converter.** Parse `~/.claude/skills/*.md` and emit a `PlanSpec` YAML. Standalone script; not blocked by this refactor.
- **Durable pause/resume with external hooks** (Vercel `createHook`-style). Evolve `request_clarification` into a durable primitive. Non-trivial; follow-up.
- **Manager-in-live-mode.** The in-memory backend simply doesn't implement `CoordOp.SPAWN` in v1. When someone needs it, add a micro-scheduler to `live/in_memory.py`. Not architecturally forbidden; just unimplemented.
- **`core/budget.py` as a shared price table.** Inlined into `adapters/openai/executor.py` for now. Promote to a shared module only once Phase 1 ships and we actually need it from two places.
- **Retry semantics rewrite.** The new `attempts` table unblocks multi-attempt history, but this PR keeps the existing retry policy (`on_failure: retry` + `retry_count`). A future PR can add richer retry strategies.

---

## Naming

Keep `swarm`. Update README tagline from "Multi-agent orchestration for Claude Code" to "Multi-agent orchestration for coding agents (Claude + OpenAI)". No rename, no pyproject churn, no CLI break — but every CLI command that previously said "agent" may need to say "node" or vice versa as the new `nodes`/`attempts` vocabulary lands. Use "agent" for user-facing docs (`swarm run --agent foo`), "node" only in DB schema and internal code.

---

## Risks

- **Intermediate commits may not import or pass tests.** Confirmed acceptable — the stack is graded as a whole at commit 7. The PR description must call this out explicitly so reviewers don't `git checkout` a middle commit and panic.
- **The `AgentRequest` → `ResolvedAgent` resolution is load-bearing.** If resolution fails (unknown profile, bad default runtime, capability/profile mismatch), it must fail at plan-load time with a clear `PlanValidationError`, not mid-run. Cover with tests.
- **`swarm roles` → `swarm profiles` is a hard break.** Anything scripting the old command (user skills, CI) breaks. Mitigation: call it out prominently in README and commit 7's commit message; cheap for the user since the migration is a one-word find/replace.
- **The `MockExecutor` replacing `run_worker_mock` needs to reproduce the current `--mock` CLI semantics exactly** (runs the `check` command, reports based on exit code, writes a fake cost of 0.0). Users rely on this for CI dry-runs.
- **`core/` accreting too much**. The temptation is to put everything vendor-neutral in `core/`. Resist: `core/` should hold cross-mode contracts only. DB-backed things go in `batch/`, in-memory things go in `live/`.
- **Import cycles**. `core/profiles.py` references `core/capabilities.py`. `adapters/claude/tools.py` references `core/coordination.py`. Keep the dependency graph one-way: `core → nothing; adapters → core; batch → core, workspaces; live → core, workspaces; cli → batch, live`. No back-references.
- **Test churn is large.** Most tests in `tests/` get rewritten or replaced. Budget for it; the old tests are tightly coupled to the old module structure.

---

## Execution notes

- Work branch: `feat/multi-runtime`. One PR with 7 commits as described above.
- PR title: `Multi-runtime restructure: Claude + OpenAI + live mode`.
- PR description: link this plan file (the canonical location `~/dev/swarm/.claude/plans/gleaming-cuddling-pike.md`), list the 7 commits with a one-line summary each, and document the four intentional breaks: (1) `reviewer` profile becomes read-only-plus-shell (no write/edit); (2) `swarm roles` is renamed to `swarm profiles` with no alias; (3) `swarm merge --strategy auto` no longer spawns a resolver agent on conflict and errors with a manual-resolution hint; (4) managers are forbidden in live mode v1 (in-memory backend returns False for `CoordOp.SPAWN`).
- **Pre-execution TODO**: create the branch, sync the plan file into the repo (`cp ~/.claude/plans/gleaming-cuddling-pike.md ~/dev/swarm/.claude/plans/gleaming-cuddling-pike.md`), then start commit 1.
