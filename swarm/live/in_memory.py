"""In-memory coordination backend for live mode.

Batch mode's SqliteCoordinationBackend persists every state transition.
Live mode runs a single pipeline in one process and doesn't need
persistence — it just needs enough plumbing for mark_complete /
report_progress / report_blocker / request_clarification to work without
blocking indefinitely.

v1 semantics:
- mark_complete: records the status against the in-memory table and runs
  the check command in the workspace.
- report_progress: forwards to an EventSink, no-op otherwise.
- request_clarification, report_blocker: auto-acknowledge with a generic
  "no parent available; proceed" response. Orchestrator-in-live-mode is
  the deferred feature — if someone calls request_clarification expecting
  a real reply, they'll get a message telling them to move on.
- spawn: raises CoordinationNotSupported. Live mode has no scheduler;
  callers who want nested pipelines should compose them directly via
  pipeline() rather than asking the backend to spawn.
- All other orchestrator ops (status, respond, cancel,
  pending_clarifications, mark_plan_complete): raise
  CoordinationNotSupported.
"""

import asyncio
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from swarm.core.agent import AgentRequest
from swarm.core.coordination import CoordinationBackend, CoordOp, CoordResult
from swarm.core.errors import CoordinationNotSupported
from swarm.core.events import CoordCall, EventSink, NullSink

logger = logging.getLogger("swarm.live.in_memory")

_SUPPORTED = {
    CoordOp.MARK_COMPLETE,
    CoordOp.REPORT_PROGRESS,
    CoordOp.REPORT_BLOCKER,
    CoordOp.REQUEST_CLARIFICATION,
}


@dataclass
class _AgentRec:
    status: str = "pending"
    summary: str = ""
    check: str = "true"
    cwd: Path = field(default_factory=Path.cwd)


class InMemoryCoordinationBackend:
    name = "in_memory"

    def __init__(self, event_sink: EventSink | None = None):
        self.events = event_sink or NullSink()
        self._agents: dict[tuple[str, str], _AgentRec] = {}
        self._lock = asyncio.Lock()

    def supports(self, op: CoordOp) -> bool:
        return op in _SUPPORTED

    def register_agent(
        self,
        run_id: str,
        agent: str,
        *,
        check: str = "true",
        cwd: Path | None = None,
    ) -> None:
        self._agents[(run_id, agent)] = _AgentRec(
            check=check, cwd=cwd or Path.cwd()
        )

    def get_status(self, run_id: str, agent: str) -> str:
        rec = self._agents.get((run_id, agent))
        return rec.status if rec else "unknown"

    # -- worker ops ---------------------------------------------------------

    async def mark_complete(
        self, run_id: str, agent: str, summary: str
    ) -> CoordResult:
        rec = self._agents.get((run_id, agent))
        if rec is None:
            return CoordResult(
                text=f"ERROR: Agent {agent} not registered", success=False
            )
        proc = subprocess.run(
            rec.check,
            shell=True,
            cwd=str(rec.cwd),
            capture_output=True,
            text=True,
        )
        self.events.emit(
            CoordCall(run_id=run_id, agent=agent, op="mark_complete", payload={})
        )
        if proc.returncode == 0:
            rec.status = "completed"
            rec.summary = summary
            return CoordResult(text="Task completed. Check passed.")
        output = f"{proc.stdout}\n{proc.stderr}".strip()[-1000:]
        return CoordResult(
            text=f"Check failed. Fix and retry.\n\nOutput:\n{output}",
            success=False,
        )

    async def report_progress(
        self, run_id: str, agent: str, status: str, milestone: str | None
    ) -> CoordResult:
        self.events.emit(
            CoordCall(
                run_id=run_id,
                agent=agent,
                op="report_progress",
                payload={"status": status, "milestone": milestone},
            )
        )
        return CoordResult(text="Progress recorded.")

    async def report_blocker(
        self, run_id: str, agent: str, issue: str, timeout: int
    ) -> CoordResult:
        logger.warning("[%s] blocker: %s", agent, issue)
        self.events.emit(
            CoordCall(
                run_id=run_id,
                agent=agent,
                op="report_blocker",
                payload={"issue": issue},
            )
        )
        return CoordResult(
            text="No parent available in live mode. Proceed as best you can and describe the blocker in your final summary.",
            success=False,
        )

    async def request_clarification(
        self,
        run_id: str,
        agent: str,
        question: str,
        escalate_to: str,
        timeout: int,
    ) -> CoordResult:
        logger.info("[%s] clarification: %s", agent, question)
        self.events.emit(
            CoordCall(
                run_id=run_id,
                agent=agent,
                op="request_clarification",
                payload={"question": question},
            )
        )
        return CoordResult(
            text="No parent available in live mode. Proceed with your best guess and document assumptions in your final summary.",
            success=False,
        )

    # -- orchestrator ops (not supported in v1) -----------------------------

    async def spawn(
        self, run_id: str, parent: str, request: AgentRequest
    ) -> CoordResult:
        raise CoordinationNotSupported(self.name, CoordOp.SPAWN.value)

    async def status(
        self, run_id: str, parent: str, name: str | None
    ) -> CoordResult:
        raise CoordinationNotSupported(self.name, CoordOp.STATUS.value)

    async def respond(
        self,
        run_id: str,
        parent: str,
        clarification_id: str,
        response: str,
    ) -> CoordResult:
        raise CoordinationNotSupported(self.name, CoordOp.RESPOND.value)

    async def cancel(
        self, run_id: str, parent: str, name: str
    ) -> CoordResult:
        raise CoordinationNotSupported(self.name, CoordOp.CANCEL.value)

    async def pending_clarifications(
        self, run_id: str, parent: str
    ) -> CoordResult:
        raise CoordinationNotSupported(
            self.name, CoordOp.PENDING_CLARIFICATIONS.value
        )

    async def mark_plan_complete(
        self, run_id: str, agent: str, summary: str
    ) -> CoordResult:
        raise CoordinationNotSupported(
            self.name, CoordOp.MARK_PLAN_COMPLETE.value
        )
