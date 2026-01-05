# Claude Swarm - Design Plan

## Vision

A comprehensive orchestration system for Claude Code enabling:
- **Parallel agents** working in git worktrees
- **Pipeline workflows** (plan → implement → test → review)
- **Hierarchical delegation** (manager → workers)
- **Auto-detection completion** with templates
- **Progress tracking** and checkpointing

## Architecture

### Distribution Layers

```
┌─────────────────────────────────────────────────────────────────┐
│                    User Interfaces                               │
├─────────────────┬─────────────────┬─────────────────────────────┤
│ Claude Code     │ CLI Tool        │ MCP Server                  │
│ /loop, /spawn   │ orch loop       │ tools: spawn, status,       │
│ /status, etc.   │ orch spawn      │ cancel, merge               │
└────────┬────────┴────────┬────────┴──────────────┬──────────────┘
         │                 │                        │
         └─────────────────┴────────────────────────┘
                           │
                           ▼
         ┌─────────────────────────────────┐
         │  Python Package (shared logic)  │
         │  ~/.claude/claude-swarm/swarm/  │
         └─────────────────────────────────┘
```

### File Structure

```
~/.claude/
├── claude-swarm/                    # Core orchestration system
│   ├── .claude-plugin/plugin.json   # Claude Code plugin manifest
│   ├── hooks/
│   │   ├── hooks.json              # Hook registration (automatic)
│   │   └── stop_hook.py            # Unified stop hook (Python)
│   ├── swarm/                       # Python package (core logic)
│   │   ├── __init__.py
│   │   ├── cli.py                  # Click CLI entrypoint
│   │   ├── loop.py                 # Loop management
│   │   ├── spawn.py                # Worktree + agent creation
│   │   ├── agents.py               # Agent polling/status (subprocess poll)
│   │   ├── pipeline.py             # Sequential workflows
│   │   ├── swarm_cmd.py            # Parallel spawning
│   │   ├── merge.py                # Branch consolidation + auto-cleanup
│   │   ├── coordination.py         # Per-agent files, merge on read
│   │   ├── state.py                # State file I/O
│   │   ├── templates.py            # Jinja2 template loading
│   │   ├── models.py               # Pydantic models
│   │   └── mcp_server.py           # MCP daemon server (Phase 5)
│   ├── commands/                    # /slash commands (bash wrappers)
│   │   ├── loop.md
│   │   ├── spawn.md
│   │   ├── pipeline.md
│   │   ├── swarm.md
│   │   ├── status.md
│   │   ├── cancel.md
│   │   └── merge.md
│   ├── templates/
│   │   ├── fix-tests.yaml
│   │   ├── lint-fix.yaml
│   │   ├── implement.yaml
│   │   └── refactor.yaml
│   ├── workflows/
│   │   ├── tdd.yaml
│   │   ├── feature.yaml
│   │   └── refactor.yaml
│   ├── pyproject.toml
│   └── requirements.txt
├── swarm/
│   └── logs/                        # Central log directory
│       └── {agent_id}.log          # One log file per agent
└── state/
    └── swarm.json                   # Global agent registry

PROJECT/
├── .gitignore                       # Contains: worktrees/
└── worktrees/                       # Project-local worktrees
    ├── .swarm/                      # Per-agent coordination files
    │   ├── {agent_id}.json         # Each agent owns its file
    │   └── ...                     # Merged on read for status
    ├── auth/                        # Agent worktree (branch: auth)
    │   └── .claude/agent.local.md  # Agent-specific state
    └── cache/                       # Another worktree (branch: cache)
```

## Two-System Architecture

The framework is split into two completely separate systems:

| Aspect | Loop (`/loop`) | Orchestration (`/spawn`, `/dag`, `/swarm`) |
|--------|----------------|-------------------------------------------|
| **Runs in** | Claude Code session | External Python (SDK) |
| **Mechanism** | Stop hooks | Claude Agent SDK |
| **State** | `.claude/agent.local.md` | `.swarm/` JSON files |
| **Purpose** | Iterative plan execution | Multi-agent coordination |
| **Interaction** | None - completely isolated | None - completely isolated |

**Why separate?** Hooks intercept Claude Code exit events (in-session). SDK spawns external agents (out-of-session). These are mutually exclusive architectures that serve different use cases.

## Core Components

### 1. Loop (Single Agent) - `/loop`

