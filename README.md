# swarm

> Multi-agent orchestration for coding agents (Claude + OpenAI). Parallel
> worktrees in batch mode. Pipelines and handoffs in live mode. Same primitives,
> same profiles, same coordination contract.

```bash
# batch mode (YAML, SQLite, parallel worktrees)
swarm run -f plan.yaml
swarm dashboard <run-id>
swarm merge <run-id>

# live mode (Python, in-process, no SQLite)
python -c "
import asyncio, swarm.adapters.claude, swarm.adapters.openai
from swarm.core.agent import AgentRequest
from swarm.live.pipeline import pipeline
asyncio.run(pipeline([
    AgentRequest(name='gen', runtime='claude', prompt='Write fib(n)'),
    AgentRequest(name='rev', runtime='openai', profile='reviewer',
                 prompt='Review the function above'),
]))
"
```

Write a YAML plan, or compose a live pipeline in 5 lines. swarm resolves
profiles + capabilities, dispatches to the right vendor adapter, and
tracks state.

---

## Why

Chaining agent sessions by hand doesn't scale. Copy-pasting outputs between
windows, manually rebasing branches, losing all context when a session dies
— this is friction that shouldn't exist. So is being locked to one vendor.

swarm treats multi-agent work as a **data structure**: profiles describe
what an agent can do, plans describe how they connect, and the same
contract works whether the agent is running through Claude or OpenAI.

- **Two runtimes, one contract.** Claude Agent SDK and OpenAI Agents SDK
  ship as adapter subpackages; mock is built in. Mix `runtime: claude` and
  `runtime: openai` in the same plan with `depends_on` edges.
- **Profiles over roles.** A profile bundles a system prompt, a capability
  set (vendor-neutral: `FILE_READ`, `SHELL`, ...), and a coordination
  surface (`mark_complete`, `request_clarification`, ...). Eight builtins
  including a read-only-plus-shell `reviewer` and an `orchestrator` that
  spawns children.
- **Batch mode** persists everything: `nodes` (immutable config) +
  `attempts` (every retry is a new row, full history preserved) +
  `workspaces` + `events` + `coord_responses`. SQLite WAL, resumable.
- **Live mode** runs a pipeline in-process: no SQLite, no DAG, no
  worktrees by default. Drop into a script, get a Claude→OpenAI handoff
  in twenty lines.
- **Failure modes.** `continue` / `stop` / `retry` per agent. Retries
  insert a fresh `attempts` row; resume reuses the same machinery. Circuit
  breaker, cost budget, cascade-failure, stuck detection.

---

## Installation

```bash
pip install -e .                  # base install (mock runtime only)
pip install -e ".[sdk]"           # + Claude Agent SDK
pip install -e ".[openai]"        # + OpenAI Agents SDK
pip install -e ".[sdk,openai]"    # both
```

---

## Quick start: batch mode

Write a plan:

```yaml
# plan.yaml
name: auth-feature
defaults:
  runtime: claude
  on_failure: retry
  retry_count: 3

agents:
  - name: design
    profile: architect
    prompt: "Design the JWT auth middleware. Output a spec."

  - name: implement
    profile: implementer
    prompt: "Implement the JWT auth middleware from design's spec."
    depends_on: [design]
    check: "cargo build"

  - name: test
    profile: tester
    prompt: "Write unit and integration tests."
    depends_on: [implement]
    check: "cargo test auth"

  - name: review
    profile: reviewer        # read-only-plus-shell
    runtime: openai          # cross-vendor in one plan
    prompt: "Review the implementation and tests."
    depends_on: [implement, test]
```

Run it:

```bash
swarm run -f plan.yaml        # launch all agents
swarm dashboard <run-id>      # live status
swarm logs <run-id> -a test   # stream agent logs
swarm merge <run-id>          # merge completed branches
```

Or skip the file for quick tasks:

```bash
swarm run -p "audit: Find all SQL injection risks"
swarm run -p "find: List deprecated APIs" -p "fix: Apply fixes" --sequential
swarm run -p "test: noop" --mock          # CI dry run, no API calls
```

---

## Quick start: live mode

```python
import asyncio
import swarm.adapters.claude  # noqa: registers ClaudeExecutor
import swarm.adapters.openai  # noqa: registers OpenAIExecutor
from swarm.core.agent import AgentRequest
from swarm.live.pipeline import pipeline

async def main():
    results = await pipeline(
        [
            AgentRequest(
                name="generator",
                runtime="claude",
                profile="implementer",
                prompt="Write a 10-line Python fibonacci function",
            ),
            AgentRequest(
                name="reviewer",
                runtime="openai",
                profile="reviewer",
                prompt="Review the function. List bugs, edge cases, style issues.",
            ),
        ],
        workspace="cwd",   # cwd | worktree | tempdir
    )
    for r in results:
        print(r.status, r.final_text[:200])

asyncio.run(main())
```

Two more examples ship in `examples/`: `cross_check.py` (this same
generator-reviewer pattern) and `debt.py` (port of the `debt` skill —
audit + cross-reference).

