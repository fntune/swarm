# swarm

Multi-agent orchestration CLI for Claude Code. Define agents in a YAML plan, run them in parallel across isolated git worktrees, and merge the results.

```bash
swarm run -f plan.yaml
swarm dashboard <run-id>
swarm merge <run-id>
```

---

## How it works

You write a plan spec — a YAML file describing agents, their tasks, and dependencies. Swarm resolves the dependency graph, spawns agents in parallel git worktrees, tracks state in SQLite, and merges branches when done.

Each agent gets its own worktree so they can edit files without conflicts. Workers signal completion via tool calls; managers can spawn subagents and respond to clarification requests mid-run.

## Installation

Requires Python 3.10+ and the Claude Agent SDK.

```bash
pip install -e ".[sdk]"
```

Or without the SDK (for `--mock` runs):

```bash
pip install -e .
```

## Quick start

Write a plan:

```yaml
# plan.yaml
name: add-feature
agents:
  - name: design
    prompt: "Design the API for a rate limiter module. Output a spec."

  - name: implement
    prompt: "Implement the rate limiter from the spec in design's output."
    depends_on: [design]

  - name: test
    prompt: "Write tests for the rate limiter."
    depends_on: [implement]
    check: "pytest tests/rate_limiter/ -v"
```

Run it:

```bash
swarm run -f plan.yaml
swarm dashboard <run-id>   # live status
swarm merge <run-id>        # merge completed branches
```

Or run inline without a file:

```bash
# Single agent
swarm run -p "auth: Implement JWT middleware"

# Sequential chain
swarm run -p "analyze: Audit auth code" -p "fix: Apply the fixes from analyze" --sequential
```

## Commands

| Command | Description |
|---------|-------------|
| `swarm run -f plan.yaml` | Execute a plan spec |
| `swarm run -p "name: task"` | Inline single agent |
| `swarm resume <run-id>` | Resume a paused or failed run |
| `swarm status [run-id]` | View run status (latest if no ID) |
| `swarm dashboard <run-id>` | Live status view |
| `swarm logs <run-id> -a <agent>` | View agent logs |
| `swarm merge <run-id>` | Merge completed branches into current |
| `swarm cancel <run-id>` | Cancel running agents |
| `swarm clean [run-id]` | Remove artifacts for a run |
| `swarm roles` | List built-in role templates |

## Plan spec

```yaml
name: my-plan

defaults:
  model: sonnet          # default model for all agents
  check: null            # default completion check

agents:
  - name: architect
    use_role: architect  # use a built-in role template
    prompt: "Design the auth system for this service"

  - name: implementer
    use_role: implementer
    prompt: "Implement the design from architect's output"
    depends_on: [architect]
    check: "cargo build"  # must pass for agent to be marked complete

  - name: reviewer
    use_role: reviewer
    prompt: "Review the implementation"
    depends_on: [implementer]
    model: opus
```

## Built-in roles

| Role | Description |
|------|-------------|
| `architect` | Designs system architecture and produces specs (uses Opus) |
| `implementer` | Implements features from specs |
| `tester` | Writes and runs tests (check: `pytest`) |
| `reviewer` | Reviews code for quality and correctness |
| `debugger` | Investigates and fixes bugs |
| `documenter` | Writes documentation |
| `refactorer` | Refactors code for quality |

Roles set a specialized system prompt and optionally a default model and check command.

## Resumable runs

Every run gets a unique `run-id`. State is persisted to SQLite so interrupted runs can be resumed:

```bash
swarm run -f plan.yaml --run-id my-run
# ... interrupted

swarm resume my-run
```

## Testing without the SDK

Use `--mock` to test plan parsing and dependency resolution without making API calls:

```bash
swarm run -p "test: true" --mock
```

## Architecture

```
swarm/
├── cli.py          10 Click commands
├── models.py       AgentSpec, PlanSpec, Defaults (Pydantic)
├── deps.py         Dependency graph, topological sort
├── scheduler.py    Parallel execution, circuit breaker
├── executor.py     Agent execution (SDK + MCP tools)
├── git.py          Worktree creation, branch management
├── merge.py        Branch consolidation, conflict handling
├── roles.py        Built-in role templates
├── tools.py        Worker + manager coordination tools
└── db.py           SQLite state (WAL mode)
```

## License

MIT