Simplified plan-file iteration:
- Iterates on existing plan files (PLAN.md, TODO.md, etc.)
- Safe defaults (max=30 iterations)
- Claude-native `<done/>` token for completion
- CLI access via `swarm loop`
- Replaces active loop if one exists

```bash
/loop                               # Iterate on default plan file
/loop PLAN.md                       # Iterate on specific plan file
/loop --max 20                      # Custom iteration limit

# CLI equivalent
swarm loop
swarm loop PLAN.md --max 20
```

**Completion:** Agent outputs `<done/>` when plan is complete.
**Auto-commit:** Changes committed on each iteration for checkpointing.

### 2. Parallel Agents - `/spawn`

Spawn agents in git worktrees:

```bash
# Spawn 3 parallel agents
/spawn "Implement auth module" --worktree auth
/spawn "Implement cache module" --worktree cache
/spawn "Implement logging module" --worktree logging

# View status
/status

# Merge when complete
/merge auth cache logging
```

**Implementation:**
- Each `/spawn` creates a git worktree
- Launches background Claude Code session
- Tracks in `~/.claude/state/orchestrator.json`
- Uses existing `worktree-diff` for consolidation

### 3. Pipeline Workflows - `/pipeline`

Sequential agent handoffs:

```bash
/pipeline feature "Add user authentication"
# Runs: plan → implement → test → review
```

**Pre-built pipelines:**

```yaml
# workflows/feature.yaml
name: feature
description: Full feature development pipeline
stages:
  - name: plan
    template: plan
    output: PLAN.md
  - name: implement
    template: implement
    input: PLAN.md
    check: "ruff check . && pytest"
  - name: review
    template: review
    input: git diff main...HEAD
```

### 4. Swarm (Parallel + Merge) - `/swarm`

Parallel agents with automatic merge:

```bash
/swarm refactor "Refactor all services to use async" --pattern "src/services/*.py"
# Creates N agents for N files, merges when all complete
```

### 5. Status & Control - `/status`, `/cancel`

```bash
/status
# ┌──────────┬──────────┬─────────┬────────────┐
# │ Agent    │ Worktree │ Status  │ Iteration  │
# ├──────────┼──────────┼─────────┼────────────┤
# │ auth     │ wt-auth  │ running │ 5/30       │
# │ cache    │ wt-cache │ done    │ 12/30      │
# │ logging  │ wt-log   │ failed  │ 8/30       │
# └──────────┴──────────┴─────────┴────────────┘

/cancel auth         # Cancel specific agent
/cancel --all        # Cancel all agents
```

## State Management

### Orchestrator State (`~/.claude/state/orchestrator.json`)

```json
{
  "version": 1,
  "agents": {
    "auth-abc123": {
      "name": "auth",
      "worktree": "/path/to/wt-auth",
      "branch": "feature-auth",
      "status": "running",
      "iteration": 5,
      "max_iterations": 30,
      "started_at": "2026-01-01T12:00:00Z",
      "pid": 12345,
      "check_command": "pytest tests/auth/",
      "template": "implement"
    }
  },
  "pipelines": {
    "feature-xyz": {
      "name": "Add user auth",
      "current_stage": "implement",
      "stages": ["plan", "implement", "test", "review"],
      "completed": ["plan"],
      "artifacts": {
        "plan": "PLAN.md"
      }
    }
  }
}
```

### Agent State (per worktree: `.claude/agent.local.md`)

```yaml
---
active: true
iteration: 5
max_iterations: 30
completion_token: "<done/>"
parent_pipeline: "feature-xyz"
started_at: "2026-01-01T12:00:00Z"
---

Implement auth module per PLAN.md...

When complete, output <done/> to signal completion.
```

## Communication Patterns

### Layer 1: Git (Artifact Durability)
- Each agent commits to own branch in its worktree
- Artifacts passed via committed files (PLAN.md, etc.)
- Full audit trail via git history
- Merge conflicts handled at consolidation time

### Layer 2: Coordination State (Per-Agent Files)
```
./worktrees/.swarm/
├── {agent_id}.json     # Each agent owns its file
├── tasks/              # Task spec files for DAG orchestration
│   └── feature-xyz.md  # Manager-written task specs
└── results/            # Completed task results
    └── {task_name}.json
```

**Agent state file schema:**
```json
{
  "agent_id": "auth-abc123",
  "status": "running",
  "iteration": 5,
  "worktree": "auth",
  "branch": "auth",
  "started_at": "2026-01-01T12:00:00Z"
}
```

