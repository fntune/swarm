# Claude Swarm - Design Plan

## Vision

Multi-agent orchestration for Claude Code:
- **Loop**: In-session plan-file iteration via stop hooks
- **Spawn**: Parallel agents in git worktrees
- **Pipeline**: Sequential workflows (plan → implement → test → review)
- **DAG**: Dependency-based multi-agent coordination

## Two-System Architecture

| Aspect | Loop (`/loop`) | Orchestration (`/spawn`, `/dag`) |
|--------|----------------|----------------------------------|
| Runs in | Claude Code session | External Python (SDK) |
| Mechanism | Stop hooks | Claude Agent SDK |
| State | `.claude/agent.local.md` | `.swarm/` JSON files |
| Purpose | Plan-file iteration | Multi-agent coordination |

## Implementation Phases

### Phase 1: Loop + Foundation
**Goal:** Single-agent plan-file iteration with CLI

1. Create plugin structure with `pyproject.toml`
2. Implement `swarm/models.py` - Pydantic LoopState model
3. Implement `swarm/state.py` - State file I/O
4. Implement `hooks/stop_hook.py`:
   - Detect `<done/>` token
   - Handle retry with error context
   - Auto-commit on each iteration
5. Implement `swarm/loop.py` - Loop setup, cancel-and-replace
6. Implement `swarm/cli.py` - Click CLI
7. Create `/loop`, `/cancel` slash commands
8. Add shell alias: `alias swarm="python ~/.claude/claude-swarm/swarm/cli.py"`

**Deliverable:** `/loop PLAN.md` works end-to-end

### Phase 2: Parallel Agents
- `swarm/spawn.py` - Worktree creation + SDK agent launch
- `swarm/coordination.py` - Per-agent JSON files
- `swarm/agents.py` - Subprocess monitoring
- `/spawn`, `/status` commands

### Phase 3: Pipelines
- `swarm/pipeline.py` - Stage transitions, artifact passing
- Workflow YAML schema
- `/pipeline` command

### Phase 4: Swarm + Merge
- `swarm/swarm_cmd.py` - Pattern-based spawning
- `swarm/merge.py` - Branch consolidation + auto-cleanup
- `/swarm`, `/merge` commands

### Phase 5: DAG Orchestration
- `swarm/dag.py` - Task spec parsing, dependency graph
- `swarm/scheduler.py` - Daemon polling, spawn on deps satisfied
- `/dag` command

### Phase 6: MCP Server
- `swarm/mcp_server.py` - Full control via MCP protocol

## File Structure

```
~/.claude/claude-swarm/
├── .claude-plugin/plugin.json
├── hooks/
│   ├── hooks.json
│   └── stop_hook.py
├── swarm/
│   ├── __init__.py
│   ├── cli.py
│   ├── loop.py
│   ├── spawn.py
│   ├── dag.py
│   ├── models.py
│   └── state.py
├── commands/
│   ├── loop.md
│   ├── spawn.md
│   └── ...
├── templates/           # Orchestration only
├── workflows/
├── pyproject.toml
└── requirements.txt

PROJECT/
└── worktrees/
    ├── .swarm/          # Coordination state
    └── {agent}/         # Agent worktrees
```

## Key Design Decisions

1. **State**: JSON files only (no git tags)
2. **Completion**: `<done/>` token
3. **Max iterations**: 30 default
4. **Worktrees**: `{name}-{uuid}` naming, project-local
5. **Cleanup**: Auto after successful merge
6. **Templates**: Orchestration only (not loop)
7. **Agent SDK**: For spawn/DAG, hooks for loop

## Hook Contract

```python
# Input (stdin)
{"session_id": "...", "transcript": [...]}

# Output (stdout)
{"decision": "allow"}  # Let exit
{"decision": "block", "reason": "Continue: ..."}  # Re-inject prompt
```

## Agent State Schema

```json
{
  "agent_id": "auth-abc123",
  "status": "running",
  "iteration": 5,
  "max_iterations": 30,
  "pid": 12345,
  "worktree": "./worktrees/auth-abc123",
  "started_at": "2026-01-04T12:00:00Z"
}
```
