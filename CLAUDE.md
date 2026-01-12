# CLAUDE.md

## Project Overview

**claude-swarm** - Multi-agent orchestration framework for Claude Code.

Executes agents in parallel git worktrees with dependency resolution and branch merging.

## Commands

```bash
# Development
pip install -e .
swarm --help

# Testing
pytest tests/

# Core CLI
swarm run -f plan.yaml           # Execute plan spec
swarm run -p "auth: Impl auth"   # Inline single agent
swarm run -p "a: step1" -p "b: step2" --sequential  # Sequential chain
swarm status <run_id>            # View agent status
swarm logs <run_id> -a <agent>   # View agent logs
swarm logs <run_id> --all        # View all logs
swarm merge <run_id>             # Merge completed branches
swarm cancel <run_id>            # Cancel running agents
swarm dashboard <run_id>         # Live status view

# Testing without Claude CLI
swarm run -p "test: true" --mock
```

## Architecture

```
swarm/                    # Python package
├── cli.py               # Click CLI entrypoint
├── models.py            # Pydantic: AgentSpec, PlanSpec, Defaults
├── parser.py            # YAML parsing, inline plan creation
├── db.py                # SQLite setup, queries (WAL mode)
├── deps.py              # Dependency graph, topological sort
├── scheduler.py         # Parallel execution coordinator
├── executor.py          # Agent worker (subprocess or mock)
├── git.py               # Worktree creation, branch merging
├── merge.py             # Branch consolidation CLI helper
├── logs.py              # Log file management
└── tools.py             # Agent toolset (mark_complete, etc.)
```

## Key Patterns

1. **SQLite state**: `.swarm/runs/{run_id}/swarm.db` (WAL mode for concurrency)
2. **Git worktrees**: `.swarm/runs/{run_id}/worktrees/{agent}/` for isolation
3. **Branch naming**: `swarm/{run_id}/{agent}`
4. **Dependency merging**: When agent has depends_on, dependency branches merge into its worktree before execution
5. **Check command**: Optional validation after agent completion (default: `true`)
6. **Run scoping**: Each run gets unique ID like `inline-abc123-def456`

## Plan Spec Format

```yaml
name: my-plan
defaults:
  check: "pytest tests/"
agents:
  - name: auth
    prompt: "Implement authentication"
  - name: api
    prompt: "Add API endpoints"
    depends_on: [auth]
```

## File Layout

```
.swarm/
└── runs/{run_id}/
    ├── swarm.db                # SQLite state
    ├── worktrees/{agent}/      # Git worktrees
    └── logs/{agent}.log        # Per-agent logs
```

## Dependencies

- `pydantic>=2.0` - State models
- `click>=8.0` - CLI
- `pyyaml>=6.0` - Plan spec parsing

## Style

- Follow global CLAUDE.md conventions
- SQLite WAL mode for concurrent agent access
- Logs stay as files (for tail -f compatibility)