**Task result schema:**
```json
{
  "task_name": "auth-module",
  "status": "completed",
  "result": {
    "summary": "Implemented JWT auth with refresh tokens",
    "files_changed": ["src/auth.py", "src/middleware.py"],
    "tests_passed": true
  },
  "completed_at": "2026-01-01T14:30:00Z"
}
```

### Layer 3: Per-Agent State
- `./worktrees/AGENT/.claude/agent.local.md` - agent's own loop state
- Read by stop-hook for loop control
- Updated by agent each iteration

### Coordination Flow (Simple)
```
1. Agent starts → writes own state file
2. Agent works → commits to branch → updates state
3. Agent completes → writes <done/> → writes result file
4. Orchestrator → reads all state files → updates status
5. Orchestrator → merges branches → cleans up
```

## DAG Orchestration (Multi-Agent)

### Task Spec Format (Markdown + YAML Frontmatter)

Manager agent writes task specs to `.swarm/tasks/`:

```markdown
---
name: implement-user-auth
type: dag
subtasks:
  - name: auth-module
    prompt: "Implement JWT authentication with refresh tokens"
    worktree: auth
    depends_on: []
    on_failure: continue   # continue | stop | retry

  - name: cache-module
    prompt: "Implement Redis session cache"
    worktree: cache
    depends_on: []
    on_failure: stop

  - name: integration
    prompt: "Integrate auth with cache, add middleware"
    worktree: integration
    depends_on: [auth-module, cache-module]
    on_failure: retry
---

# Feature: User Authentication

Manager decomposed this feature into 3 subtasks.
Auth and cache can run in parallel, integration waits for both.
```

### DAG Execution Flow

```
                    ┌─────────────┐
                    │   Manager   │
                    │   Agent     │
                    └──────┬──────┘
                           │ writes task spec
                           ▼
              ┌────────────────────────┐
              │ .swarm/tasks/auth.md   │
              └────────────┬───────────┘
                           │ orchestrator detects
                           ▼
              ┌────────────────────────┐
              │   Dependency Resolver  │
              │   (topological sort)   │
              └────────────┬───────────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
           ▼               ▼               │
    ┌─────────────┐ ┌─────────────┐        │
    │ auth-module │ │cache-module │        │
    │  (parallel) │ │  (parallel) │        │
    └──────┬──────┘ └──────┬──────┘        │
           │               │               │
           └───────┬───────┘               │
                   │ both complete         │
                   ▼                       │
           ┌─────────────┐                 │
           │ integration │ ◄───────────────┘
           │(waits for deps)
           └──────┬──────┘
                  │
                  ▼
           ┌─────────────┐
           │  Results to │
           │ .swarm/results/
           └─────────────┘
```

### Failure Handling (Per-Task Configurable)

| `on_failure` | Behavior |
|--------------|----------|
| `continue` | Mark failed, continue independent branches |
| `stop` | Cancel all pending/running tasks immediately |
| `retry` | Retry with error context (up to 3 times) |

### Cyclic Dependencies (Iterative Patterns)

Cycles are allowed for iterative refinement (e.g., test→fix→test):

```yaml
subtasks:
  - name: implement
    depends_on: []
  - name: test
    depends_on: [implement]
  - name: fix
    depends_on: [test]
    on_failure: continue
  - name: test  # Cycle back to test
    depends_on: [fix]
    max_iterations: 5  # Default: 5, then break cycle
```

### Tree Decomposition Pattern

For dynamic work breakdown:

```
1. Manager agent receives complex task
2. Manager analyzes, writes task spec with subtasks
3. Orchestrator spawns workers per subtask
4. Workers complete, write results to .swarm/results/
5. Worker requests new subtask → manager reviews → modifies spec
6. Manager reads results via coordination state
7. Manager synthesizes final output
```

### Orchestrator Scheduler

**Two modes:**
- **Daemon mode**: `swarm scheduler start` - polls for task specs
- **Hook mode**: Triggered on agent completion for simple flows

```python
# Daemon scheduler (start with: swarm scheduler start)
def scheduler_loop():
    while running:
        specs = read_task_specs(".swarm/tasks/")

        for spec in specs:
            graph = build_dependency_graph(spec.subtasks)

            # Handle cycles with max-depth tracking
            for task in graph.ready_tasks():
                if task.cycle_count < task.max_iterations:
                    if not is_running(task):
                        spawn_agent(task)

            for task in graph.running_tasks():
                # Check status field in coordination state
                if get_task_status(task) == "completed":
                    handle_completion(task, graph)

        sleep(poll_interval)

# Stop with: swarm scheduler stop
```