---

## Profiles

| Profile | Capabilities | Coord ops | Notes |
|---------|--------------|-----------|-------|
| `implementer` | read/write/edit/glob/grep/shell | worker | default |
| `architect` | full coding | worker | defaults to opus |
| `tester` | full coding | worker | check = `pytest tests/ -v` |
| `reviewer` | read/glob/grep/**shell** (no write/edit) | worker | read-only-plus-shell |
| `debugger` | full coding | worker | |
| `refactorer` | full coding | worker | check = `pytest` |
| `documenter` | full coding | worker | |
| `orchestrator` | full coding | worker + spawn/status/respond/cancel/mark_plan_complete | spawns child agents |

`swarm profiles [name]` shows them at the CLI.

---

## Commands

| Command | Description |
|---------|-------------|
| `swarm run -f plan.yaml` | Execute a plan spec |
| `swarm run -p "name: task"` | Inline single agent |
| `swarm run ... --sequential` | Force sequential execution |
| `swarm run ... --mock` | Mock runtime + cwd workspace (CI dry run) |
| `swarm run ... --workspace cwd|worktree|tempdir` | Override workspace |
| `swarm resume <run-id>` | Resume from last known state (new attempts row per node) |
| `swarm status [run-id] [--json]` | Run status |
| `swarm dashboard <run-id>` | Live status view |
| `swarm logs <run-id> -a <agent>` | Stream agent logs |
| `swarm logs <run-id> --all` | All agent logs |
| `swarm merge <run-id> [--strategy manual|fail|auto]` | Merge completed branches |
| `swarm cancel <run-id>` | Cancel a running plan |
| `swarm clean [run-id|--all]` | Remove artifacts |
| `swarm db <run-id> [query]` | Query run state in SQLite |
| `swarm profiles [name]` | List / inspect profiles (renamed from `roles`) |

`swarm roles` is gone in this release. The renamed command is
`swarm profiles`. There is no alias.

---

## Default runtime resolution

When an agent doesn't specify `runtime:`, the resolver checks in order:

1. `PlanDefaults.runtime` if set
2. `SWARM_DEFAULT_RUNTIME` env var (`claude` | `openai` | `mock`)
3. Hard fallback: `claude`

Invalid env values raise `PlanValidationError` at plan-load time.

---

## Architecture

```
swarm/
├── cli.py                  10 Click commands
├── core/                   Cross-mode contracts (no SQLite, no asyncio)
│   ├── agent.py            AgentRequest, ResolvedAgent, Limits, OnFailure
│   ├── profiles.py         AgentProfile, PROFILE_REGISTRY, 8 builtins
│   ├── capabilities.py     Capability enum, DEFAULT_CODING_CAPS, READONLY_CAPS
│   ├── execution.py        Executor ABC, RunContext, ExecutionResult
│   ├── coordination.py     CoordOp, CoordinationBackend protocol
│   ├── events.py           SwarmEvent ADT, EventSink
│   ├── workspace.py        Workspace ADT, WorkspaceProvider
│   └── errors.py           SwarmError hierarchy
├── adapters/
│   ├── claude/             ClaudeExecutor + MCP coord server + capability map
│   ├── openai/             OpenAIExecutor + function_tool wrappers + code tools
│   └── mock/               MockExecutor — runs the agent's check command
├── batch/                  SQLite-backed parallel scheduler
│   ├── plan.py             PlanSpec, PlanDefaults, resolve_plan, resolve_child
│   ├── input.py            YAML parser, inline plan builder, validation
│   ├── dag.py              Dependency graph + topological sort
│   ├── scheduler.py        Poll loop, dispatch, retry, circuit breaker
│   ├── sqlite.py           Schema, helpers, SqliteSink, SqliteCoordinationBackend
│   ├── logs.py             Per-agent log file helpers
│   └── merge.py            Branch consolidation (no spawn_resolver)
├── live/                   In-process pipelines, no SQLite
│   ├── pipeline.py         pipeline(), handoff(), StdoutSink
│   ├── bridge.py           as_claude_tool, as_openai_tool
│   └── in_memory.py        InMemoryCoordinationBackend
└── workspaces/
    ├── git.py              GitWorktreeProvider + git helpers
    ├── cwd.py              CwdProvider
    └── temp.py             TempDirProvider
```

Dependency graph is one-way:
`core → nothing; adapters → core; batch → core, workspaces; live → core, workspaces; cli → batch, live`.

---

## Status

Beta. Two runtimes (Claude + OpenAI) plus mock, batch + live modes, 8
profiles, the `attempts`-row history schema, retry / cascade / circuit
breaker / cost budget / stuck detection, full CLI, two example pipelines.

Manager-in-live-mode (`spawn` from `InMemoryCoordinationBackend`) is the
biggest deferred feature; it raises `CoordinationNotSupported` for now.
The merge `auto` strategy no longer spawns a resolver agent on conflict —
it raises `MergeConflictError` and points you at `--strategy manual`.
