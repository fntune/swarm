# CLAUDE.md

## Project Overview

**swarm** — Multi-agent orchestration for coding agents (Claude + OpenAI).

Two execution modes share one set of primitives (profile / capability /
coordination backend / executor):

- **Batch mode** persists everything in SQLite (`nodes` / `attempts` /
  `workspaces` / `events` / `coord_responses`), runs agents in parallel
  isolated git worktrees, supports DAG dependencies, retry-with-history,
  resume, circuit breaker, and branch merging.
- **Live mode** is a single-process pipeline runner: no SQLite, no DAG, no
  worktrees by default. `from swarm.live import pipeline` runs a
  Claude→OpenAI handoff in 20 lines.

## Commands

```bash
# Development
pip install -e .
pip install -e ".[openai]"     # add OpenAI Agents SDK
swarm --help

# Testing
pytest tests/

# Core CLI
swarm run -f plan.yaml                          # Execute plan spec
swarm run -p "auth: Impl auth"                  # Inline single agent
swarm run -p "a: step1" -p "b: step2" --sequential
swarm run --run-id <id> -p "..."                # Explicit run ID
swarm run --resume --run-id <id>                # Resume existing run
swarm run -p "test: noop" --mock                # Force mock runtime + cwd workspace
swarm run -f plan.yaml --workspace tempdir      # Override workspace

swarm resume <run_id>                           # Resume alias
swarm status [run_id] [--json]                  # View status (latest if no id)
swarm logs <run_id> -a <agent>                  # View agent logs
swarm logs <run_id> --all                       # View all logs
swarm merge <run_id> [--strategy manual|fail|auto]
swarm cancel <run_id>                           # Cancel running agents
swarm dashboard <run_id>                        # Live status view
swarm clean [run_id] [--all]                    # Clean up artifacts
swarm db [run_id] [query]                       # Query SQLite database
swarm profiles [name]                           # List/view built-in profiles
```

`swarm roles` is gone in this release. The renamed command is
`swarm profiles`. There is no alias.

## Architecture

```
swarm/
├── cli.py                  # Click CLI entrypoint (10 commands)
├── core/                   # Cross-mode contracts (no SQLite, no asyncio)
│   ├── agent.py            # AgentRequest, ResolvedAgent, Limits, OnFailure
│   ├── profiles.py         # AgentProfile, PROFILE_REGISTRY, 8 builtins
│   ├── capabilities.py     # Capability enum, DEFAULT_CODING_CAPS, READONLY_CAPS
│   ├── execution.py        # Executor ABC, RunContext, ExecutionResult, registry
│   ├── coordination.py     # CoordOp, CoordinationBackend protocol, CoordResult
│   ├── events.py           # SwarmEvent ADT, EventSink, NullSink
│   ├── workspace.py        # Workspace ADT, WorkspaceProvider protocol
│   └── errors.py           # SwarmError hierarchy
├── adapters/               # Vendor adapters (one subpackage each)
│   ├── claude/             # ClaudeExecutor + MCP coord server + capability map
│   ├── openai/             # OpenAIExecutor + function_tool wrappers + code tools
│   └── mock/               # MockExecutor — runs the check command
├── batch/                  # SQLite-backed parallel scheduler
│   ├── plan.py             # PlanSpec, PlanDefaults, resolve_plan, resolve_child
│   ├── input.py            # YAML parser, inline plan builder, validation
│   ├── dag.py              # Dependency graph + topological sort
│   ├── scheduler.py        # Poll loop, dispatch, retry, circuit breaker
│   ├── sqlite.py           # Schema, helpers, SqliteSink, SqliteCoordinationBackend
│   ├── logs.py             # Per-agent log file helpers
│   └── merge.py            # Branch consolidation (no spawn_resolver)
├── live/                   # In-process pipelines, no SQLite
│   ├── pipeline.py         # pipeline(), handoff(), StdoutSink
│   ├── bridge.py           # as_claude_tool, as_openai_tool
│   └── in_memory.py        # InMemoryCoordinationBackend
└── workspaces/
    ├── git.py              # GitWorktreeProvider + low-level git helpers
    ├── cwd.py              # CwdProvider — zero isolation
    └── temp.py             # TempDirProvider — throwaway tempdir
```

## Key Concepts