## Implementation Phases

### Phase 1: Loop + Foundation
**Goal:** Single-agent plan-file iteration with CLI

**Dependencies:** `pydantic`, `click`, `pyyaml`

1. Create plugin directory structure with `pyproject.toml`
2. Implement `swarm/models.py` - Pydantic models for state (LoopState)
3. Implement `swarm/state.py` - State file I/O (read/write `.claude/agent.local.md`)
4. Implement `hooks/stop_hook.py`:
   - Detect `<done/>` token in output
   - Handle retry with error + conversation summary
   - Auto-commit on each iteration
5. Implement `swarm/loop.py` - Loop setup, cancel-and-replace if active
6. Implement `swarm/cli.py` - Click CLI (`swarm loop`, `swarm cancel`)
7. Implement slash commands (bash wrappers calling Python):
   - `/loop` → `python ~/.claude/claude-swarm/swarm/cli.py loop "$@"`
   - `/cancel` → `python ~/.claude/claude-swarm/swarm/cli.py cancel`
8. Add shell alias to `.zshrc`: `alias swarm="python ~/.claude/claude-swarm/swarm/cli.py"`
9. Write integration tests for loop lifecycle

**Deliverable:** `/loop PLAN.md` and `swarm loop` work end-to-end

### Phase 2: Parallel Agents
**Goal:** Spawn agents in worktrees with coordination

1. Implement `swarm/spawn.py`:
   - Create git worktree with simple branch name
   - Launch `claude -p "prompt" --dangerously-skip-permissions` in background
   - Write agent state to `./worktrees/.swarm/{agent_id}.json`
2. Implement `swarm/coordination.py`:
   - Per-agent JSON files (no locking needed)
   - Merge all files on read for status
3. Implement `swarm/agents.py`:
   - Subprocess poll loop to monitor children
   - Log output to `~/.claude/swarm/logs/{agent_id}.log`
4. Extend `swarm/cli.py` - `swarm spawn`, `swarm status` commands
5. Implement `/spawn`, `/status` slash commands
6. Update `/cancel` to support named agents

**Deliverable:** `/spawn "task" --worktree foo` creates isolated agent

### Phase 3: Pipelines
**Goal:** Sequential multi-stage workflows

1. Design workflow YAML schema (stages, inputs, outputs, checks)
2. Implement `swarm/pipeline.py` - stage transitions, artifact passing, check execution
3. Create 3 workflows: tdd.yaml, feature.yaml, refactor.yaml
4. Extend `swarm/cli.py` - `swarm pipeline` command
5. Implement `/pipeline` slash command

**Deliverable:** `/pipeline feature "Add auth"` runs plan→implement→test→review

### Phase 4: Swarm + Merge
**Goal:** Parallel agents with automatic consolidation

1. Implement `swarm/swarm_cmd.py` - pattern-based spawning (glob → spawn per file)
2. Implement `swarm/merge.py`:
   - Branch consolidation using worktree-diff skill
   - Auto-cleanup worktree + branch after successful merge
3. Extend `swarm/cli.py` - `swarm swarm`, `swarm merge` commands
4. Implement `/swarm`, `/merge` slash commands

**Deliverable:** `/swarm refactor "Add types" --pattern "src/*.py"` parallelizes

### Phase 5: DAG Orchestration
**Goal:** Multi-agent coordination with dependency resolution

1. Implement `swarm/dag.py`:
   - Parse task spec files (markdown + YAML frontmatter)
   - Build dependency graph (topological sort)
   - Track task states: pending → running → completed/failed
2. Implement `swarm/scheduler.py`:
   - Polling loop to detect new task specs
   - Spawn agents when dependencies satisfied
   - Handle per-task failure modes (continue/stop/retry)
3. Implement `swarm/results.py`:
   - Write task results to `.swarm/results/`
   - Aggregate results for manager agent
4. Extend `swarm/cli.py` - `swarm dag`, `swarm graph` commands
5. Implement `/dag` slash command for manager agents
6. Add task spec template for managers to use

**Deliverable:** Manager writes `.swarm/tasks/feature.md`, workers auto-spawn with dep resolution

