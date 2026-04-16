"""Live-mode pipeline: sequential agent dispatch, no SQLite, no DAG.

Takes a list of AgentRequests, resolves each via batch.plan.resolve_agent
(reusing the same profile / default / capability logic as batch mode),
allocates a workspace via the requested provider, and dispatches through
the executor registry. Returns a list of ExecutionResults in order.

handoff() is a convenience for the two-step case.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from uuid import uuid4

from swarm.batch.plan import PlanDefaults, resolve_agent
from swarm.core.agent import AgentRequest, ResolvedAgent
from swarm.core.events import (
    AgentCompleted,
    AgentStarted,
    CoordCall,
    CostUpdate,
    EventSink,
    IterationTick,
    LogText,
    NullSink,
    SwarmEvent,
)
from swarm.core.execution import ExecutionResult, RunContext, get_executor
from swarm.core.workspace import Workspace
from swarm.live.in_memory import InMemoryCoordinationBackend

logger = logging.getLogger("swarm.live.pipeline")

WorkspaceKind = Literal["cwd", "worktree", "tempdir"]


class StdoutSink:
    """Human-readable event sink for live runs — prints to stdout."""

    def emit(self, event: SwarmEvent) -> None:
        if isinstance(event, AgentStarted):
            print(f"[start]   {event.agent}  (runtime={event.runtime})")
        elif isinstance(event, AgentCompleted):
            err = f"  error={event.error}" if event.error else ""
            print(f"[done]    {event.agent}  status={event.status}{err}")
        elif isinstance(event, IterationTick):
            print(f"[tick]    {event.agent}  iter={event.iteration}")
        elif isinstance(event, CostUpdate):
            print(
                f"[cost]    {event.agent}  ${event.cost_usd:.4f} ({event.source})"
            )
        elif isinstance(event, CoordCall):
            print(f"[coord]   {event.agent}  {event.op}")
        elif isinstance(event, LogText):
            text = event.text.strip()
            if text:
                prefix = f"[log {event.agent}] "
                print(prefix + text.replace("\n", "\n" + prefix))


def _build_provider(kind: WorkspaceKind, base_path: Path | None):
    if kind == "cwd":
        from swarm.workspaces.cwd import CwdProvider

        return CwdProvider(base_path)
    if kind == "tempdir":
        from swarm.workspaces.temp import TempDirProvider

        return TempDirProvider()
    if kind == "worktree":
        from swarm.workspaces.git import GitWorktreeProvider

        return GitWorktreeProvider(repo_path=base_path)
    raise ValueError(f"Unknown workspace kind: {kind!r}")


@dataclass
class PipelineRun:
    run_id: str
    results: list[ExecutionResult] = field(default_factory=list)


async def pipeline(
    steps: list[AgentRequest],
    *,
    workspace: WorkspaceKind = "cwd",
    keep: bool = False,
    event_sink: EventSink | None = None,
    base_path: Path | None = None,
    defaults: PlanDefaults | None = None,
) -> list[ExecutionResult]:
    """Run a sequential pipeline of agents in live mode.

    Every step runs to completion before the next starts. Failure does not
    automatically stop the pipeline — callers inspect the returned results
    and decide.
    """
    if not steps:
        return []

    sink: EventSink = event_sink or StdoutSink()
    plan_defaults = defaults or PlanDefaults()
    run_id = f"live-{uuid4().hex[:8]}"
    provider = _build_provider(workspace, base_path)
    coord = InMemoryCoordinationBackend(event_sink=sink)

    results: list[ExecutionResult] = []
    for step in steps:
        resolved = resolve_agent(step, defaults=plan_defaults)
        ws = await provider.allocate(run_id, resolved.name)
        coord.register_agent(
            run_id, resolved.name, check=resolved.check, cwd=Path(ws.path)
        )
        ctx = RunContext(run_id=run_id, workspace=ws, coord=coord, events=sink)
        sink.emit(
            AgentStarted(run_id=run_id, agent=resolved.name, runtime=resolved.runtime)
        )
        executor = get_executor(resolved.runtime)
        try:
            result = await executor.run(resolved, ctx)
        except Exception as exc:  # noqa: BLE001
            logger.exception("pipeline step %s raised", resolved.name)
            result = ExecutionResult(
                status="failed",
                final_text="",
                cost_usd=0.0,
                cost_source="estimated",
                error=str(exc),
            )
        sink.emit(
            AgentCompleted(
                run_id=run_id,
                agent=resolved.name,
                status=result.status,
                error=result.error,
            )
        )
        results.append(result)
        await provider.release(ws, keep=keep)
    return results


async def handoff(
    a: AgentRequest,
    b: AgentRequest,
    *,
    workspace: WorkspaceKind = "cwd",
    keep: bool = False,
    event_sink: EventSink | None = None,
    base_path: Path | None = None,
    defaults: PlanDefaults | None = None,
) -> list[ExecutionResult]:
    """Two-step pipeline: a runs first, then b runs with visibility into
    a's final output via the second agent's prompt context."""
    return await pipeline(
        [a, b],
        workspace=workspace,
        keep=keep,
        event_sink=event_sink,
        base_path=base_path,
        defaults=defaults,
    )
