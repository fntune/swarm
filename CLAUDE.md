# CLAUDE.md

## Project Overview

**claude-swarm** - Multi-agent orchestration framework for Claude Code.

Executes agents in parallel git worktrees with dependency resolution, retry logic, and branch merging.

## Commands

```bash
# Development
pip install -e .
swarm --help

# Testing
pytest tests/

# Core CLI
swarm run -f plan.yaml                    # Execute plan spec
swarm run -p "auth: Impl auth"            # Inline single agent
swarm run -p "a: step1" -p "b: step2" --sequential  # Sequential chain
swarm run --run-id <id> -p "..."          # Explicit run ID
swarm run --resume --run-id <id>          # Resume existing run

swarm resume <run_id>                     # Resume alias
swarm status [run_id] [--json]            # View status (latest if no id)
swarm logs <run_id> -a <agent>            # View agent logs
swarm logs <run_id> --all                 # View all logs
swarm merge <run_id> [--dry-run]          # Merge completed branches
swarm cancel <run_id>                     # Cancel running agents
swarm dashboard <run_id>                  # Live status view
swarm clean [run_id] [--all]              # Clean up artifacts
swarm db [run_id] [query]                 # Query SQLite database
swarm roles [name]                        # List/view available roles

# Testing without Claude CLI
swarm run -p "test: true" --mock
```

## Architecture

```
swarm/                    # Python package
├── cli.py               # Click CLI entrypoint (10 commands)
├── models.py            # Pydantic: AgentSpec, PlanSpec, Defaults
├── parser.py            # YAML parsing, inline plan creation
├── db.py                # SQLite setup, queries (WAL mode)
├── deps.py              # Dependency graph, topological sort
├── scheduler.py         # Parallel execution, circuit breaker, stuck detection
├── executor.py          # Agent worker (subprocess or mock)
├── git.py               # Worktree creation, branch merging
├── merge.py             # Branch consolidation CLI helper
├── logs.py              # Log file management
├── roles.py             # Built-in role templates (7 roles)
└── tools.py             # Worker + Manager coordination tools
```

## Key Features

### Execution
- **Parallel agents** in isolated git worktrees
- **Dependency resolution** with topological ordering
- **Sequential mode** (`--sequential`) for linear pipelines
- **Resume support** (`--resume --run-id` or `swarm resume`)

### Failure Handling
- **on_failure: continue** - Default, continue with other agents
- **on_failure: stop** - Cancel all agents on first failure
- **on_failure: retry** - Retry failed agents up to `retry_count` times
- **Error context injection** - Previous error shown in retry prompt
- **Circuit breaker** - Trip after N failures (cancel_all/pause/notify)
- **Cascade failures** - Skip agents with failed dependencies

### Coordination Tools
Worker tools: `mark_complete`, `request_clarification`, `report_progress`, `report_blocker`
Manager tools: `spawn_worker`, `respond_to_clarification`, `cancel_worker`, `get_worker_status`, `get_pending_clarifications`, `mark_plan_complete`

### Roles
Built-in roles: `architect`, `implementer`, `tester`, `reviewer`, `debugger`, `refactorer`, `documenter`

## Plan Spec Format

```yaml
name: my-plan
defaults:
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
    use_role: implementer
  - name: tests
    prompt: "Write tests for auth"
    use_role: tester
    depends_on: [auth]
```

## File Layout

```
.swarm/
└── runs/{run_id}/
    ├── swarm.db                # SQLite state (WAL mode)
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