### Phase 6: MCP Server
**Goal:** External orchestration via MCP protocol

1. Implement `swarm/mcp_server.py`:
   - MCP daemon (background process)
   - Full control: spawn, status, cancel, merge, dag tools
2. Document MCP server registration in Claude Code settings

**Deliverable:** Other Claude sessions can orchestrate via MCP

### Phase 7: Observability
**Goal:** Rich monitoring and debugging

1. Compact table-formatted status display (box drawing)
2. DAG visualization (show dependency graph)
3. Per-agent iteration progress
4. Log aggregation from `~/.claude/swarm/logs/`
5. Optional: token/cost estimation

## Files to Create

**Phase 1 (Loop + Foundation):**
```
~/.claude/claude-swarm/
├── .claude-plugin/plugin.json       # Plugin manifest
├── hooks/
│   ├── hooks.json                  # Hook registration (automatic)
│   └── stop_hook.py                # Completion detection (<done/>), retry, auto-commit
├── swarm/                           # Python package (core logic)
│   ├── __init__.py
│   ├── cli.py                      # Click CLI entrypoint
│   ├── loop.py                     # Loop management (cancel-and-replace)
│   ├── state.py                    # State file I/O (.claude/agent.local.md)
│   └── models.py                   # Pydantic models for state
├── commands/                        # /slash commands (bash wrappers)
│   ├── loop.md                     # /loop → calls swarm/cli.py loop
│   └── cancel.md                   # /cancel → calls swarm/cli.py cancel
├── tests/
│   └── test_integration.py         # Integration tests
├── pyproject.toml
└── requirements.txt                 # pydantic, click, pyyaml
```

**Phase 2 (Parallel Agents):**
```
├── swarm/
│   ├── spawn.py                    # Worktree creation + claude launch
│   ├── agents.py                   # Subprocess poll loop
│   └── coordination.py             # Per-agent files, merge on read
├── commands/
│   ├── spawn.md
│   └── status.md
```

**Phase 3 (Pipelines):**
```
├── swarm/
│   └── pipeline.py                 # Stage transitions, artifact passing
├── commands/
│   └── pipeline.md
├── workflows/
│   ├── tdd.yaml
│   ├── feature.yaml
│   └── refactor.yaml
```

**Phase 4 (Swarm + Merge):**
```
├── swarm/
│   ├── swarm_cmd.py                # Pattern-based spawning
│   └── merge.py                    # Branch consolidation + auto-cleanup
├── commands/
│   ├── swarm.md
│   └── merge.md
```

**Phase 5 (DAG Orchestration):**
```
├── swarm/
│   ├── dag.py                      # Task spec parsing, dependency graph
│   ├── scheduler.py                # Polling loop, spawn on deps satisfied
│   └── results.py                  # Task result aggregation
├── commands/
│   └── dag.md                      # /dag command for managers
├── templates/
│   └── task-spec.yaml              # Template for manager task specs
```

**Phase 6 (MCP Server):**
```
├── swarm/
│   └── mcp_server.py               # MCP daemon server
```

## Key Design Decisions

### Naming & Distribution
1. **Package name**: `claude-swarm` (CLI: `swarm`)
2. **Plugin location**: `~/.claude/claude-swarm/`
3. **CLI installation**: Shell alias in `.zshrc`: `alias swarm="python ~/.claude/claude-swarm/swarm/cli.py"`
4. **Slash commands**: Direct names (`/loop`, `/spawn`) - bash wrappers call Python

### Agent Execution
5. **Agent execution**: Claude Agent SDK (Python) - not CLI subprocess
6. **Process management**: SDK handles agent lifecycle, PID + process check for stale detection
7. **Loop conflict**: Replace - cancel old loop, start new one
8. **Auto-commit**: Commit state update only (skip if no code changes)
9. **Conversation persistence**: Hybrid - SDK primary, git backup for crash recovery

### Completion & Retry
10. **Completion token**: `<done/>` (XML-style, Claude-native)
11. **Default max iterations**: 30 (safe default)
12. **Error detection**: Parse last assistant message for error patterns
13. **Retry context**: Key events extraction (tool calls + errors only)

### State Architecture (Files Only)
14. **Source of truth**: JSON files in `.swarm/` directory (no git tags)
15. **Agent state**: `.swarm/{agent_id}.json` - each agent owns its file
16. **Coordination**: Central coordinator assigns tasks (no self-claiming)
17. **Logs**: `~/.claude/swarm/logs/{agent_id}.log`

