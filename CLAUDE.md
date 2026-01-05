# CLAUDE.md

## Project Overview

**claude-swarm** - Multi-agent orchestration framework for Claude Code.

Two-system architecture:
- **Loop** (`/loop`): In-session plan-file iteration via stop hooks
- **Orchestration** (`/spawn`, `/dag`, `/swarm`): External multi-agent coordination via Claude Agent SDK

## Commands

```bash
# Development
pip install -e .
swarm --help

# Testing
pytest tests/
```

## Architecture

```
swarm/                    # Python package
├── cli.py               # Click CLI entrypoint
├── loop.py              # Loop management (hook-based)
├── spawn.py             # Worktree + SDK agent creation
├── dag.py               # DAG orchestration
├── models.py            # Pydantic state models
└── state.py             # State file I/O

hooks/
└── stop_hook.py         # Stop hook for /loop

commands/                # Slash command definitions
├── loop.md
├── spawn.md
└── ...
```

## Key Patterns

1. **State files**: JSON in `.swarm/` directory, each agent owns its file
2. **Completion token**: `<done/>` signals task completion
3. **Worktrees**: Project-local `./worktrees/` with auto-cleanup after merge
4. **Hook contract**: stdin JSON → stdout `{decision: "allow"|"block", reason?: string}`

## Dependencies

- `pydantic>=2.0` - State models
- `click>=8.0` - CLI
- `pyyaml>=6.0` - Config parsing
- `jinja2>=3.0` - Template rendering (orchestration only)
- `claude-agent-sdk` - SDK agent spawning (Phase 2+)

## Style

- Follow global CLAUDE.md conventions
- No templates for loop mode (plan-file iteration only)
- Templates only for orchestration (pipelines, spawn)
