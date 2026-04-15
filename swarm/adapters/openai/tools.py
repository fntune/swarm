"""OpenAI Agents SDK coord tools.

Thin @function_tool closures that forward to the CoordinationBackend.
Filtered by the agent's profile.coord_ops at build time.
"""

from typing import Any

from swarm.core.agent import AgentRequest
from swarm.core.coordination import CoordinationBackend
from swarm.core.events import CoordCall
from swarm.core.execution import RunContext


def build_coord_tools(
    ctx: RunContext,
    agent_name: str,
    coord_ops: frozenset[str],
) -> list[Any]:
    from agents import function_tool

    backend: CoordinationBackend = ctx.coord
    tools: list[Any] = []

    def _emit(op: str, payload: dict) -> None:
        ctx.events.emit(
            CoordCall(run_id=ctx.run_id, agent=agent_name, op=op, payload=payload)
        )

    if "mark_complete" in coord_ops:
        @function_tool
        async def mark_complete(summary: str) -> str:
            """Signal task completion. Runs the agent's check command automatically."""
            _emit("mark_complete", {"summary_len": len(summary)})
            r = await backend.mark_complete(ctx.run_id, agent_name, summary)
            return r.text

        tools.append(mark_complete)

    if "report_progress" in coord_ops:
        @function_tool
        async def report_progress(status: str, milestone: str = "") -> str:
            """Report non-blocking progress."""
            _emit("report_progress", {"status": status})
            r = await backend.report_progress(
                ctx.run_id, agent_name, status, milestone or None
            )
            return r.text

        tools.append(report_progress)

    if "request_clarification" in coord_ops:
        @function_tool
        async def request_clarification(question: str, escalate_to: str = "auto") -> str:
            """Ask the parent for guidance. BLOCKS until response or timeout."""
            _emit("request_clarification", {"question_len": len(question)})
            r = await backend.request_clarification(
                ctx.run_id, agent_name, question, escalate_to, timeout=300
            )
            return r.text

        tools.append(request_clarification)

    if "report_blocker" in coord_ops:
        @function_tool
        async def report_blocker(issue: str) -> str:
            """Report a blocking issue. BLOCKS until resolved."""
            _emit("report_blocker", {"issue_len": len(issue)})
            r = await backend.report_blocker(
                ctx.run_id, agent_name, issue, timeout=300
            )
            return r.text

        tools.append(report_blocker)

    if "spawn" in coord_ops:
        @function_tool
        async def spawn_worker(
            name: str,
            prompt: str,
            profile: str = "implementer",
            model: str = "",
            check: str = "",
        ) -> str:
            """Spawn a child worker agent."""
            _emit("spawn", {"name": name})
            req = AgentRequest(
                name=name,
                prompt=prompt,
                profile=profile or None,
                model=model or None,
                check=check or None,
            )
            r = await backend.spawn(ctx.run_id, agent_name, req)
            return r.text

        tools.append(spawn_worker)

    if "status" in coord_ops:
        @function_tool
        async def get_worker_status(name: str = "") -> str:
            """Get status of one or all child workers."""
            _emit("status", {"name": name})
            r = await backend.status(ctx.run_id, agent_name, name or None)
            return r.text

        tools.append(get_worker_status)

    if "respond" in coord_ops:
        @function_tool
        async def respond_to_clarification(
            clarification_id: str, response: str
        ) -> str:
            """Reply to a worker's clarification/blocker event."""
            _emit("respond", {"id": clarification_id[:8]})
            r = await backend.respond(
                ctx.run_id, agent_name, clarification_id, response
            )
            return r.text

        tools.append(respond_to_clarification)

    if "cancel" in coord_ops:
        @function_tool
        async def cancel_worker(name: str) -> str:
            """Cancel a child worker."""
            _emit("cancel", {"name": name})
            r = await backend.cancel(ctx.run_id, agent_name, name)
            return r.text

        tools.append(cancel_worker)

    if "pending_clarifications" in coord_ops:
        @function_tool
        async def get_pending_clarifications() -> str:
            """List unanswered clarification/blocker events from children."""
            _emit("pending_clarifications", {})
            r = await backend.pending_clarifications(ctx.run_id, agent_name)
            return r.text

        tools.append(get_pending_clarifications)

    if "mark_plan_complete" in coord_ops:
        @function_tool
        async def mark_plan_complete(summary: str) -> str:
            """Signal the orchestrator's plan is complete."""
            _emit("mark_plan_complete", {"summary_len": len(summary)})
            r = await backend.mark_plan_complete(ctx.run_id, agent_name, summary)
            return r.text

        tools.append(mark_plan_complete)

    return tools