### Git & Worktrees
18. **Worktree location**: Project-local `./worktrees/`
19. **Worktree naming**: `{name}-{uuid_suffix}` (e.g., `auth-abc123`) - collision-proof
20. **Branch naming**: Same as worktree name
21. **Cleanup**: Auto-cleanup after successful merge
22. **Merge conflicts**: Spawn conflict-resolution agent automatically

### Templates (Orchestration Only)
23. **Template syntax**: Jinja2 `{{ variable }}` (for pipelines/spawn, not loop)
24. **Template schema**: Minimal - `prompt`, `max_iterations`, `check_command`
25. **Hook registration**: Plugin hooks.json (automatic)

### DAG Orchestration
26. **Orchestration model**: Both DAG and tree patterns supported
27. **Task identity**: UUID for each task instance (e.g., `test:abc123`, `test:def456`)
28. **Task dependencies**: Explicit `depends_on` in YAML frontmatter
29. **Delegation**: Manager writes task spec → central coordinator spawns workers
30. **Task spec format**: Markdown with YAML frontmatter
31. **Result handoff**: Workers write to `.swarm/results/`, manager reads via file query
32. **Failure modes**: Configurable per-task (`continue`, `stop`, `retry`)
33. **Dep check**: Status field in `.swarm/{task_id}.json`
34. **Scheduler mode**: Daemon only (`swarm scheduler start/stop`)
35. **Cyclic deps**: Allowed with max-depth (default: 5 iterations)
36. **Dynamic subtasks**: Only manager can modify task spec (workers request)
37. **Daemon control**: Manual `swarm scheduler start` / `swarm scheduler stop`

### Resource Management
38. **Rate limits**: Agent queue with throttling (central queue limits API calls)
39. **Token budget**: 150K tokens per agent (hard limit, kill if exceeded)
40. **Context overflow**: Automatic summarization when approaching limit
41. **Max concurrent agents**: Default 5 (configurable)
42. **Network failures**: SDK handles retry with idempotency
43. **Log management**: TTL-based cleanup (delete logs older than 7 days)
44. **File conflicts**: Each agent writes own file only (no conflicts possible)

### Security
45. **Template sandboxing**: Jinja2 SandboxedEnvironment (disable dangerous ops)

### MCP & Observability
46. **MCP mode**: Daemon (background process)
47. **MCP scope**: Full control (spawn, status, cancel, merge, dag)
48. **Status output**: Compact table format + DAG visualization
49. **Testing**: Integration tests only

## Failure Resilience

### Stale State Detection
```python
def is_agent_alive(agent_id: str) -> bool:
    state_file = Path(f".swarm/{agent_id}.json")
    if not state_file.exists():
        return False

    state = json.loads(state_file.read_text())
    pid = state.get("pid")

    if pid:
        try:
            os.kill(pid, 0)  # Check if process exists
            return True
        except OSError:
            return False  # Process dead, state is stale

    return False
```

### Agent State File Schema
```
File: .swarm/auth-abc123.json
{
    "agent_id": "auth-abc123",
    "status": "running",      # pending | running | completed | failed
    "iteration": 5,
    "max_iterations": 30,
    "pid": 12345,
    "worktree": "./worktrees/auth-abc123",
    "branch": "auth-abc123",
    "started_at": "2026-01-04T12:00:00Z",
    "last_heartbeat": "2026-01-04T12:05:00Z",
    "parent_task": "feature-xyz",     # For DAG tracking
    "error": null                      # Last error if any
}
```

### Error Detection (Parse Assistant Message)
```python
ERROR_PATTERNS = [
    r"Error:",
    r"Failed to",
    r"Exception:",
    r"Could not",
    r"Permission denied",
    r"No such file",
]

def detect_error(last_message: str) -> Optional[str]:
    for pattern in ERROR_PATTERNS:
        if match := re.search(pattern, last_message):
            # Extract context around error
            return extract_error_context(last_message, match)
    return None
```

### Key Events Extraction (Retry Context)
```python
def extract_key_events(conversation: list) -> str:
    events = []
    for msg in conversation[-10:]:  # Last 10 messages
        if msg.type == "tool_use":
            events.append(f"Tool: {msg.name}({msg.input})")
        elif msg.type == "tool_result" and msg.is_error:
            events.append(f"Error: {msg.content[:200]}")
    return "\n".join(events)
```

