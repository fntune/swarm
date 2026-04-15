"""CoordOp enum, CoordResult, and CoordinationBackend protocol.

Every coordination call — worker-initiated (mark_complete, report_progress,
report_blocker, request_clarification) and orchestrator-initiated (spawn,
status, respond, cancel, pending_clarifications, mark_plan_complete) — goes
through a single Protocol. Two implementations:

- batch/sqlite.py:SqliteCoordinationBackend writes to the nodes/attempts/
  events/coord_responses tables.
- live/in_memory.py:InMemoryCoordinationBackend uses asyncio queues; raises
  CoordinationNotSupported on spawn() in v1.

Adapter tool wrappers (adapters/claude/tools.py, adapters/openai/tools.py)
are thin SDK-specific closures around these methods.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from swarm.core.agent import AgentRequest


class CoordOp(str, Enum):
    MARK_COMPLETE = "mark_complete"
    REPORT_PROGRESS = "report_progress"
    REPORT_BLOCKER = "report_blocker"
    REQUEST_CLARIFICATION = "request_clarification"
    SPAWN = "spawn"
    STATUS = "status"
    RESPOND = "respond"
    CANCEL = "cancel"
    PENDING_CLARIFICATIONS = "pending_clarifications"
    MARK_PLAN_COMPLETE = "mark_plan_complete"


@dataclass(frozen=True)
class CoordResult:
    text: str
    success: bool = True
    data: dict[str, Any] = field(default_factory=dict)


class CoordinationBackend(Protocol):
    async def mark_complete(
        self, run_id: str, agent: str, summary: str
    ) -> CoordResult: ...

    async def report_progress(
        self, run_id: str, agent: str, status: str, milestone: str | None
    ) -> CoordResult: ...

    async def report_blocker(
        self, run_id: str, agent: str, issue: str, timeout: int
    ) -> CoordResult: ...

    async def request_clarification(
        self,
        run_id: str,
        agent: str,
        question: str,
        escalate_to: str,
        timeout: int,
    ) -> CoordResult: ...

    async def spawn(
        self, run_id: str, parent: str, request: "AgentRequest"
    ) -> CoordResult: ...

    async def status(
        self, run_id: str, parent: str, name: str | None
    ) -> CoordResult: ...

    async def respond(
        self,
        run_id: str,
        parent: str,
        clarification_id: str,
        response: str,
    ) -> CoordResult: ...

    async def cancel(
        self, run_id: str, parent: str, name: str
    ) -> CoordResult: ...

    async def pending_clarifications(
        self, run_id: str, parent: str
    ) -> CoordResult: ...

    async def mark_plan_complete(
        self, run_id: str, agent: str, summary: str
    ) -> CoordResult: ...

    def supports(self, op: CoordOp) -> bool: ...