### Profile = capabilities + coord ops + system prompt
8 builtin profiles: `implementer` (default), `architect`, `tester`,
`reviewer` (read-only-plus-shell — can read/glob/grep and run tests, but
cannot write/edit files), `debugger`, `refactorer`, `documenter`,
`orchestrator` (full coding caps + spawn/status/respond/cancel/
mark_plan_complete coord ops).

### Capability is vendor-neutral
`Capability.{FILE_READ, FILE_WRITE, FILE_EDIT, GLOB, GREP, SHELL,
WEB_FETCH, WEB_SEARCH}`. The Claude adapter expands these to
`Read/Write/Edit/Glob/Grep/Bash/...` via `CLAUDE_CAPABILITY_MAP`. The
OpenAI adapter wires them to `@function_tool`-decorated stdlib closures.

### Default runtime resolution
`PlanDefaults.runtime` → `SWARM_DEFAULT_RUNTIME` env var → hard fallback
`claude`. Invalid env values raise `PlanValidationError`.

### Failure handling
- **on_failure: continue** — default
- **on_failure: stop** — cancel all agents on first failure
- **on_failure: retry** — insert a NEW `attempts` row each retry; full
  history preserved; resume reuses the same machinery
- **Cascade failures** — agents with failed deps are marked failed
- **Circuit breaker** — trip after N failures (cancel_all/pause/notify)

### Coordination
Worker ops: `mark_complete`, `request_clarification`, `report_progress`,
`report_blocker`.
Orchestrator ops: `spawn`, `status`, `respond`, `cancel`,
`pending_clarifications`, `mark_plan_complete`.

Two backends:
- `batch/sqlite.py:SqliteCoordinationBackend` — persists via the events /
  coord_responses tables.
- `live/in_memory.py:InMemoryCoordinationBackend` — asyncio-friendly,
  spawn raises `CoordinationNotSupported` in v1.

## Plan Spec Format

```yaml
name: my-plan
defaults:
  runtime: claude          # or openai, or mock
  model: sonnet
  check: "pytest tests/"
  on_failure: retry
  retry_count: 3
orchestration:
  circuit_breaker:
    threshold: 3
    action: cancel_all
agents:
  - name: auth
    prompt: "Implement authentication"
    profile: implementer
  - name: review
    prompt: "Review the auth implementation"
    profile: reviewer        # read-only + shell
    runtime: openai          # cross-vendor in one plan
    depends_on: [auth]
```

## File Layout

```
.swarm/
└── runs/{run_id}/
    ├── swarm.db                # SQLite state (5 tables, WAL mode)
    ├── worktrees/{agent}/      # Git worktrees (when workspace=worktree)
    └── logs/{agent}.log        # Per-agent log files
```

## Dependencies

- `pydantic>=2.0` — YAML boundary models in batch/input.py
- `click>=8.0` — CLI
- `pyyaml>=6.0` — Plan spec parsing
- `claude-agent-sdk>=0.1.19` (optional `[sdk]` extra) — Claude runtime
- `openai-agents>=0.0.9`, `openai>=1.50` (optional `[openai]` extra) — OpenAI runtime

## Style

- Follow global CLAUDE.md conventions
- SQLite WAL mode for concurrent agent access
- Logs stay as files (for tail -f compatibility)
- `core/` only holds cross-mode contracts; DB-backed things live in
  `batch/`, in-memory things in `live/`
- Dependency graph is one-way: `core → nothing; adapters → core;
  batch → core, workspaces; live → core, workspaces; cli → batch, live`

## Code Patterns

### Database Access
```python
from swarm.batch.sqlite import get_db, get_nodes, latest_attempt

with get_db(run_id) as db:
    for node in get_nodes(db, run_id):
        attempt = latest_attempt(db, run_id, node["name"])
```

### Live pipeline
```python
import swarm.adapters.claude  # noqa: registers ClaudeExecutor
import swarm.adapters.openai  # noqa: registers OpenAIExecutor
from swarm.core.agent import AgentRequest
from swarm.live.pipeline import pipeline

results = await pipeline(
    [
        AgentRequest(name="gen", profile="implementer", runtime="claude",
                     prompt="Write a fibonacci function"),
        AgentRequest(name="rev", profile="reviewer", runtime="openai",
                     prompt="Review the function above"),
    ],
    workspace="cwd",
)
```

### Custom Executor
```python
from swarm.core.execution import Executor, ExecutionResult, register

class MyExecutor(Executor):
    runtime = "myruntime"
    async def run(self, agent, ctx) -> ExecutionResult:
        ...

register(MyExecutor())
```