### Conflict Resolution Agent
```python
async def handle_merge_conflict(worktrees: list[str], target: str):
    # Create conflict branch
    conflict_branch = f"conflict-{uuid4().hex[:8]}"

    # Spawn resolution agent
    agent = await sdk.create_agent(
        prompt=f"""Resolve merge conflicts between branches:
        {worktrees}

        Target branch: {target}

        Review conflicts, make decisions, commit resolution.
        Output <done/> when resolved.""",
        worktree=f"conflict-resolver-{conflict_branch}"
    )

    await agent.run()
```

### Recovery on Crash
```python
def recover_from_crash():
    """Called on swarm scheduler start to recover orphaned agents."""
    for state_file in Path(".swarm").glob("*.json"):
        state = json.loads(state_file.read_text())
        agent_id = state_file.stem

        if state["status"] == "running":
            if not is_agent_alive(agent_id):
                # Mark as failed, allow retry
                state["status"] = "failed"
                state["error"] = "Agent crashed unexpectedly"
                state_file.write_text(json.dumps(state, indent=2))

                # Notify scheduler to potentially retry
                scheduler.notify_failure(agent_id)
```

## Python Hook Integration

Claude Code hooks are shell scripts, but we can invoke Python:

```json
// hooks/hooks.json
{
  "hooks": [
    {
      "matcher": {"event": "Stop"},
      "hooks": [{"command": "python ~/.claude/claude-swarm/hooks/stop_hook.py"}]
    }
  ]
}
```

**Hook contract:**
- Input: JSON via stdin (`{"session_id": "...", "transcript": [...]}`)
- Output: JSON to stdout
  - Allow exit: `{"decision": "allow"}`
  - Block + re-inject: `{"decision": "block", "reason": "Continue: <prompt>"}`

**stop_hook.py flow:**
```python
def main():
    data = json.load(sys.stdin)
    git_root = find_git_root()
    state = load_agent_state(git_root / ".claude/agent.local.md")

    if not state.active:
        return allow()

    last_output = extract_last_output(data["transcript"])

    # Check for completion token
    if "<done/>" in last_output:
        state.active = False
        save_agent_state(state)
        return allow()

    # Check for max iterations
    if state.iteration >= state.max_iterations:
        state.active = False
        save_agent_state(state)
        return allow()

    # Auto-commit changes on each iteration
    auto_commit(f"swarm: iteration {state.iteration}")

    # Check for errors - append context for retry
    error_context = extract_error_context(data["transcript"])
    if error_context:
        state.retry_count += 1
        summary = summarize_conversation(data["transcript"])
        prompt = f"{state.prompt}\n\nPrevious error:\n{error_context}\n\nContext:\n{summary}"
    else:
        state.retry_count = 0
        prompt = state.prompt

    state.iteration += 1
    save_agent_state(state)
    return block(f"Continue iteration {state.iteration}/{state.max_iterations}:\n{prompt}")
```

## Dependencies

```
# requirements.txt
pydantic>=2.0
click>=8.0
pyyaml>=6.0
jinja2>=3.0
anthropic>=0.30.0        # Claude API
claude-agent-sdk>=0.1.0  # Agent SDK for programmatic agents
mcp>=0.1.0               # Phase 6 - MCP server
```

## Usage Examples

### Simple loop (plan-file iteration)
```bash
# Via slash command
/loop                              # Iterate on default plan file
/loop PLAN.md                      # Iterate on specific plan file
/loop --max 20                     # Custom iteration limit

# Via CLI
swarm loop
swarm loop PLAN.md --max 20
```

### Parallel feature development
```bash
# Spawn agents in worktrees (branches: auth, cache)
/spawn "Auth module" --worktree auth
/spawn "Cache module" --worktree cache
/status                            # Monitor progress (compact table)
/merge auth cache                  # Consolidate + auto-cleanup
```

### Full pipeline
```bash
/pipeline feature "User authentication"
# Runs: plan → implement → test → review
```

### Codebase-wide refactor
```bash
/swarm refactor "Add type hints" --pattern "src/**/*.py" --max 50
# Spawns N agents (one per file), auto-merges when all complete
```

### CLI equivalents
```bash
swarm spawn "Auth module" --worktree auth
swarm status
swarm merge auth cache
swarm pipeline feature "User auth"
swarm swarm refactor "Add types" --pattern "src/*.py"
```
